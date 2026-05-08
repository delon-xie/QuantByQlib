"""
Qlib 数据下载 Worker
基于 QRunnable + WorkerSignals 在后台线程执行下载，不阻塞 UI
"""
from __future__ import annotations

import subprocess
import sys
import os
from typing import Optional
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger

# SunsetWolf 美股 Qlib 数据集（真正的美股日频数据，features/ 下为 AAPL/ MSFT/ 等）
SUNSETWOLF_US_DATA_URL = (
    "https://github.com/SunsetWolf/qlib_dataset/releases/download/v2/qlib_data_us_1d_latest.zip"
)
SUNSETWOLF_US_DATA_SIZE_MB = 450


class DownloadSignals(QObject):
    """Worker 信号（必须是独立 QObject，不能直接混入 QRunnable）"""
    progress    = pyqtSignal(int, str)    # (百分比 0-100, 状态文字)
    log_line    = pyqtSignal(str)         # 原始输出行
    completed   = pyqtSignal(bool, str)   # (成功?, 最终消息)
    error       = pyqtSignal(str)         # 错误消息


class QlibDownloadWorker(QRunnable):
    """
    Qlib 美股数据下载 Worker
    下载 SunsetWolf/qlib_dataset 美股日频 Qlib 数据（真正的美股，含 AAPL/MSFT 等）
    通过信号将进度/日志实时推送到 UI
    """

    def __init__(self, scope: str = "sp500", start_date: str = "2015-01-01"):
        super().__init__()
        self.scope = scope
        self.start_date = start_date
        self.signals = DownloadSignals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """请求取消（下次轮询时生效）"""
        self._cancelled = True

    @pyqtSlot()
    def run(self) -> None:
        """Worker 主逻辑（在线程池中执行）"""
        try:
            self._run_download()
        except Exception as e:
            #logger.exception(f"下载 Worker 异常：{e}")
            self.signals.error.emit(str(e))
            self.signals.completed.emit(False, str(e))

    def _run_download(self) -> None:
        from data.qlib_manager import build_download_command, QLIB_DATA_DIR, init_qlib

        # 确保目标目录存在
        QLIB_DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.signals.progress.emit(2, "正在构建下载命令...")
        self.signals.log_line.emit(f"[INFO] 开始下载 Qlib 美股数据，stock pool: {self.scope}")

        try:
            cmd = build_download_command(self.scope, self.start_date)
        except (FileNotFoundError, RuntimeError) as e:
            # 采集器脚本未找到 → 使用 SunsetWolf 美股预打包数据集
            self.signals.log_line.emit(f"[WARN] {e}")
            self.signals.log_line.emit("[INFO] 尝试下载 SunsetWolf 美股 Qlib 数据集...")
            self._fallback_download()
            return

        self.signals.progress.emit(5, "正在启动采集器...")
        self.signals.log_line.emit(f"[CMD] {' '.join(cmd[:4])} ...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ},
            )
        except Exception as e:
            self.signals.error.emit(f"无法启动采集器：{e}")
            self.signals.completed.emit(False, str(e))
            return

        # 读取输出行，解析进度
        total_stocks = 500 if self.scope == "sp500" else 5000
        downloaded = 0
        for line in iter(proc.stdout.readline, ""):
            if self._cancelled:
                proc.terminate()
                self.signals.log_line.emit("[INFO] 用户取消下载")
                self.signals.completed.emit(False, "已取消")
                return

            line = line.rstrip()
            if line:
                self.signals.log_line.emit(line)

            # 简单进度估算（根据输出行数）
            if any(kw in line for kw in ["Downloading", "downloading", "fetching", "GET"]):
                downloaded += 1
                pct = min(5 + int(downloaded / total_stocks * 85), 90)
                self.signals.progress.emit(pct, f"正在下载... ({downloaded}/{total_stocks})")

        proc.wait()

        if proc.returncode == 0 or proc.returncode is None:
            self.signals.progress.emit(95, "正在初始化 Qlib 数据...")
            self.signals.log_line.emit("[INFO] 数据下载完成，正在初始化 Qlib...")

            # 重新初始化 Qlib
            ok = init_qlib()
            if ok:
                self.signals.progress.emit(100, "✅ 初始化完成")
                self.signals.log_line.emit("[INFO] ✅ Qlib 初始化成功，可以开始量化选股")
                self.signals.completed.emit(True, "数据下载和初始化成功")
                # 通知事件总线
                try:
                    from core.event_bus import get_event_bus
                    get_event_bus().qlib_initialized.emit()
                    get_event_bus().qlib_data_downloaded.emit()
                except Exception:
                    pass
            else:
                self.signals.completed.emit(False, "数据下载完成但 Qlib 初始化失败，请检查数据完整性")
        else:
            msg = f"采集器退出码：{proc.returncode}"
            self.signals.log_line.emit(f"[ERROR] {msg}")
            self.signals.completed.emit(False, msg)

    def _fallback_download(self) -> None:
        """
        备用下载方式：下载 SunsetWolf/qlib_dataset 美股 Qlib 数据集
        真正的美股日频数据（features/ 下为 AAPL/ MSFT/ 等纯字母目录）
        约 450MB zip，解压后约 1.5GB
        """
        self._download_sunsetwolf_us_data()

    def _download_sunsetwolf_us_data(self) -> None:
        """
        下载 SunsetWolf/qlib_dataset 美股 Qlib 数据集并解压。
        目标目录始终为 ~/.qlib/qlib_data/（即 FIXED_TARGET_DIR）。
        zip 内层目录（如 qlib_data_us_1d_latest/）会被重命名为目标目录。
        """
        import tempfile
        import shutil
        from pathlib import Path
        from data.qlib_manager import init_qlib

        # 固定目标目录：始终是 ~/.qlib/qlib_data/，不依赖动态的 QLIB_DATA_DIR
        FIXED_TARGET_DIR = Path.home() / ".qlib" / "qlib_data"
        FIXED_PARENT_DIR = FIXED_TARGET_DIR.parent    # ~/.qlib/
        FIXED_TARGET_DIR.mkdir(parents=True, exist_ok=True)

        url = SUNSETWOLF_US_DATA_URL
        self.signals.log_line.emit(f"[INFO] 下载地址：{url}")
        self.signals.log_line.emit(f"[INFO] 文件大小：约 {SUNSETWOLF_US_DATA_SIZE_MB} MB，请耐心等待...")
        self.signals.progress.emit(5, f"正在下载美股 Qlib 数据集（约 {SUNSETWOLF_US_DATA_SIZE_MB} MB）...")

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "qlib_data_us.zip")

            # 下载
            self.signals.log_line.emit("[INFO] 开始下载到临时目录...")
            cmd_download = ["curl", "-L", "--progress-bar", "-o", zip_path, url]

            try:
                proc = subprocess.Popen(
                    cmd_download,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(proc.stdout.readline, ""):
                    if self._cancelled:
                        proc.terminate()
                        self.signals.completed.emit(False, "用户取消")
                        return
                    line = line.rstrip()
                    if line:
                        self.signals.log_line.emit(line)
                        if "%" in line:
                            try:
                                pct_str = [s for s in line.split() if "%" in s][0].replace("%", "")
                                pct = max(5, min(75, int(float(pct_str) * 0.70) + 5))
                                self.signals.progress.emit(pct, "正在下载美股数据集...")
                            except Exception:
                                pass
                proc.wait()
                if proc.returncode != 0:
                    self.signals.completed.emit(False, f"curl 下载失败（退出码 {proc.returncode}）")
                    return
            except FileNotFoundError:
                self.signals.log_line.emit("[INFO] curl 不可用，使用 Python urllib 下载...")
                self._download_with_urllib_fallback(url, zip_path)

            if self._cancelled:
                self.signals.completed.emit(False, "用户取消")
                return

            self.signals.log_line.emit("[INFO] 下载完成，正在解压...")
            self.signals.progress.emit(78, "正在解压数据包（约 2-3 分钟）...")

            # 解压到临时子目录，避免直接污染目标目录
            extract_tmp = Path(tmpdir) / "extracted"
            extract_tmp.mkdir()

            cmd_extract = ["unzip", "-o", zip_path, "-d", str(extract_tmp)]
            self.signals.log_line.emit(f"[CMD] unzip ... -d {extract_tmp}")

            try:
                proc = subprocess.Popen(
                    cmd_extract,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(proc.stdout.readline, ""):
                    if self._cancelled:
                        proc.terminate()
                        self.signals.completed.emit(False, "用户取消")
                        return
                    line = line.rstrip()
                    if line and "inflating" in line.lower():
                        self.signals.log_line.emit(line)
                proc.wait()
                if proc.returncode != 0:
                    self.signals.log_line.emit(f"[WARN] unzip 退出码 {proc.returncode}，尝试 Python zipfile...")
                    import zipfile
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(str(extract_tmp))
            except FileNotFoundError:
                self.signals.log_line.emit("[INFO] unzip 不可用，使用 Python zipfile 解压...")
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        total_files = len(zf.namelist())
                        for i, name in enumerate(zf.namelist()):
                            if self._cancelled:
                                self.signals.completed.emit(False, "用户取消")
                                return
                            zf.extract(name, str(extract_tmp))
                            if i % 500 == 0:
                                pct = 78 + int(i / total_files * 15)
                                self.signals.progress.emit(pct, f"解压中... {i}/{total_files}")
                except Exception as e:
                    self.signals.completed.emit(False, f"解压异常：{e}")
                    return
            except Exception as e:
                self.signals.completed.emit(False, f"解压异常：{e}")
                return

            self.signals.progress.emit(93, "检查解压结果...")

            # 找到解压后含 features/ 的子目录（zip 内层目录名不固定）
            US_DATA_ITEMS = ["features", "calendars", "instruments"]
            extracted_dir = None

            # 先看 extract_tmp 下有无直接的 features/（zip 无子目录结构）
            if (extract_tmp / "features").exists():
                extracted_dir = extract_tmp
            else:
                # zip 内有子目录，找第一个含 features/ 的
                for sub in extract_tmp.iterdir():
                    if sub.is_dir() and (sub / "features").exists():
                        extracted_dir = sub
                        self.signals.log_line.emit(f"[INFO] 找到解压目录：{sub.name}")
                        break

            if extracted_dir is None:
                dirs = [p.name for p in extract_tmp.iterdir() if p.is_dir()]
                self.signals.log_line.emit(f"[WARN] 未找到含 features/ 的目录，当前：{dirs}")
                self.signals.completed.emit(False, "解压结构异常，未找到 features/ 目录")
                return

            # 备份旧数据，将新数据的各子目录移入 FIXED_TARGET_DIR
            self.signals.log_line.emit(f"[INFO] 正在将数据写入 {FIXED_TARGET_DIR}...")
            for item_name in US_DATA_ITEMS:
                src = extracted_dir / item_name
                dst = FIXED_TARGET_DIR / item_name
                if not src.exists():
                    continue
                if dst.exists():
                    backup = FIXED_TARGET_DIR / f"{item_name}_backup"
                    if backup.exists():
                        shutil.rmtree(backup, ignore_errors=True)
                    dst.rename(backup)
                shutil.move(str(src), str(dst))
                self.signals.log_line.emit(f"[INFO] 已更新 {item_name}/")

        self.signals.progress.emit(96, "重新初始化 Qlib...")
        self.signals.log_line.emit("[INFO] 正在重新初始化 Qlib...")

        ok = init_qlib()
        if ok:
            self.signals.progress.emit(100, "✅ 下载完成")
            self.signals.log_line.emit("[INFO] ✅ 美股 Qlib 数据下载成功，可以开始量化选股")
            self.signals.completed.emit(True, "美股 Qlib 数据下载成功")
            try:
                from core.event_bus import get_event_bus
                get_event_bus().qlib_initialized.emit()
                get_event_bus().qlib_data_downloaded.emit()
            except Exception:
                pass
        else:
            self.signals.completed.emit(False, "数据解压完成但 Qlib 初始化失败，请检查目录结构")

    def _download_with_urllib_fallback(self, url: str, dest: str) -> None:
        """urllib fallback 下载"""
        import urllib.request
        self.signals.log_line.emit("[INFO] urllib 下载中（无进度），请等待...")

        def reporthook(count, block_size, total_size):
            if self._cancelled:
                raise InterruptedError("用户取消")
            if total_size > 0:
                pct = min(75, int(count * block_size / total_size * 70) + 5)
                self.signals.progress.emit(pct, "下载中...")

        urllib.request.urlretrieve(url, dest, reporthook=reporthook)


class QlibUpdateWorker(QRunnable):
    """
    Qlib 数据更新 Worker
    下载 SunsetWolf/qlib_dataset 最新美股 Qlib 数据集
    真正的美股日频数据（features/ 下为 AAPL/ MSFT/ 等），约 450MB
    """

    def __init__(self):
        super().__init__()
        self.signals = DownloadSignals()
        self._cancelled = False
        self._proc: Optional[subprocess.Popen] = None
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._run_update()
        except Exception as e:
            #logger.exception(f"更新 Worker 异常：{e}")
            self.signals.error.emit(str(e))
            self.signals.completed.emit(False, str(e))

    def _run_update(self) -> None:
        import tempfile
        import shutil
        from pathlib import Path
        from data.qlib_manager import init_qlib

        # 固定目标目录：始终是 ~/.qlib/qlib_data/
        FIXED_TARGET_DIR = Path.home() / ".qlib" / "qlib_data"
        FIXED_TARGET_DIR.mkdir(parents=True, exist_ok=True)

        url = SUNSETWOLF_US_DATA_URL
        self.signals.log_line.emit(f"[INFO] 下载 SunsetWolf 美股 Qlib 数据集...")
        self.signals.log_line.emit(f"[INFO] 下载地址：{url}")
        self.signals.log_line.emit(f"[INFO] 文件大小：约 {SUNSETWOLF_US_DATA_SIZE_MB} MB，请耐心等待...")
        self.signals.progress.emit(5, f"正在下载美股 Qlib 数据集（约 {SUNSETWOLF_US_DATA_SIZE_MB} MB）...")

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "qlib_data_us.zip")

            # 下载
            self.signals.log_line.emit("[INFO] 开始下载到临时目录...")
            cmd_download = ["curl", "-L", "--progress-bar", "-o", zip_path, url]

            try:
                self._proc = subprocess.Popen(
                    cmd_download,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(self._proc.stdout.readline, ""):
                    if self._cancelled:
                        self._proc.terminate()
                        self.signals.completed.emit(False, "用户取消")
                        return
                    line = line.rstrip()
                    if line:
                        self.signals.log_line.emit(line)
                        if "%" in line:
                            try:
                                pct_str = [s for s in line.split() if "%" in s][0].replace("%", "")
                                pct = max(5, min(75, int(float(pct_str) * 0.70) + 5))
                                self.signals.progress.emit(pct, "正在下载美股数据集...")
                            except Exception:
                                pass
                self._proc.wait()
                if self._proc.returncode != 0:
                    self.signals.completed.emit(False, f"curl 下载失败（退出码 {self._proc.returncode}）")
                    return
            except FileNotFoundError:
                self.signals.log_line.emit("[INFO] curl 不可用，使用 Python urllib 下载...")
                self._download_with_urllib(url, zip_path)

            if self._cancelled:
                self.signals.completed.emit(False, "用户取消")
                return

            self.signals.log_line.emit("[INFO] 下载完成，正在解压...")
            self.signals.progress.emit(78, "正在解压数据包（约 2-3 分钟）...")

            # 解压到临时子目录
            extract_tmp = Path(tmpdir) / "extracted"
            extract_tmp.mkdir()
            cmd_extract = ["unzip", "-o", zip_path, "-d", str(extract_tmp)]
            self.signals.log_line.emit(f"[CMD] unzip ... -d {extract_tmp}")

            try:
                self._proc = subprocess.Popen(
                    cmd_extract,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(self._proc.stdout.readline, ""):
                    if self._cancelled:
                        self._proc.terminate()
                        self.signals.completed.emit(False, "用户取消")
                        return
                    line = line.rstrip()
                    if line and "inflating" in line.lower():
                        self.signals.log_line.emit(line)
                self._proc.wait()
                if self._proc.returncode != 0:
                    self.signals.log_line.emit(f"[WARN] unzip 退出码 {self._proc.returncode}，尝试 Python zipfile...")
                    import zipfile
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(str(extract_tmp))
            except FileNotFoundError:
                self.signals.log_line.emit("[INFO] unzip 不可用，使用 Python zipfile 解压...")
                try:
                    import zipfile
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        total_files = len(zf.namelist())
                        for i, name in enumerate(zf.namelist()):
                            if self._cancelled:
                                self.signals.completed.emit(False, "用户取消")
                                return
                            zf.extract(name, str(extract_tmp))
                            if i % 500 == 0:
                                pct = 78 + int(i / total_files * 15)
                                self.signals.progress.emit(pct, f"解压中... {i}/{total_files}")
                except Exception as e:
                    self.signals.completed.emit(False, f"解压异常：{e}")
                    return
            except Exception as e:
                self.signals.completed.emit(False, f"解压异常：{e}")
                return

            self.signals.progress.emit(93, "检查解压结果...")
            self.signals.log_line.emit("[INFO] 解压完成，检查目录结构...")

            US_DATA_ITEMS = ["features", "calendars", "instruments"]
            extracted_dir = None

            if (extract_tmp / "features").exists():
                extracted_dir = extract_tmp
            else:
                for sub in extract_tmp.iterdir():
                    if sub.is_dir() and (sub / "features").exists():
                        extracted_dir = sub
                        self.signals.log_line.emit(f"[INFO] 找到解压目录：{sub.name}")
                        break

            if extracted_dir is None:
                dirs = [p.name for p in extract_tmp.iterdir() if p.is_dir()]
                self.signals.log_line.emit(f"[WARN] 未找到含 features/ 的目录，当前：{dirs}")
                self.signals.completed.emit(False, "解压结构异常，未找到 features/ 目录")
                return

            # 将各子目录移入 FIXED_TARGET_DIR
            self.signals.log_line.emit(f"[INFO] 正在将数据写入 {FIXED_TARGET_DIR}...")
            for item_name in US_DATA_ITEMS:
                src = extracted_dir / item_name
                dst = FIXED_TARGET_DIR / item_name
                if not src.exists():
                    continue
                if dst.exists():
                    backup = FIXED_TARGET_DIR / f"{item_name}_backup"
                    if backup.exists():
                        shutil.rmtree(backup, ignore_errors=True)
                    dst.rename(backup)
                shutil.move(str(src), str(dst))
                self.signals.log_line.emit(f"[INFO] 已更新 {item_name}/")

        self.signals.progress.emit(96, "重新初始化 Qlib...")
        self.signals.log_line.emit("[INFO] 正在重新初始化 Qlib...")

        ok = init_qlib()
        if ok:
            self.signals.progress.emit(100, "✅ 数据更新完成")
            self.signals.log_line.emit(
                "[INFO] ✅ 美股 Qlib 数据更新完成，现在可以使用完整的 Alpha158/360 量化模型"
            )
            self.signals.completed.emit(True, "美股 Qlib 数据更新成功")
            try:
                from core.event_bus import get_event_bus
                get_event_bus().qlib_initialized.emit()
                get_event_bus().qlib_data_downloaded.emit()
            except Exception:
                pass
        else:
            self.signals.completed.emit(False, "数据解压完成但 Qlib 初始化失败，请检查目录结构")

    def _download_with_urllib(self, url: str, dest: str) -> None:
        """urllib fallback 下载"""
        import urllib.request
        self.signals.log_line.emit("[INFO] urllib 下载中（无进度），请等待...")

        def reporthook(count, block_size, total_size):
            if self._cancelled:
                raise InterruptedError("用户取消")
            if total_size > 0:
                pct = min(75, int(count * block_size / total_size * 70) + 5)
                self.signals.progress.emit(pct, "下载中...")

        urllib.request.urlretrieve(url, dest, reporthook=reporthook)
