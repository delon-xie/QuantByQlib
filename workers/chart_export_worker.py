"""
持仓 K 线图批量导出 Worker
对每支持仓股票生成 5日/日线/周线 三张 PNG，保存到指定目录
"""
from __future__ import annotations

from pathlib import Path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal


class ChartExportSignals(QObject):
    progress  = pyqtSignal(int, str)   # (pct, message)
    completed = pyqtSignal(str)        # 导出目录路径
    error     = pyqtSignal(str)


class ChartExportWorker(QRunnable):
    """
    批量导出 K 线图到 output_dir。

    Parameters
    ----------
    tickers               : 股票代码列表
    output_dir            : 主要保存目录（由用户通过文件对话框选择）
    also_export_to_journal: 同时将图表同步到「美股交易日记/pics/」（供 Claude 消费）
    """

    _PERIOD_PARAMS = {
        "zoom": dict(period="180d", interval="1d",  label="Zoom"),
        "day":  dict(period="130d", interval="1d",  label="Daily"),
        "week": dict(period="80wk", interval="1wk", label="Weekly"),
    }

    def __init__(self, tickers: list[str], output_dir: Path,
                 also_export_to_journal: bool = True):
        super().__init__()
        self.tickers                = tickers
        self.output_dir             = output_dir
        self.also_export_to_journal = also_export_to_journal
        self.signals                = ChartExportSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        from loguru import logger

        try:
            import yfinance as yf
            import mplfinance as mpf
            import matplotlib
            matplotlib.use("Agg")   # 无 GUI 后端，适合后台导出

            self.output_dir.mkdir(parents=True, exist_ok=True)

            import matplotlib.pyplot as plt
            for _font in ["PingFang HK", "PingFang SC", "STHeiti", "Heiti TC", "Arial Unicode MS"]:
                try:
                    plt.rcParams["font.family"] = _font
                    break
                except Exception:
                    continue
            plt.rcParams["axes.unicode_minus"] = False

            total = len(self.tickers) * len(self._PERIOD_PARAMS)
            done  = 0

            import matplotlib.font_manager as fm
            _cn_font = None
            for _fname in ["PingFang HK", "PingFang SC", "STHeiti", "Heiti TC", "Arial Unicode MS"]:
                try:
                    _fp = fm.FontProperties(family=_fname)
                    if fm.findfont(_fp, fallback_to_default=False):
                        _cn_font = _fp
                        plt.rcParams["font.family"] = _fname
                        break
                except Exception:
                    continue

            _MAV = {
                "zoom": (5, 10, 20),
                "day":  (5, 10, 20, 30),
                "week": (5, 10, 20, 30),
            }
            _TAIL = {
                # zoom：不截断，保留完整数据供 MA 计算，xlim 控制显示范围
                "day":  90,   # 展示最近90根
                "week": 60,   # 展示最近60根
            }

            style = mpf.make_mpf_style(
                base_mpf_style="charles",
                marketcolors=mpf.make_marketcolors(
                    up="#22C55E", down="#EF4444",
                    edge="inherit", wick="inherit",
                    volume={"up": "#22C55E88", "down": "#EF444488"},
                ),
                figcolor="#FFFFFF",
                gridcolor="#E2E4EA",
                gridstyle="--",
                mavcolors=["#F59E0B", "#3B82F6", "#8B5CF6", "#EC4899"],  # MA5橙/MA10蓝/MA20紫/MA30粉
            )

            for ticker in self.tickers:
                for period_key, params in self._PERIOD_PARAMS.items():
                    label = params["label"]
                    msg   = f"正在导出 {ticker} {label}..."
                    pct   = int(done / total * 95) if total > 0 else 0
                    self.signals.progress.emit(pct, msg)

                    try:
                        # 优先长桥，fallback yfinance
                        df = None
                        src = "yfinance"
                        try:
                            from data.longport_client import get_candlesticks, is_configured
                            if is_configured():
                                df = get_candlesticks(ticker, period_key)
                                if df is not None and not df.empty:
                                    src = "LongPort"
                        except Exception:
                            pass

                        if df is None or df.empty:
                            from core.app_state import get_state
                            from workers.binance_downloader import binance_download
                            reg = get_state().reg
                            if reg == "bt":
                                df = binance_download(
                                    ticker, progress=False, 
                                    auto_adjust=True,
                                    period=params["period"], 
                                    interval=params["interval"],
                                    threads=True,
                                )
                            else:
                                import yfinance as yf
                                # yfinance 一次下载所有 ticker，速度远快于逐一下载
                                # tickers_str = " ".join(tickers)
                                df = yf.download(
                                    ticker, progress=False, 
                                    auto_adjust=True,
                                    period=params["period"], 
                                    interval=params["interval"],
                                    threads=True,
                                )

                            if df is not None and not df.empty:
                                if hasattr(df.columns, "levels"):
                                    df.columns = df.columns.get_level_values(0)
                                df.index.name = "Date"
                                tail_n = _TAIL.get(period_key)
                                if tail_n:
                                    df = df.tail(tail_n)

                        if df is None or df.empty:
                            logger.warning(f"[图表导出] {ticker} {label} 无数据，跳过")
                            done += 1
                            continue

                        title = f"{ticker}  {label}  [{src}]"
                        from datetime import date
                        date_str = date.today().strftime("%Y%m%d")
                        fname     = f"{ticker}_{period_key}_{date_str}.png"
                        save_path = self.output_dir / fname

                        mav = _MAV.get(period_key, (5, 20))
                        fig, axes = mpf.plot(
                            df,
                            type="candle",
                            style=style,
                            title=title,
                            volume=True,
                            mav=mav,
                            returnfig=True,
                            figsize=(14, 9),    # 1400×900 @ dpi=100
                            tight_layout=True,
                        )
                        # zoom：MA 基于完整数据计算，xlim 限制显示最后20根（确保 MA20 正确显示）
                        # autoscale_view 消除成交量轴双层刻度
                        if period_key == "zoom":
                            n = len(df)
                            for ax in axes:
                                ax.set_xlim(n - 20 - 0.5, n - 0.5)
                                ax.autoscale_view()
                        if _cn_font:
                            for ax in fig.get_axes():
                                for lbl in ax.get_xticklabels() + ax.get_yticklabels():
                                    lbl.set_fontproperties(_cn_font)
                        fig.savefig(str(save_path), dpi=100, bbox_inches="tight")

                        # 同步到「美股交易日记/pics/」
                        if self.also_export_to_journal:
                            try:
                                from services.output_paths import get_pics_dir
                                journal_path = get_pics_dir() / fname
                                fig.savefig(str(journal_path), dpi=100, bbox_inches="tight")
                                logger.info(f"[图表导出] Journal 同步：{journal_path}")
                            except Exception as je:
                                logger.warning(f"[图表导出] Journal 同步失败：{je}")

                        plt.close(fig)
                        logger.info(f"[图表导出] 已保存：{save_path}")

                    except Exception as e:
                        logger.warning(f"[图表导出] {ticker} {label} 失败：{e}")

                    done += 1

            self.signals.progress.emit(100, f"导出完成，共 {done} 张图表")
            self.signals.completed.emit(str(self.output_dir))

        except Exception as e:
            from loguru import logger as _log
            _log.exception(f"[图表导出] Worker 异常：{e}")
            self.signals.error.emit(str(e))
