"""
QuantByQlib 环境预检脚本
运行方式：python3 scripts/check_env.py

检查内容：
  1. Python 版本
  2. 关键依赖包是否可导入
  3. Qlib 数据是否已下载
  4. API Key 是否配置（不检查有效性，仅检查是否非空）
  5. Docker 是否可用
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# ── 颜色输出 ──────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✅ {msg}{RESET}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠️  {msg}{RESET}")
def fail(msg: str) -> None: print(f"  {RED}❌ {msg}{RESET}")


def check_python() -> None:
    print("\n[1] Python 版本")
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v.major == 3 and v.minor >= 9:
        ok(f"Python {ver}")
    else:
        fail(f"Python {ver}（需要 3.9+）")


def check_packages() -> None:
    print("\n[2] 关键依赖包")
    packages = [
        ("PyQt6",        "PyQt6"),
        ("pyqtgraph",    "pyqtgraph"),
        ("qlib",         "qlib"),
        ("openbb",       "openbb"),
        ("lightgbm",     "lightgbm"),
        ("torch",        "torch"),
        ("loguru",       "loguru"),
        ("dotenv",       "dotenv"),
        ("docker",       "docker"),
        ("transformers", "transformers"),
        ("pandas",       "pandas"),
        ("numpy",        "numpy"),
    ]
    for label, module in packages:
        try:
            __import__(module)
            ok(label)
        except ImportError:
            fail(f"{label}（pip3 install {label.lower()}）")


def check_qlib_data() -> None:
    print("\n[3] Qlib 数据")
    data_path = Path.home() / ".qlib" / "qlib_data" / "us_data"
    if data_path.exists() and any(data_path.iterdir()):
        try:
            from core.qlibhelper import qlib_safeinit
            qlib_safeinit(uri)
            ok(f"Qlib 数据已就绪：{data_path}")
        except Exception as e:
            warn(f"Qlib 数据目录存在但初始化失败：{e}")
    else:
        warn(f"Qlib 数据未找到（{data_path}）\n"
             f"     → 应用将以降级模式运行\n"
             f"     → 下载命令：python3 -c \""
             f"from qlib.tests.data import GetData; "
             f"GetData().qlib_data(target_dir='~/.qlib/qlib_data/us_data', region='us')\"")


def check_api_keys() -> None:
    print("\n[4] API Key 配置")

    # 加载 .env
    root = Path(__file__).parent.parent
    env_file = root / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            ok(f".env 文件已加载：{env_file}")
        except ImportError:
            warn(".env 文件存在但 python-dotenv 未安装")
    else:
        warn(f".env 文件未找到（{env_file}）\n"
             f"     → 请参考 .env.example 创建")

    keys_info = [
        ("FMP_API_KEY",            "FMP（基本面）",        True),
        ("FINNHUB_API_KEY",        "Finnhub（新闻）",      True),
        ("ALPHA_VANTAGE_API_KEY",  "Alpha Vantage（K线）", False),
        ("DEEPSEEK_API_KEY",       "DeepSeek（因子发现）", False),
    ]
    for env_var, label, required in keys_info:
        val = os.environ.get(env_var, "")
        if val:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            ok(f"{label}：{masked}")
        elif required:
            warn(f"{label}：未配置（建议配置，否则对应功能显示「暂无数据」）")
        else:
            warn(f"{label}：未配置（可选）")


def check_docker() -> None:
    print("\n[5] Docker")
    try:
        import docker
        client = docker.from_env()
        client.ping()
        info = client.info()
        ok(f"Docker {info.get('ServerVersion', 'unknown')} 运行中")

        # 检查 RD-Agent 镜像（rdagent 自行构建 local_qlib:latest）
        try:
            client.images.get("local_qlib:latest")
            ok("RD-Agent 镜像已就绪（local_qlib:latest）")
        except Exception:
            warn("RD-Agent 镜像未构建\n"
                 "     → 需要时执行：pip3 install rdagent && rdagent fin_quant\n"
                 "     → rdagent 首次运行时会自动构建 local_qlib:latest 镜像")
    except ImportError:
        fail("docker 包未安装（pip3 install docker）")
    except Exception as e:
        warn(f"Docker 未连接（{e}）\n"
             f"     → 请启动 Docker Desktop")


def main() -> None:
    print("=" * 60)
    print("  QuantByQlib 环境预检")
    print("=" * 60)

    check_python()
    check_packages()
    check_qlib_data()
    check_api_keys()
    check_docker()

    print("\n" + "=" * 60)
    print("  预检完成（⚠️ 为警告，不影响启动；❌ 为必须修复）")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
