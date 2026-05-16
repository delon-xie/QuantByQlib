"""
本地 Markdown 报告归档 (Report Writer)

将 AI 分析报告和每日摘要保存为结构化 MD 文件到本地目录。

目录结构：
  ~/Documents/美股交易日记/reports/   （可通过 REPORTS_DIR 环境变量覆盖）
    YYYYMMDD/
      {TICKER}_analysis.md            # 个股 AI 分析报告
      daily_summary.md                # 每日筛选摘要（市场状态 + Top-K 信号）

使用方式：
  writer = ReportWriter()
  writer.save_stock_report("AAPL", markdown_text)
  writer.save_daily_summary(signals_df, regime_info)
"""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import pandas as pd


class ReportWriter:
    """MD 报告写入器"""

    def __init__(self, reports_dir: Optional[Path] = None):
        if reports_dir is not None:
            self._root = Path(reports_dir)
        else:
            from services.output_paths import get_reports_dir
            self._root = get_reports_dir()

    # ── 个股 AI 分析报告 ──────────────────────────────────────

    def save_stock_report(
        self,
        ticker: str,
        markdown_content: str,
        trade_date: Optional[date] = None,
    ) -> Path:
        """
        保存个股 AI 分析报告。
        路径：reports/YYYYMMDD/{TICKER}_analysis.md
        若同日已存在，追加时间戳后缀而非覆盖。
        """
        d = trade_date or date.today()
        day_dir = self._root / d.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        base_path = day_dir / f"{ticker.upper()}_analysis.md"
        path = self._unique_path(base_path)

        header = self._report_header(ticker, d)
        path.write_text(header + markdown_content, encoding="utf-8")
        logger.info(f"[ReportWriter] 个股报告已保存：{path}")
        return path

    # ── 每日摘要 ──────────────────────────────────────────────

    def save_daily_summary(
        self,
        signals_df: Optional["pd.DataFrame"],
        regime_info: Optional[dict] = None,
        trade_date: Optional[date] = None,
        strategy_name: str = "",
    ) -> Path:
        """
        保存每日筛选摘要。
        路径：reports/YYYYMMDD/daily_summary.md
        """
        d = trade_date or date.today()
        day_dir = self._root / d.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        path = day_dir / "daily_summary.md"
        content = self._build_daily_summary(signals_df, regime_info, d, strategy_name)
        path.write_text(content, encoding="utf-8")
        logger.info(f"[ReportWriter] 每日摘要已保存：{path}")
        return path

    # ── 内部构建 ──────────────────────────────────────────────

    def _build_daily_summary(
        self,
        signals_df: Optional["pd.DataFrame"],
        regime_info: Optional[dict],
        d: date,
        strategy_name: str,
    ) -> str:
        import pandas as pd

        lines: list[str] = [
            f"# 美股每日交易摘要 — {d.strftime('%Y年%m月%d日')}",
            "",
        ]

        # 市场状态
        if regime_info:
            regime = regime_info.get("current_regime", "未知")
            regime_zh = {
                "recovery":    "复苏期",
                "expansion":   "扩张期",
                "overheating": "过热期",
                "recession":   "衰退期",
            }.get(regime, regime)
            spy_5d  = regime_info.get("spy_return_5d")
            spy_20d = regime_info.get("spy_return_20d")
            lines += [
                "## 市场状态（HMM 检测）",
                "",
                f"- **当前状态**：{regime_zh}",
            ]
            if spy_5d is not None:
                lines.append(f"- **SPY 5日预测收益**：{spy_5d*100:+.2f}%")
            if spy_20d is not None:
                lines.append(f"- **SPY 20日预测收益**：{spy_20d*100:+.2f}%")
            lines.append("")

        # 策略信号摘要
        if strategy_name:
            lines.append(f"## 策略信号（{strategy_name}）")
        else:
            lines.append("## 量化选股信号")
        lines.append("")

        if signals_df is None or (hasattr(signals_df, "empty") and signals_df.empty):
            lines.append("_今日无信号数据_")
        else:
            # 买入信号
            df = signals_df
            buy_col = next((c for c in ["信号", "signal", "direction"] if c in df.columns), None)
            if buy_col:
                buy_df = df[df[buy_col].str.contains("买|Buy|BUY", na=False)]
            else:
                buy_df = df

            lines.append(f"共筛选出 **{len(df)}** 只股票，其中买入信号 **{len(buy_df)}** 只。")
            lines.append("")

            # Top-K 表格
            show_cols_priority = ["股票", "symbol", "ticker", "信号", "Qlib评分", "score", "今日涨跌%", "change_pct"]
            show_cols = [c for c in show_cols_priority if c in df.columns]
            if not show_cols:
                show_cols = list(df.columns[:5])

            lines.append("| " + " | ".join(show_cols) + " |")
            lines.append("| " + " | ".join(["---"] * len(show_cols)) + " |")
            for _, row in df.head(20).iterrows():
                cells = []
                for col in show_cols:
                    val = row.get(col, "")
                    if isinstance(val, float):
                        cells.append(f"{val:.4f}" if abs(val) < 10 else f"{val:.2f}")
                    else:
                        cells.append(str(val))
                lines.append("| " + " | ".join(cells) + " |")

        lines += ["", f"---", f"_生成时间：{d.isoformat()} | QuantByQlib_"]
        return "\n".join(lines)

    def _report_header(self, ticker: str, d: date) -> str:
        return textwrap.dedent(f"""\
            # {ticker} 个股 AI 分析报告

            > **生成日期**：{d.strftime('%Y年%m月%d日')}
            > **分析工具**：QuantByQlib + Claude AI | DeepSeek AI
            > **免责声明**：本报告仅供参考，不构成投资建议。

            ---

        """)

    def _unique_path(self, base: Path) -> Path:
        """若文件已存在，添加时间戳后缀"""
        if not base.exists():
            return base
        from datetime import datetime
        ts = datetime.now().strftime("%H%M%S")
        return base.with_stem(f"{base.stem}_{ts}")
    
    def _latest_path(self, base: Path) -> Path:
        """获取类似文件最新的文件（基于修改时间）"""
        import re
        
        # 查找所有匹配的文件
        parent_dir = base.parent
        stem = base.stem.rstrip('_')
        
        # 查找所有相关文件
        related_files = []
        
        # 添加基础文件（如果存在）
        if base.exists():
            related_files.append(base)
        
        # 查找带时间戳的文件
        for file_path in parent_dir.glob(f"{stem}_*{base.suffix}"):
            # 检查文件名格式: stem_六位数字.suffix
            if file_path.suffix == base.suffix:
                name_without_ext = file_path.stem
                if name_without_ext.startswith(stem + '_'):
                    suffix_part = name_without_ext[len(stem) + 1:]
                    if len(suffix_part) == 6 and suffix_part.isdigit():
                        # 验证是有效的时间
                        hour = suffix_part[0:2]
                        minute = suffix_part[2:4]
                        second = suffix_part[4:6]
                        if hour.isdigit() and minute.isdigit() and second.isdigit():
                            if 0 <= int(hour) < 24 and 0 <= int(minute) < 60 and 0 <= int(second) < 60:
                                related_files.append(file_path)
        
        if not related_files:
            return base
        
        # 按修改时间排序，获取最新的文件
        related_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return related_files[0]
    
    def get_report(self,
        ticker: str,
        trade_date: Optional[date] = None,
    ) -> str:
        """
        读取个股 AI 分析报告。
        路径：reports/YYYYMMDD/{TICKER}_analysis.md
        若同日已存在，追加时间戳后缀而非覆盖。
        """
        d = trade_date or date.today()
        day_dir = self._root / d.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        base_path = day_dir / f"{ticker.upper()}_analysis.md"
        file_path = self._latest_path(base_path)

        path = Path(file_path) if isinstance(file_path, str) else file_path
    
        if not path.exists():
            return None
        
        if not path.is_file():
            return None
        
        try:
            # 尝试其他常见编码
            common_encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1', 'cp1252']
            
            for enc in common_encodings:
                try:
                    with open(path, 'r', encoding=enc) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
        except UnicodeDecodeError as e:
            return None
