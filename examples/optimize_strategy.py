#!/usr/bin/env python
# examples/optimize_strategy.py
"""
策略优化 CLI 入口

Usage:
    python examples/optimize_strategy.py --strategy early_trend
    python examples/optimize_strategy.py --strategy golden_cross --start 2022-01-01
    python examples/optimize_strategy.py --strategy ma10 --bayesian
    python examples/optimize_strategy.py --all
"""
import sys
import argparse
import multiprocessing
# 必须在任何 C 扩展加载前设置 spawn，避免 conda 环境下的 fork segfault
multiprocessing.set_start_method('spawn', force=True)

import faulthandler
faulthandler.enable()

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="策略参数优化工具")
    parser.add_argument("--strategy", type=str, default="early_trend",
                        choices=["early_trend", "golden_cross", "ma10", "trendline_breakout"])
    parser.add_argument("--all", action="store_true", help="优化所有策略")
    parser.add_argument("--start", type=str, default="2023-01-01")
    parser.add_argument("--bayesian", action="store_true")
    parser.add_argument("--no-wf", action="store_true")
    parser.add_argument("--no-robustness", action="store_true")
    args = parser.parse_args()

    from optimization.config import STRATEGY_PARAMS_MAP, OptimizationConfig
    from optimization.controller import OptimizationController
    from optimization.reporter import OptimizationReporter
    from loguru import logger

    strategies = (
        ["early_trend", "golden_cross", "ma10", "trendline_breakout"]
        if args.all else [args.strategy]
    )

    for strat in strategies:
        logger.info(f"{'='*60}\n  开始优化: {strat}\n{'='*60}")

        config = OptimizationConfig(
            strategy_key=strat,
            param_specs=STRATEGY_PARAMS_MAP[strat],
            start_date=args.start,
            bayesian_enabled=args.bayesian,
            walkforward_enabled=not args.no_wf,
            robustness_enabled=not args.no_robustness,
        )

        result = OptimizationController(config).run()

        reporter = OptimizationReporter()
        report_path = reporter.generate(result)

        # 可选：图表需要 matplotlib
        try:
            from optimization.visualizer import OptimizationVisualizer
            vis = OptimizationVisualizer(report_path.parent / f"charts_{strat}")
            opt = result.get("optimization", {})
            all_res = opt.get("all_results", [])
            if all_res:
                params = list(all_res[0]["params"].keys())
                if len(params) >= 2:
                    vis.plot_heatmap(all_res, params[0], params[1], title=f"{strat}")
            if "perturbation" in result:
                vis.plot_sensitivity(result["perturbation"])
            if "walkforward" in result:
                vis.plot_walkforward(result["walkforward"])
        except Exception:
            pass

        logger.info(f"  报告: {report_path}")

    logger.info("全部优化完成！")


if __name__ == "__main__":
    main()
