#!/usr/bin/env python3
"""
Qlib RD-Agent 因子发现启动脚本
支持多种 AI 模型：Anthropic, OpenAI, DeepSeek
Qlib因子回测
"""
from typing import List, Tuple, Dict, Any, Callable
import pandas as pd
import numpy as np
import sys
import re
from pathlib import Path

import os
import sys
import logging
from loguru import logger
from typing import Optional
from core.qlibhelper import qlib_safeinit, _get_test_instruments

# 配置日志
logger.add("logs/factor_discovery.log", rotation="100 MB", retention="10 days")

def prepare_factor_signal_for_backtest(factor_df, factor_name, normalize=True):
    """
    将因子数据转换为回测策略需要的信号格式
    
    Args:
        factor_df: 从 D.features 获取的因子数据
        factor_name: 因子名称
        normalize: 是否进行截面标准化
    
    Returns:
        signal_df: 格式为 MultiIndex (datetime, instrument) 的信号DataFrame
    """
    logger.info("="*60)
    logger.info("开始准备信号数据")
    logger.info(f"输入数据形状: {factor_df.shape}")
    logger.info(f"因子名称: {factor_name}")
    
    # 检查因子列是否存在
    if factor_name not in factor_df.columns and len(factor_df.columns) == 1:
        # 如果只有一列，使用该列
        factor_name = factor_df.columns[0]
        logger.info(f"使用单列因子: {factor_name}")
    
    if factor_name not in factor_df.columns:
        raise ValueError(f"因子 {factor_name} 不在数据中。可用列: {factor_df.columns.tolist()}")
    
    # 处理不同的数据格式
    if isinstance(factor_df.index, pd.MultiIndex):
        # 已经是 MultiIndex
        signal_df = factor_df[[factor_name]].copy()
        logger.info("数据已经是MultiIndex格式")
        
    elif factor_df.index.nlevels > 1:
        # 多层索引
        signal_df = factor_df[[factor_name]].copy()
        
    elif 'datetime' in factor_df.columns and 'instrument' in factor_df.columns:
        # 有 datetime 和 instrument 列
        signal_df = factor_df.set_index(['datetime', 'instrument'])[[factor_name]].copy()
        
    elif factor_df.columns.name == 'instrument' and factor_df.index.name == 'datetime':
        # 宽格式：索引是datetime，列是instrument
        signal_df = factor_df.stack().to_frame(factor_name)
        signal_df.index.names = ['datetime', 'instrument']
        
    else:
        # 尝试推断
        if pd.api.types.is_datetime64_any_dtype(factor_df.index):
            # 索引是datetime，列可能是instrument
            signal_df = factor_df.stack().to_frame(factor_name)
            signal_df.index.names = ['datetime', 'instrument']
        else:
            raise ValueError(f"无法识别数据格式。索引: {factor_df.index}, 列: {factor_df.columns}")
    
    # 重命名列
    signal_df.columns = ['score']
    
    # 转换数据类型
    signal_df['score'] = pd.to_numeric(signal_df['score'], errors='coerce')
    
    # 移除NaN
    before_len = len(signal_df)
    signal_df = signal_df.dropna()
    after_len = len(signal_df)
    logger.info(f"移除NaN: {before_len - after_len} 行 (保留 {after_len} 行)")
    
    if after_len == 0:
        raise ValueError("信号数据全部为NaN")
    
    # 截面标准化
    if normalize:
        logger.info("执行截面标准化...")
        
        def normalize_group(s):
            if len(s) > 1 and s.std() > 0:
                return (s - s.mean()) / s.std()
            elif len(s) > 0:
                return s - s.mean()
            return s
        
        signal_df['score'] = signal_df.groupby(level='datetime')['score'].transform(normalize_group)
    
    # 验证数据格式
    required_index_names = ['datetime', 'instrument']
    actual_names = signal_df.index.names
    
    for i, req in enumerate(required_index_names):
        if actual_names[i] != req:
            logger.warning(f"索引名不匹配: 期望 '{req}'，实际 '{actual_names[i]}'，将重命名")
            new_names = list(actual_names)
            new_names[i] = req
            signal_df.index.names = new_names
    
    # 数据统计
    dates = signal_df.index.get_level_values('datetime')
    instruments = signal_df.index.get_level_values('instrument')
    
    logger.info(f"最终信号数据形状: {signal_df.shape}")
    logger.info(f"时间范围: {dates.min()} 到 {dates.max()}")
    logger.info(f"交易日数: {dates.nunique()}")
    logger.info(f"股票数量: {instruments.nunique()}")
    logger.info(f"信号统计:")
    logger.info(f"  均值: {signal_df['score'].mean():.4f}")
    logger.info(f"  标准差: {signal_df['score'].std():.4f}")
    logger.info(f"  最小值: {signal_df['score'].min():.4f}")
    logger.info(f"  最大值: {signal_df['score'].max():.4f}")
    logger.info(f"  NaN数量: {signal_df['score'].isna().sum()}")
    logger.info("="*60)
    
    return signal_df

