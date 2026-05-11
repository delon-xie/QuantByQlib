"""
Docker 管理器
通过 Python docker SDK 管理 RD-Agent 容器的生命周期
"""
from __future__ import annotations

from typing import Optional
from loguru import logger


# RD-Agent 使用本地构建的 local_qlib:latest 镜像（arm64 原生）
RDAGENT_IMAGE = "local_qlib:latest"
CONTAINER_NAME = "rdagent_fin_quant"

# 不指定平台，使用镜像原生架构（arm64）
PLATFORM = None


class DockerManager:
    """
    封装 Docker SDK 操作，提供容器级别的 start/stop/logs 接口。
    若 Docker 未安装或未运行，方法返回 False / 空字符串，不抛异常。
    """

    def __init__(self):
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        try:
            import docker
            import os

            # 按优先级尝试各 socket，找到能 ping 通且有目标镜像的连接
            # 顺序：Desktop socket → OrbStack → 默认 from_env
            candidate_sockets = [
                os.path.expanduser("~/.docker/run/docker.sock"),   # Docker Desktop
                os.path.expanduser("~/.orbstack/run/docker.sock"), # OrbStack
                "/var/run/docker.sock",                            # 标准 socket
            ]

            def _try_connect(base_url: str | None = None) -> docker.DockerClient:
                """尝试连接，自动降级 API 版本"""
                kwargs = {"base_url": base_url} if base_url else {}
                try:
                    c = docker.DockerClient(**kwargs) if base_url else docker.from_env()
                    c.ping()
                    return c
                except Exception as e:
                    if "is too new" in str(e) or "Maximum supported API version" in str(e):
                        os.environ["DOCKER_API_VERSION"] = "1.51"
                        c = docker.DockerClient(**kwargs) if base_url else docker.from_env()
                        c.ping()
                        return c
                    raise

            connected = False
            for sock in candidate_sockets:
                if not os.path.exists(sock):
                    continue
                try:
                    client = _try_connect(f"unix://{sock}")
                    self._client = client
                    connected = True
                    logger.info(f"Docker 连接成功（{sock}）")
                    break
                except Exception:
                    continue

            if not connected:
                # 最后兜底：from_env()
                self._client = _try_connect()
                logger.info("Docker 连接成功（from_env）")

            self._available = True
        except ImportError:
            logger.warning("docker 包未安装：pip install docker")
        except Exception as e:
            logger.warning(f"Docker 连接失败（Docker Desktop 是否运行？）：{e}")

    @property
    def available(self) -> bool:
        return self._available

    def check_docker(self) -> tuple[bool, str]:
        """
        检测 Docker 状态。
        Returns: (ok, status_message)
        """
        if not self._available:
            return False, "Docker 未连接（请检查 Docker Desktop 是否运行）"
        try:
            info = self._client.info()
            return True, f"Docker {info.get('ServerVersion', 'unknown')} 运行中"
        except Exception as e:
            return False, f"Docker 异常：{e}"

    def image_exists(self) -> bool:
        """检查 RD-Agent 镜像是否已拉取"""
        if not self._available:
            return False
        try:
            self._client.images.get(RDAGENT_IMAGE)
            return True
        except Exception:
            return False

    def pull_image(self, progress_cb=None) -> bool:
        """
        拉取 RD-Agent 镜像（约 2GB，首次运行）。
        progress_cb: callable(msg: str) 接收进度消息
        """
        if not self._available:
            return False
        try:
            logger.info(f"开始拉取镜像 {RDAGENT_IMAGE}...")
            if progress_cb:
                progress_cb(f"正在加载 {RDAGENT_IMAGE}（rdagent fin_quant 会自动构建此镜像）...")
            pull_kwargs = dict(stream=True, decode=True)
            if PLATFORM:
                pull_kwargs["platform"] = PLATFORM
            for line in self._client.api.pull(RDAGENT_IMAGE, **pull_kwargs):
                status = line.get("status", "")
                detail = line.get("progress", "")
                msg = f"{status} {detail}".strip()
                if msg and progress_cb:
                    progress_cb(msg)
            logger.info("镜像拉取完成")
            return True
        except Exception as e:
            logger.error(f"镜像拉取失败：{e}")
            return False

    def get_container(self):
        """获取已有容器（可能是 running/exited 状态）"""
        if not self._available:
            return None
        try:
            return self._client.containers.get(CONTAINER_NAME)
        except Exception:
            return None

    def container_status(self) -> str:
        """返回容器状态字符串，'not_found' / 'running' / 'exited' / 'unknown'"""
        c = self.get_container()
        if c is None:
            return "not_found"
        try:
            c.reload()
            return c.status  # 'running', 'exited', 'paused', etc.
        except Exception:
            return "unknown"

    def start_container(self,
                        env_vars: dict[str, str],
                        workspace_dir: str,
                        reg: str,
                        log_cb=None) -> tuple[bool, str]:
        """
        启动 RD-Agent 容器。
        env_vars:      传入容器的环境变量（含 LLM keys）
        workspace_dir: 宿主机工作目录（挂载为 /workspace）
        reg:           指定数据的{reg}拼接
        log_cb:        callable(msg: str) 实时接收启动日志

        Returns: (success, error_message)
        """
        if not self._available:
            return False, "Docker 不可用"

        # 若已有同名容器，先删除
        existing = self.get_container()
        if existing:
            try:
                existing.remove(force=True)
                logger.info(f"已删除旧容器 {CONTAINER_NAME}")
            except Exception as e:
                logger.warning(f"删除旧容器失败（忽略）：{e}")

        try:
            import os
            from pathlib import Path
            
            # ---------- 关键：挂载 scripts 目录 ----------
            project_root = Path(__file__).resolve().parent.parent
            logger.info(f"project_root : {project_root}")
            scripts_path = Path(f"{project_root}/scripts/run_factor_discovery.py")
            logger.info(f"scripts_path : {scripts_path}")
            core_path = Path(f"{project_root}/core")
            logger.info(f"core_path : {core_path}")
        
            volumes = {
                scripts_path: {"bind": "/workspace/run_factor_discovery.py", "mode": "rw"},
                f"{project_root}/core": {"bind": "/workspace/core", "mode": "rw"},
                f"{project_root}/log": {"bind": "/workspace/log", "mode": "rw"},
                f"{Path.home()}/.qlib/qlib_data": {"bind": "/root/.qlib/qlib_data", "mode": "rw"},
                
                # ✅ 实时挂载 run_factor_discovery.py（不依赖镜像编译，实时可以修改，放弃原有workspace 执行逻辑）
                #core_path: {"bind": "/app/core", "mode": "rw"},
                #str(scripts_path): {"bind": "/app/run_factor_discovery.py", "mode": "ro"},
            }
            # 如果宿主机有 qlib 数据，挂载进容器供 IC 验证使用
            qlib_data = Path(f"{Path.home()}/.qlib/qlib_data")
            if qlib_data.exists():
                volumes[str(qlib_data)] = {"bind": "/root/.qlib/qlib_data", "mode": "ro"}

            run_kwargs = dict(
                image=RDAGENT_IMAGE,
                name=CONTAINER_NAME,
                environment=env_vars,
                volumes=volumes,
                detach=True,
                remove=False,           # 保留容器方便查看日志
                network_mode="host",    # 容器直接使用宿主机网络
                command=[
                        "python",
                        #"/app/run_factor_discovery.py",
                        "/workspace/run_factor_discovery.py",
                        "--provider",
                        "deepseek",
                        "--reg",
                        reg,
                ],
            )
            if PLATFORM:
                run_kwargs["platform"] = PLATFORM
            container = self._client.containers.run(**run_kwargs)
            logger.info(f"容器 {CONTAINER_NAME} 启动成功，ID={container.short_id}")
            return True, ""

        except Exception as e:
            logger.error(f"容器启动失败：{e}")
            return False, str(e)

    def stop_container(self) -> bool:
        """停止容器"""
        c = self.get_container()
        if c is None:
            return True
        try:
            c.stop(timeout=10)
            logger.info(f"容器 {CONTAINER_NAME} 已停止")
            return True
        except Exception as e:
            logger.error(f"停止容器失败：{e}")
            return False

    def stream_logs(self, log_cb, stop_event=None) -> None:
        """
        实时流式读取容器日志，直到容器退出或 stop_event 置位。
        log_cb:     callable(line: str) 每行日志回调
        stop_event: threading.Event，置位时停止读取
        """
        c = self.get_container()
        if c is None:
            log_cb("[ERROR] 容器不存在，无法读取日志")
            return
        try:
            for chunk in c.logs(stream=True, follow=True):
                if stop_event and stop_event.is_set():
                    break
                line = chunk.decode("utf-8", errors="replace").rstrip()
                if line:
                    log_cb(line)
        except Exception as e:
            log_cb(f"[ERROR] 日志流异常：{e}")


# 模块级单例
_manager: Optional[DockerManager] = None


def get_docker_manager() -> DockerManager:
    global _manager
    if _manager is None:
        _manager = DockerManager()
    return _manager
