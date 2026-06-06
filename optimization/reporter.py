# optimization/reporter.py
"""优化报告生成 — Markdown 格式"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger


class OptimizationReporter:
    """优化报告生成器"""

    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            from services.output_paths import get_reports_dir
            self.output_dir = get_reports_dir() / "optimization"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, result: dict, charts_dir: Optional[str] = None) -> Path:
        """生成 Markdown 优化报告"""
        sk = result.get("strategy_key", "unknown")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"optimization_{sk}_{ts}.md"

        lines = [
            f"# 策略优化报告：{sk}",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**市场状态**: {result.get('market_regime', 'N/A')}",
            f"**数据范围**: {result.get('data_range', 'N/A')}",
            f"**股票池大小**: {result.get('universe_size', 'N/A')} 支",
            "", "---", "",
        ]

        # 最优参数
        opt = result.get("optimization", {})
        bp = opt.get("best_params", {})
        if bp:
            lines += ["## 1. 最优参数", "", "| 参数 | 最优值 |", "|------|--------|"]
            for k, v in bp.items():
                lines.append(f"| {k} | {v} |")
            lines += ["", f"**优化得分**: {_f(opt.get('best_score'))}", ""]

        # 性能指标
        bm = opt.get("best_metrics")
        if bm:
            lines += [
                "## 2. 最优性能指标", "",
                "| 指标 | 数值 |", "|------|------|",
                f"| 年化收益率 | {_fp(bm.annual_return)} |",
                f"| 总收益率 | {_fp(bm.total_return)} |",
                f"| 夏普比率 | {_f(bm.sharpe_ratio)} |",
                f"| 最大回撤 | {_fp(bm.max_drawdown)} |",
                f"| 胜率 | {_fp(bm.win_rate)} |",
                "",
            ]

        # Walk-Forward
        wf = result.get("walkforward", {})
        if wf and "error" not in wf:
            lines += [
                "## 3. Walk-Forward 验证", "",
                f"| 窗口数 | 训练均分 | 测试均分 | 测试Std |",
                f"|--------|----------|----------|---------|",
                f"| {wf.get('n_windows',0)} | {_f(wf.get('avg_train_score'))} | {_f(wf.get('avg_test_score'))} | {_f(wf.get('test_score_std'))} |",
                "",
            ]
            st = wf.get("param_stability", {})
            if st:
                lines += ["### 参数稳定性", "", "| 参数 | 均值 | Std | CV |", "|------|------|-----|----|"]
                for nm, v in st.items():
                    lines.append(f"| {nm} | {_f(v['mean'])} | {_f(v['std'])} | {_f(v['cv'])} |")
                lines.append("")

        # 蒙特卡洛
        mc = result.get("monte_carlo", {})
        if mc:
            lines += [
                "## 4. 蒙特卡洛模拟", "",
                f"| 模拟次数 | 均分 | Std | P5 | P95 | 通过 |",
                f"|----------|------|-----|----|-----|------|",
                f"| {mc.get('n_simulations',0)} | {_f(mc.get('score_mean'))} | {_f(mc.get('score_std'))} | {_f(mc.get('score_p5'))} | {_f(mc.get('score_p95'))} | {'✅' if mc.get('pass_threshold') else '❌'} |",
                "",
            ]

        # 参数敏感性
        pert = result.get("perturbation", {})
        params = pert.get("parameters", {})
        if params:
            lines += [
                "## 5. 参数敏感性", "",
                "| 参数 | 基准值 | 敏感度 | 评估 |",
                "|------|--------|--------|------|",
            ]
            for nm, info in params.items():
                s = info.get("sensitivity", 0)
                a = "🔴高" if s > 0.1 else ("🟡中" if s > 0.05 else "🟢稳")
                lines.append(f"| {nm} | {info.get('base_value','-')} | {_f(s)} | {a} |")
            lines.append("")

        # 建议
        lines += ["## 6. 建议", ""]
        for r in self._recommendations(result):
            lines.append(f"- {r}")
        lines.append("")

        # 图表
        if charts_dir:
            lines += [
                "## 7. 图表",
                f"![敏感度]({charts_dir}/sensitivity.png)",
                f"![Walk-Forward]({charts_dir}/walkforward.png)",
                "",
            ]

        report = "\n".join(lines)
        path.write_text(report, encoding="utf-8")
        logger.info(f"[Reporter] 报告: {path}")
        return path

    def _recommendations(self, result: dict) -> list[str]:
        r = []
        wf = result.get("walkforward", {})
        if wf.get("test_score_std", 0) > 0.15:
            r.append("⚠️ 测试得分波动大（>0.15），建议缩小参数范围。")
        else:
            r.append("✅ 参数在 Walk-Forward 中表现稳定。")

        pert = result.get("perturbation", {})
        if pert.get("most_sensitive"):
            r.append(f"🔍 最敏感参数: **{pert['most_sensitive']}**，建议设窄区间。")

        mc = result.get("monte_carlo", {})
        if not mc.get("pass_threshold", False):
            r.append("⚠️ 蒙特卡洛未通过稳健性阈值（mean<0.3）。")

        score = result.get("optimization", {}).get("best_score", 0)
        if score < 0.3:
            r.append("❌ 得分<0.3，建议重新审视策略逻辑。")
        elif score < 0.5:
            r.append("⚡ 得分 0.3~0.5，有提升空间。")
        else:
            r.append("✅ 得分>0.5，策略质量良好。")
        return r


def _f(v) -> str:
    if v is None: return "N/A"
    if isinstance(v, float): return f"{v:.4f}"
    return str(v)


def _fp(v) -> str:
    if v is None: return "N/A"
    return f"{float(v)*100:.2f}%"