def setup_ai_client(provider: str = "auto"):
    """
    根据环境变量设置 AI 客户端
    
    Args:
        provider: auto|anthropic|openai|deepseek
    """
    available_providers = []
    
    # 检查可用的 API Key
    if os.getenv("ANTHROPIC_API_KEY"):
        available_providers.append("anthropic")
    if os.getenv("OPENAI_API_KEY"):
        available_providers.append("openai")
    if os.getenv("DEEPSEEK_API_KEY"):
        available_providers.append("deepseek")
    
    logger.info(f"Available AI providers: {available_providers}")
    
    if not available_providers:
        logger.warning("No AI API keys found! Factor discovery will use local models only.")
        return None
    
    # 自动选择优先级
    if provider == "auto":
        # 优先级：DeepSeek > Anthropic > OpenAI
        for pref in ["deepseek", "anthropic", "openai"]:
            if pref in available_providers:
                provider = pref
                break
    
    try:
        if provider == "deepseek":
            from openai import OpenAI
            client = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com/v1"
            )
            logger.info("DeepSeek client initialized")
            return {"client": client, "provider": "deepseek", "model": "deepseek-chat"}
            
        elif provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            logger.info("Anthropic client initialized")
            return {"client": client, "provider": "anthropic", "model": "claude-3-5-sonnet-20241022"}
            
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            logger.info("OpenAI client initialized")
            return {"client": client, "provider": "openai", "model": "gpt-4-turbo"}
            
    except ImportError as e:
        logger.error(f"Failed to import {provider} client: {e}")
    except Exception as e:
        logger.error(f"Error initializing {provider} client: {e}")
    
    return None

def prepare_signal_for_backtest(factor_df, factor_name):
    # 取出因子列
    if factor_name in factor_df.columns:
        signal_df = factor_df[[factor_name]].copy()
    else:
        signal_df = factor_df.iloc[:, [0]].copy()
    signal_df.columns = ['score']

    # 确保索引是 MultiIndex (datetime, instrument)
    if not isinstance(signal_df.index, pd.MultiIndex):
        # 如果不是 MultiIndex，强制转换
        if 'datetime' in signal_df.columns and 'instrument' in signal_df.columns:
            signal_df = signal_df.set_index(['datetime', 'instrument'])
        else:
            raise ValueError("signal_df 必须是 MultiIndex (datetime, instrument)")

    # 确保 dtype 正确
    signal_df['score'] = pd.to_numeric(signal_df['score'], errors='coerce')

    # 去掉 NaN
    signal_df = signal_df.dropna()

    # 标准化因子值
    if signal_df['score'].std() > 0:
        signal_df['score'] = (signal_df['score'] - signal_df['score'].mean()) / signal_df['score'].std()

    return signal_df

