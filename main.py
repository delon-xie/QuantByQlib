"""
QuantByQlib 应用入口
美股量化辅助决策平台
"""
import sys
import os
from pathlib import Path
from core.qlibhelper import _check_qlib_init
os.environ["LOKY_MAX_DEPTH"] = "1"


# for WebEngine
# ========== 第1步：必须放在最前面 ==========
# 设置环境变量
os.environ["QT_QPA_PLATFORM"] = "cocoa"  # macOS
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--single-process"  # 解决共享上下文问题
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"  # 禁用 sandbox，解决页面加载失败问题

# 导入 QtCore 并设置属性
from PyQt6.QtCore import QCoreApplication, Qt
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


# ── 确保项目根目录在 Python 路径中 ──────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 加载 .env 环境变量（API Keys 等）────────────────────────
def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            # 手动解析
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()

# ── 初始化日志系统 ───────────────────────────────────────────
from utils.logger import setup_logger, logger
setup_logger()

# ── 预导入 PyTorch（必须在主线程完成，避免子线程首次 import 触发 GIL 死锁）
try:
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    logger.debug(f"PyTorch {torch.__version__} 预加载完成（主线程）")
except Exception as _torch_err:
    logger.warning(f"PyTorch 预加载失败（深度学习策略将不可用）：{_torch_err}")

# ── 启动 Qt 应用 ─────────────────────────────────────────────
def main() -> int:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    
    # 1. 设置环境变量
    os.environ["QT_QPA_PLATFORM"] = "cocoa"  # macOS
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

    # 2. 设置 WebEngine 共享上下文
    from PyQt6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    from core.app_state import get_state
    reg_name = get_state().reg_name

    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("QuantByQlib")
    app.setApplicationDisplayName("QuantByQlib — 美股量化辅助决策平台")
    app.setOrganizationName("QuantByQlib")

    # ── 应用全局样式表 ──────────────────────────────────────
    from ui.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    # ── 初始化事件总线（QObject 必须在 QApplication 之后创建）
    from core.event_bus import get_event_bus
    bus = get_event_bus()

    # ── 确保数据目录存在 ────────────────────────────────────
    data_dir = Path.home() / ".quantbyqlib"
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    (data_dir / "rdagent_output").mkdir(parents=True, exist_ok=True)

    # ── 创建并显示主窗口 ─────────────────────────────────────
    from ui.main_window import MainWindow
    from PyQt6.QtCore import QTimer
    window = MainWindow(app)
    window.show()

    # ── 检测 Qlib 初始化状态（延迟到事件循环后，确保主窗口信号连接就绪）
    QTimer.singleShot(50, lambda: _check_qlib_init(bus))

    logger.info("QuantByQlib 启动完成")
    bus.status_message.emit("QuantByQlib 已就绪")

    return app.exec()

if __name__ == "__main__":
    import faulthandler

    # --Qt异常捕捉 ─────────────────────────────────────────────
    faulthandler.enable()
    faulthandler.enable(file=open("crash.log", "a"), all_threads=True)
    sys.exit(main())
