"""
RD-Agent 运行器
构建运行所需的环境变量，协调 DockerManager 启动因子发现会话
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from rdagent_integration.docker_manager import get_docker_manager
from core.app_state import get_state


# 默认工作目录（宿主机，挂载进容器）
DEFAULT_WORKSPACE = Path.home() / ".quantbyqlib" / "rdagent_workspace"


class RDAgentRunner:
    """
    启动并监控 RD-Agent 因子发现任务。

    典型用法：
        runner = RDAgentRunner(log_cb=..., done_cb=..., error_cb=...)
        runner.start()
        # ... 用户点击停止时：
        runner.stop()
    """

    def __init__(self,
                 log_cb,
                 done_cb=None,
                 error_cb=None,
                 workspace: Optional[Path] = None):
        """
        log_cb:    callable(str) — 每行日志
        done_cb:   callable(list) — 完成后传入因子列表
        error_cb:  callable(str) — 失败原因
        workspace: 宿主机工作目录（默认 ~/.quantbyqlib/rdagent_workspace）
        """
        self._log_cb   = log_cb
        self._done_cb  = done_cb
        self._error_cb = error_cb
        self._workspace = workspace or DEFAULT_WORKSPACE
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        启动 RD-Agent（非阻塞，日志通过回调推送）。
        Returns: False 表示启动前检查失败（详情通过 log_cb/error_cb 传出）
        """
        mgr = get_docker_manager()

        # 1. Docker 可用性检查
        ok, msg = mgr.check_docker()
        self._log_cb(f"[INFO] Docker 检测：{msg}")
        if not ok:
            if self._error_cb:
                self._error_cb(msg)
            return False

        # 2. 镜像检查（不自动拉取，提示用户手动操作）
        if not mgr.image_exists():
            hint = (
                "RD-Agent 镜像未找到（local_qlib:latest）。\n"
                "请参考文档 docs/04_安装配置手册.md 中的「构建 Docker 镜像」章节重新构建。"
            )
            self._log_cb(f"[WARN] {hint}")
            if self._error_cb:
                self._error_cb("RD-Agent 镜像未安装，请参考日志提示")
            return False

        # 3. 准备工作目录
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._log_cb(f"[INFO] 工作目录：{self._workspace}")

        # 3b. 将历史已发现因子写入 workspace，供容器内 prompt 去重使用
        self._write_history_factors()

        # 4. 构建环境变量
        env = self._build_env()
        chat_model = env.get("CHAT_MODEL", "deepseek-chat")
        self._log_cb(f"[INFO] 使用 LLM：{chat_model}")

        # 检查所选 LLM 对应的 Key 是否存在
        if chat_model.startswith("claude"):
            required_key, key_name = "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY（Claude）"
        elif chat_model.startswith("gpt") or chat_model.startswith("o1") or chat_model.startswith("o3"):
            required_key, key_name = "OPENAI_API_KEY", "OPENAI_API_KEY（GPT）"
        else:
            required_key, key_name = "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY（DeepSeek）"

        if not env.get(required_key):
            warn = f"{key_name} 未配置，请在「参数配置」页面设置后重试"
            self._log_cb(f"[ERROR] {warn}")
            if self._error_cb:
                self._error_cb(warn)
            return False

        # 5. 启动容器
        self._log_cb("[INFO] 正在启动 RD-Agent 容器...")
        reg = get_state().reg
        self._log_cb("[INFO] reg : {reg}")
        self._log_cb("[INFO] env : {env}")
        self._log_cb("[INFO] _workspace : {str(self._workspace)}")
        ok, err = mgr.start_container(
            env_vars=env,
            workspace_dir=str(self._workspace),
            reg = reg
        )
        if not ok:
            self._log_cb(f"[ERROR] 容器启动失败：{err}")
            if self._error_cb:
                self._error_cb(err)
            return False

        self._log_cb("[INFO] 容器启动成功，开始读取日志...")

        # 6. 后台线程流式读取日志
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._stream_loop,
            daemon=True,
            name="RDAgentLogStream",
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """请求停止（设置事件 + 停止容器）"""
        self._stop_event.set()
        get_docker_manager().stop_container()
        logger.info("RDAgentRunner 停止请求已发送")

    def _stream_loop(self) -> None:
        """后台线程：流式读取容器日志，解析因子输出"""
        mgr = get_docker_manager()
        discovered_factors: list[dict] = []

        def on_line(line: str) -> None:
            self._log_cb(line)
            # 简单解析：RD-Agent 输出含 "Factor:" 关键词时提取
            if "Factor:" in line or "factor_name:" in line.lower():
                discovered_factors.append({"raw": line})

        try:
            mgr.stream_logs(log_cb=on_line, stop_event=self._stop_event)
        except Exception as e:
            self._log_cb(f"[ERROR] 日志流异常：{e}")

        # 容器退出后
        status = mgr.container_status()
        self._log_cb(f"[INFO] 容器已退出，状态：{status}")

        if self._stop_event.is_set():
            logger.info("RDAgentRunner 用户停止，不触发 done_cb")
            return

        if status == "exited":
            # 优先从结果 JSON 文件读取结构化因子
            result_file = self._workspace / "discovered_factors.json"
            factors = []
            if result_file.exists():
                try:
                    import json
                    data = json.loads(result_file.read_text())
                    factors = data.get("factors", [])
                    self._log_cb(f"[INFO] 因子发现完成，共发现 {len(factors)} 个因子")
                except Exception as e:
                    self._log_cb(f"[WARN] 读取结果 JSON 失败：{e}，回退到日志解析")
                    factors = discovered_factors
            else:
                # 回退：使用日志行中解析的原始记录
                factors = discovered_factors
                self._log_cb(f"[INFO] 因子发现完成，共解析 {len(factors)} 条因子记录")

            # 持久化到 session_manager（供后续注入和历史查看使用）
            if factors:
                try:
                    from rdagent_integration.session_manager import get_session_manager
                    get_session_manager().add_session(factors)
                    self._log_cb(f"[INFO] 已记录本次会话（{len(factors)} 个因子）")
                except Exception as e:
                    self._log_cb(f"[WARN] 会话记录失败：{e}")

            if self._done_cb:
                self._done_cb(factors)
        else:
            err = f"容器异常退出，状态：{status}"
            self._log_cb(f"[ERROR] {err}")
            if self._error_cb:
                self._error_cb(err)

    def _write_history_factors(self) -> None:
        """
        将所有历史会话中发现过的因子表达式写入 workspace/history_factors.json，
        容器内 run_factor_discovery.py 读取此文件并在 prompt 中排除已知因子。
        """
        try:
            import json as _json
            from rdagent_integration.session_manager import get_session_manager
            all_sessions = get_session_manager().get_all()
            seen: dict[str, dict] = {}   # expression → {name, ic_mean}
            for s in all_sessions:
                for f in s.get("factors", []):
                    expr = (f.get("expression") or "").strip()
                    if expr and expr not in seen:
                        seen[expr] = {
                            "name":    f.get("name", ""),
                            "ic_mean": f.get("ic_mean"),
                        }
            out = {"count": len(seen), "factors": list(seen.values()),
                   "expressions": list(seen.keys())}
            hist_file = self._workspace / "history_factors.json"
            hist_file.write_text(_json.dumps(out, ensure_ascii=False, indent=2))
            self._log_cb(f"[INFO] 历史因子记录：{len(seen)} 个表达式已写入去重文件")
        except Exception as e:
            self._log_cb(f"[WARN] 历史因子写入失败（忽略）：{e}")

    def _build_env(self) -> dict[str, str]:
        """从 .env 文件和 app_state 构建传入容器的环境变量"""
        env: dict[str, str] = {}

        # 从 .env 文件读取
        try:
            from dotenv import dotenv_values
            project_root = Path(__file__).parent.parent
            env_file = project_root / ".env"
            if env_file.exists():
                env.update({k: v for k, v in dotenv_values(env_file).items() if v})
        except Exception:
            pass

        # 从系统环境变量覆盖（优先级更高）
        for key in ["CHAT_MODEL", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "FMP_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY"]:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # RD-Agent 专用配置
        env.setdefault("CHAT_MODEL", "deepseek-chat")
        env.setdefault("RD_AGENT_WORKSPACE", "/workspace")

        return env