import argparse
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Factor discovery")
    parser.add_argument(
        "--provider",
        type=str,
        required=True,
        help="ai agents name"
    )
    parser.add_argument(
        "--reg",
        type=str,
        required=True,
        help="registry or region parameter"
    )
    args = parser.parse_args()

    print("Received provider:", args.provider)
    print("Received reg:", args.reg)
    logger.info("Starting Qlib RD-Agent Factor Discovery")
    
    # =====================
    # 1. 初始化 Qlib
    # =====================
    try:
        import qlib
        from core.qlibhelper import get_state
        from qlib.config import REG_CN
        from core.app_state import get_state
        
        # 初始化 Qlib
        homePath = Path.home()
        provider_uri = os.getenv("QLIB_DATA_URI", f"{homePath}/.qlib/qlib_data/{args.reg}_data")
        from qlib.config import C
        #C.set({"joblib_backend", "sequential"})
        #C["joblib_backend"] = "sequential"
        qlib_safeinit(provider_uri)
        logger.info(f"Qlib initialized with provider_uri: {provider_uri}")
        
    except Exception as e:
        logger.error(f"Failed to initialize Qlib: {e}")
        sys.exit(1)
    
    # =====================
    # 2. 设置 AI 客户端
    # =====================
    ai_client_info = setup_ai_client(args.provider)
    
    if not ai_client_info:
        logger.error("No AI client available, exit.")
        sys.exit(1)
    
    logger.info(f"Using AI provider: {ai_client_info['provider']}")


    # =====================
    # 3. 使用AI 生成因子描述
    # =====================
    
    prompt = """
You are a quantitative researcher.
Please generate ONE valid Qlib alpha factor expression.

Requirements:
- Use only Qlib built-in operators: $close, $open, $high, $low, $volume, $amount
- Operators allowed: Ref, Mean, Std, Rank, Correlation, TsMax, TsMin, Log, Abs
- Output format:
FACTOR_NAME: <name>
EXPR: <qlib expression>

You are generating factors for Qlib.

IMPORTANT RULES (MUST FOLLOW):

1. ONLY use Qlib built-in operators.
   Supported operators include:
   - Ref(x, d)
   - Mean(x, d)
   - Std(x, d)
   - Sum(x, d)
   - Return(x, d)
   - Delta(x, d)
   - Mul(x, y)
   - Div(x, y)
   - TsMax(x, d)
   - TsMin(x, d)

2. NEVER use these patterns:
   - $close * $volume   ❌
   - $close / $volume   ❌
   - $close + $open     ❌
   - Rank(x)             ❌
   - ZScore(x)           ❌
   - Corr(x, y, d)       ❌

3. All expressions MUST preserve daily frequency.
   If freq is lost, the factor will crash.

4. Output format MUST be:

FACTOR_NAME: <name>
EXPR: <valid Qlib expression>

Example:

FACTOR_NAME: Volume_Price_Trend_5d
EXPR: Mean(Mul($close, $volume), 5) / Mean($close, 5)

Error Example:
FACTOR_NAME: Momentum_10d
EXPR: Ref($close, -10) / $close
EXPR: $close * $volume
EXPR: $close / $volume
EXPR: $close + $open
EXPR: Mean($close * $volume, 5) / Mean($close, 5)

IMPORTANT:
- Only use basic operators: Ref, Mean, Std, Sum, Return, Delta
- DO NOT use Rank, ZScore, Corr, Cov
- The expression must preserve daily frequency

DO NOT nest Return() inside other operators.

Instead:
1. Compute Return() separately
2. Apply Div / Mul / Rank in pandas
"""

    try:
        response = ai_client_info["client"].chat.completions.create(
            model=ai_client_info["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        ai_text = response.choices[0].message.content
        logger.info(f"AI raw output:\n{ai_text}")

    except Exception as e:
        logger.warning(f"AI query failed: {e}")
        sys.exit(1)
    
    # =====================
    # 4. 解析 AI 输出
    # =====================
    # 解析因子信息
    #factor_name, factor_expr = parse_factor_info(ai_text)
    import re

    name_match = re.search(r"FACTOR_NAME:\s*(.+)", ai_text)
    expr_match = re.search(r"EXPR:\s*(.+)", ai_text)

    if not name_match or not expr_match:
        logger.error("Failed to parse AI factor output")
        sys.exit(1)

    factor_name = name_match.group(1).strip()
    factor_expr = expr_match.group(1).strip()
    
    logger.info(f"解析因子信息成功:")
    logger.info(f"  名称: {factor_name}")
    logger.info(f"  表达式: {factor_expr}")

    logger.info(f"Parsed factor -> name={factor_name}, expr={factor_expr}")

    # =====================
    # 5. 构造 Qlib 因子
    # =====================
    from qlib.data import D

    try:
        df = D.features(
            instruments=_get_test_instruments(),
            fields=[factor_expr],
            start_time="20180101",
            end_time="20221231",
        ).dropna()

        df.columns = [factor_name]
        logger.info(f"Factor data shape: {df.shape}")

    except Exception as e:
        logger.error(f"Factor evaluation failed: {e}")
        sys.exit(1)
    
    # =====================
    # 6. 简单回测（IC / 多空收益）
    # =====================
    from qlib.contrib.strategy import TopkDropoutStrategy
    from qlib.contrib.evaluate import backtest_daily

    strategy_config = {
        "topk": 50,
        "n_drop": 5,
    }

    instruments = _get_test_instruments()
    backtest_config = {
        "start_time": "2019-01-01",
        "end_time": "2022-12-31",
        "account": 100000,  # 初始资金
        "benchmark": instruments[0],
        "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
    }
    
    try:
        # 创建策略
        strategy = TopkDropoutStrategy(
            signal=df[[factor_name]],
            topk=20,
            n_drop=5,
            only_tradable=True
        )
        
        portfolio_metric, indicator = backtest_daily(
            start_time=backtest_config["start_time"],
            end_time=backtest_config["end_time"],
            strategy=strategy,
            account=backtest_config["account"],
            benchmark=backtest_config["benchmark"],
        )
        
        # 输出回测结果
        if portfolio_metric is not None and not portfolio_metric.empty:
            logger.info("回测完成!")
            logger.info(f"最终账户价值: {portfolio_metric.iloc[-1]['value']:.2f}")
            
            # 计算关键指标
            days = (portfolio_metric.index[-1] - portfolio_metric.index[0]).days
            if days > 0:
                total_return = portfolio_metric['return'].sum()
                annual_return = (1 + total_return) ** (252 / days) - 1
                
                print(f"\n{'='*60}")
                print("回测结果汇总")
                print(f"{'='*60}")
                print(f"回测期间: {backtest_config['start_time']} 到 {backtest_config['end_time']}")
                print(f"初始资金: {backtest_config['account']:,.2f}")
                print(f"最终价值: {portfolio_metric.iloc[-1]['value']:,.2f}")
                print(f"总收益率: {total_return:.2%}")
                print(f"年化收益率: {annual_return:.2%}")
                
                if indicator is not None:
                    if 'sharpe' in indicator:
                        print(f"夏普比率: {indicator['sharpe']:.3f}")
                    if 'mdd' in indicator:
                        print(f"最大回撤: {indicator['mdd']:.2%}")
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        sys.exit(1)

    logger.info("Factor discovery pipeline completed ✅")

    # 这里添加你的因子发现逻辑
    # logger.info("Factor discovery agent ready")
    
    # 保持容器运行（根据实际需要调整）
    # import time
    # while True:
    #     time.sleep(3600)  # 每小时代码逻辑

if __name__ == "__main__":
    main()