# optimization/visualizer.py
"""优化结果可视化 — matplotlib 图表"""
from __future__ import annotations

from typing import Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# 中文字体设置（macOS）
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class OptimizationVisualizer:
    """优化结果图表生成器"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_heatmap(
        self,
        all_results: list[dict],
        param_x: str,
        param_y: str,
        title: str = "Parameter Heatmap",
        save_path: Optional[str] = None,
    ):
        """二维参数得分散点图"""
        xv, yv, sc = [], [], []
        for r in all_results:
            if r["score"] <= -998:
                continue
            xv.append(r["params"].get(param_x))
            yv.append(r["params"].get(param_y))
            sc.append(r["score"])
        if not xv:
            return

        fig, ax = plt.subplots(figsize=(10, 8))
        pts = ax.scatter(xv, yv, c=sc, cmap="RdYlGn", s=100, edgecolors="k")
        plt.colorbar(pts, label="Score")
        ax.set_xlabel(param_x)
        ax.set_ylabel(param_y)
        ax.set_title(title)
        path = save_path or str(self.output_dir / f"heatmap_{param_x}_{param_y}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def plot_sensitivity(
        self,
        perturbation_results: dict,
        save_path: Optional[str] = None,
    ):
        """参数敏感度条形图"""
        params = perturbation_results.get("parameters", {})
        if not params:
            return
        names = list(params.keys())
        sens = [params[n]["sensitivity"] for n in names]
        colors = ["#e74c3c" if s > 0.1 else "#2ecc71" for s in sens]

        fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.5)))
        ax.barh(names, sens, color=colors)
        ax.set_xlabel("Sensitivity (score delta)")
        ax.set_title("Parameter Sensitivity")
        ax.axvline(x=0.05, color="gray", linestyle="--", alpha=0.5)

        path = save_path or str(self.output_dir / "sensitivity.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def plot_walkforward(
        self,
        wf_result: dict,
        save_path: Optional[str] = None,
    ):
        """Walk-Forward 结果概览"""
        windows = wf_result.get("windows", [])
        if not windows:
            return

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        x = range(len(windows))
        tscores = [w["train_score"] for w in windows]
        escores = [w["test_score"] for w in windows]

        axes[0].plot(x, tscores, "o-", label="Train", markersize=6)
        axes[0].plot(x, escores, "s-", label="Test", markersize=6)
        axes[0].set_title("Walk-Forward Scores")
        axes[0].set_xlabel("Window")
        axes[0].set_ylabel("Score")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        sharpes = [w.get("test_sharpe") or 0 for w in windows]
        axes[1].bar(x, sharpes, color="#3498db")
        axes[1].axhline(y=0, color="red", linestyle="--", alpha=0.5)
        axes[1].set_title("Test Sharpe per Window")
        axes[1].set_xlabel("Window")
        axes[1].set_ylabel("Sharpe")
        axes[1].grid(True, alpha=0.3)

        fig.tight_layout()
        path = save_path or str(self.output_dir / "walkforward.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
