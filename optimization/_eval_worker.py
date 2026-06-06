#!/usr/bin/env python
"""策略评估 Worker — 子进程隔离 qlib C 层崩溃"""
import json, sys, os, warnings
from pathlib import Path

warnings.filterwarnings('ignore')

inp = json.loads(sys.stdin.read())

# 设置工作目录
os.chdir(inp.get('project_root', str(Path.cwd())))

import pandas as pd
prices = pd.read_csv(inp['prices_file'], index_col=0, parse_dates=True)
universe = json.loads(Path(inp['universe_file']).read_text())

# 预初始化 qlib
try:
    from core.app_state import get_state
    from core.qlibhelper import qlib_safeinit
    state = get_state()
    qlib_data = Path(f"{Path.home()}/.qlib/qlib_data/{state.reg}_data")
    qlib_safeinit(str(qlib_data))
except Exception:
    pass

from optimization.strategy_executor import StrategyExecutor
from optimization.backtester import EnhancedBacktester

strategy = StrategyExecutor.create_strategy(inp['strategy_key'], **inp['params'])
result = strategy.run(universe)

bt = EnhancedBacktester(
    initial_capital=inp['initial_capital'],
    stop_loss_config={'fixed': inp['stop_loss_pct']},
)
bt_result = bt.run_signal_backtest(result.topk_tickers, prices)


def _sv(v):
    if v is None: return None
    if isinstance(v, (int, float, str, bool)): return v
    if hasattr(v, 'item'): return float(v)
    return None


m = bt_result['metrics']
e = bt_result.get('enhanced', {})

print(json.dumps({
    'metrics': {
        'sharpe_ratio': _sv(m.sharpe_ratio),
        'max_drawdown': _sv(m.max_drawdown),
        'total_return': _sv(m.total_return),
        'annual_return': _sv(m.annual_return),
        'volatility': _sv(m.volatility),
        'win_rate': _sv(m.win_rate),
        'alpha': _sv(m.alpha),
        'beta': _sv(m.beta),
    },
    'enhanced': {k: _sv(v) for k, v in e.items()},
}))
