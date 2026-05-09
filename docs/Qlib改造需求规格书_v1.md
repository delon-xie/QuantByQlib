# Qlib 系统改造需求规格书 v1.0

**版本**：v1.0
**日期**：2026-03-18
**定位**：将 Qlib 定位为独立的**数据与信号供应者**，为 Claude 定时任务系统提供完整的结构化数据支持。

---

## 一、系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                      Qlib 数据供应层                          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  图表生成器   │  │  信号生成器   │  │   分析报告生成器   │   │
│  │ (已实现 ✅)  │  │ (需规范化)   │  │   (待实现 🆕)     │   │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘   │
│         │                │                   │               │
└─────────┼────────────────┼───────────────────┼───────────────┘
          │                │                   │
          ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              美股交易日记/ 文件系统（共享接口层）               │
│                                                             │
│  pics/          signals/        regime/      backtest/      │
│  {图表文件}      {信号CSV}       {政体JSON}   {绩效JSON}     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Claude 定时任务系统（分析消费层）                  │
│                                                             │
│  daily-trading-analysis    weekly-quant-screening           │
│  monthly-macro-review      quarterly-factor-discovery        │
│                                                             │
│  统一通过 qlib-data-provider SKILL 读取数据                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、现有功能确认（已实现，需规格确认）

### F1：持仓图表生成

**状态**：✅ 已实现
**触发时机**：每个交易日收盘后自动运行
**输入**：当前持仓股票列表（从 Longbridge 获取或手动指定）

**输出文件**：
```
美股交易日记/pics/{TICKER}_{type}_{YYYYMMDD}.png
```

| type   | 内容      | K线数量    | 均线                 |
| ------ | ------- | ------- | ------------------ |
| `week` | 周线图     | 60周     | MA5/MA10/MA20/MA30 |
| `day`  | 日线图     | 90日     | MA5/MA10/MA20/MA30 |
| `zoom` | 近期放大日线图 | 最近20根日线 | MA5/MA10/MA20      |

**颜色规范**（须严格遵守）：
- MA5 = 琥珀色（`#FFA500` / amber/orange）
- MA10 = 蓝色（`#1E90FF`）
- MA20 = 紫色（`#9370DB`）
- MA30 = 粉色（`#FF69B4`）
- K线：阳线绿色，阴线红色
- 成交量柱：与K线颜色对应

**需求确认事项**：
- [ ] 确认 zoom 图的 MA 数值基于完整历史数据计算（非仅20根计算），避免失真
- [ ] 确认每日生成后文件名日期为交易日日期（非运行日期）
- [ ] 异常处理：股票停牌/数据缺失时生成错误标记文件或跳过

---

## 三、新增功能需求

### F2：策略信号 CSV 标准化导出 🆕

**优先级**：P0（所有定时任务均依赖）
**触发时机**：与图表生成同步，每个交易日收盘后运行

**输出目录**：
```
美股交易日记/signals/
```

**三个策略信号文件**：

#### Strategy 1 — LSTM 长期选股信号
```
文件名：signals/strategy1_{YYYYMMDD}.csv
```
- 模型：LSTM，训练窗口 504 日
- 特征集：Alpha158
- 选股范围：全市场（或指定股票池）
- 用途：正股长期持仓主信号

#### Strategy 2 — GRU 短期动量信号
```
文件名：signals/strategy2_{YYYYMMDD}.csv
```
- 模型：GRU，训练窗口 126 日
- 选股范围：Top30 动量股
- 用途：**仅用于期权时机判断**（是否出现在 BUY 榜 = 短期上行动量激活）
- 注意：信号稀疏是设计特性，不出现代表无激进动量信号

#### Strategy 3 — LightGBM + RD-Agent 因子信号
```
文件名：signals/strategy3_{YYYYMMDD}.csv
```
- 模型：LightGBM，特征由 RD-Agent 自动发现
- 选股范围：全市场（或指定股票池）
- 用途：正股选股辅助信号，与策略1交叉验证

**统一 CSV Schema**：
```csv
symbol,score,direction,rank,signal_strength,universe_size,strategy_id,date
NVDA,0.852,BUY,1,strong,500,strategy1,2026-03-18
MSFT,0.731,BUY,2,moderate,500,strategy1,2026-03-18
GOOG,0.612,BUY,3,moderate,500,strategy1,2026-03-18
PLTR,0.124,NEUTRAL,47,weak,500,strategy1,2026-03-18
VLO,-0.203,SELL,480,moderate,500,strategy1,2026-03-18
```

**字段说明**：

| 字段              | 类型     | 说明                                |
| --------------- | ------ | --------------------------------- |
| symbol          | string | 股票代码（大写）                          |
| score           | float  | 模型预测分数（-1.0 到 1.0）                |
| direction       | enum   | BUY / NEUTRAL / SELL              |
| rank            | int    | 全股票池排名（1=最强）                      |
| signal_strength | enum   | strong / moderate / weak          |
| universe_size   | int    | 本次评分的总股票数量                        |
| strategy_id     | string | strategy1 / strategy2 / strategy3 |
| date            | date   | 信号日期（YYYY-MM-DD）                  |

**Direction 阈值建议**：
- score > 0.5 → BUY + strong
- score 0.2~0.5 → BUY + moderate
- score -0.2~0.2 → NEUTRAL
- score -0.5~-0.2 → SELL + moderate
- score < -0.5 → SELL + strong

**额外要求**：
- [ ] 每个文件只包含当日信号（不追加历史）
- [ ] 当日无信号时生成空 CSV（仅含 header）
- [ ] 文件编码：UTF-8

---

### F3：HMM 市场政体识别输出 🆕

**优先级**：P1（月度任务依赖）
**触发时机**：每周日晚（与周度任务同步）
**用途**：月度宏观复盘的量化政体对比基础

**输出文件**：
```
美股交易日记/regime/hmm_regime_{YYYYMMDD}.json
```

**JSON Schema**：
```json
{
  "date": "2026-03-18",
  "regime": "expansion",
  "regime_label_cn": "扩张期",
  "regime_probability": 0.78,
  "regime_history_30d": [
    {"date": "2026-02-17", "regime": "expansion", "probability": 0.82},
    {"date": "2026-02-24", "regime": "expansion", "probability": 0.75},
    ...
  ],
  "spy_return_forecast_5d": 0.012,
  "spy_return_forecast_20d": 0.038,
  "volatility_forecast_20d": 0.152,
  "hmm_n_states": 4,
  "model_version": "hmm_v2.1",
  "training_end_date": "2026-03-18"
}
```

**政体枚举值**（4状态 HMM）：
- `recovery` — 复苏期（低增长，低波动，上行）
- `expansion` — 扩张期（高增长，低波动，上行）
- `overheating` — 过热期（高增长，高波动，震荡）
- `recession` — 衰退期（负增长，高波动，下行）

---

### F4：策略回测绩效报告 🆕

**优先级**：P1（月度任务、季度任务依赖）
**触发时机**：每月月底（与月度宏观复盘任务配合）

**输出文件**：
```
美股交易日记/backtest/performance_{YYYYMMDD}.json
```

**JSON Schema**：
```json
{
  "date": "2026-03-18",
  "strategies": {
    "strategy1": {
      "name": "LSTM Alpha158 504d",
      "sharpe_ratio": 1.42,
      "max_drawdown": -0.128,
      "annual_return": 0.234,
      "win_rate": 0.582,
      "recent_30d_return": 0.051,
      "recent_30d_alpha": 0.023,
      "information_coefficient_30d": 0.068,
      "top10_holdings": ["NVDA", "MSFT", "GOOG", "META", "AMZN", "AAPL", "TSLA", "NFLX", "PLTR", "VLO"]
    },
    "strategy2": {
      "name": "GRU Top30 126d",
      "sharpe_ratio": 1.18,
      "max_drawdown": -0.195,
      "annual_return": 0.187,
      "win_rate": 0.543,
      "recent_30d_return": 0.038,
      "recent_30d_alpha": 0.012,
      "information_coefficient_30d": 0.055,
      "signal_frequency_30d": 8
    },
    "strategy3": {
      "name": "LightGBM RD-Agent",
      "sharpe_ratio": 1.31,
      "max_drawdown": -0.156,
      "annual_return": 0.209,
      "win_rate": 0.561,
      "recent_30d_return": 0.044,
      "recent_30d_alpha": 0.018,
      "information_coefficient_30d": 0.062,
      "active_factors": ["momentum_5d", "volume_surprise", "earnings_revision", "rd_factor_007"]
    },
    "combined_2plus1": {
      "name": "三策略 2+1 组合",
      "sharpe_ratio": 1.67,
      "max_drawdown": -0.103,
      "annual_return": 0.271,
      "win_rate": 0.603,
      "recent_30d_return": 0.059,
      "recent_30d_alpha": 0.031
    }
  },
  "benchmark": {
    "name": "SPY",
    "recent_30d_return": 0.028,
    "annual_return": 0.142
  }
}
```

---

### F5：数据生成清单（Manifest）🆕

**优先级**：P0（所有任务依赖，用于数据完整性验证）
**触发时机**：每次 Qlib 运行完成后自动生成

**输出文件**：
```
美股交易日记/qlib_manifest.json
```

**JSON Schema**：
```json
{
  "last_run": "2026-03-18T16:30:00",
  "run_type": "daily",
  "tickers_processed": ["NVDA", "MSFT", "GOOG", "NFLX", "PLTR", "VLO"],
  "generated_files": {
    "charts": {
      "status": "success",
      "count": 18,
      "date": "2026-03-18",
      "files": [
        "pics/NVDA_week_20260318.png",
        "pics/NVDA_day_20260318.png",
        "pics/NVDA_zoom_20260318.png"
      ]
    },
    "signals": {
      "status": "success",
      "date": "2026-03-18",
      "files": [
        "signals/strategy1_20260318.csv",
        "signals/strategy2_20260318.csv",
        "signals/strategy3_20260318.csv"
      ]
    },
    "regime": {
      "status": "skipped",
      "reason": "仅周日运行",
      "last_available": "2026-03-15"
    },
    "backtest": {
      "status": "skipped",
      "reason": "仅月末运行",
      "last_available": "2026-02-28"
    }
  },
  "errors": [],
  "warnings": ["PLTR 数据延迟，使用 T-1 数据"]
}
```

---

## 四、数据目录结构总览

改造完成后，`美股交易日记/` 的完整目录结构：

```
美股交易日记/
│
├── pics/                              # 图表（F1，已实现）
│   ├── NVDA_week_20260318.png
│   ├── NVDA_day_20260318.png
│   ├── NVDA_zoom_20260318.png
│   └── ...（每股3张）
│
├── signals/                           # 策略信号（F2，待规范化）
│   ├── strategy1_20260318.csv
│   ├── strategy2_20260318.csv
│   └── strategy3_20260318.csv
│
├── regime/                            # HMM政体（F3，待实现）
│   └── hmm_regime_20260316.json       # 每周日更新
│
├── backtest/                          # 回测绩效（F4，待实现）
│   └── performance_20260228.json      # 每月末更新
│
├── qlib_manifest.json                 # 数据清单（F5，待实现）
│
└── skills/                            # Claude Skill定义
    ├── qlib-data-provider/
    │   └── SKILL.md                   # 新建：统一数据读取接口
    ├── stock-trend-analysis/
    │   └── SKILL.md
    └── market-cycle-dashboard/
        └── SKILL.md
```

---

## 五、运行频率与触发规则

| 功能          | 触发时机               | 频率   |
| ----------- | ------------------ | ---- |
| F1 图表生成     | 交易日收盘后（约 16:30 ET） | 每交易日 |
| F2 信号导出     | 与图表同步              | 每交易日 |
| F3 HMM政体    | 每周日盘后（17:00 ET）    | 每周   |
| F4 回测绩效     | 每月最后一个交易日          | 每月   |
| F5 Manifest | 每次运行后自动生成          | 每次运行 |

---

## 六、数据保留策略

- **图表文件**：保留最近 30 个交易日，自动清理旧文件（节省空间）
- **信号 CSV**：保留最近 60 个交易日
- **HMM 政体**：保留最近 12 周
- **回测绩效**：保留最近 12 个月
- **Manifest**：仅保留最新一份（始终覆盖写入）

---

## 七、错误处理规范

Qlib 运行时的错误处理原则：

1. **部分失败不中断**：某只股票图表生成失败，跳过该股票，继续处理其他股票
2. **错误记录到 Manifest**：`errors` 数组中记录所有失败项目
3. **不生成空文件**：若信号模型无输出，仍生成含 header 的空 CSV（避免 Claude 报错）
4. **数据延迟降级**：若当日数据不可用，可使用 T-1 数据并在 Manifest `warnings` 中标注

---

## 八、Claude 端验证规则

Claude 在读取数据前，应通过 `qlib-data-provider` SKILL 执行以下验证：

1. 读取 `qlib_manifest.json`，确认 `last_run` 距今不超过 2 个交易日
2. 对比 manifest 中的 `tickers_processed` 与当前 Longbridge 持仓列表
3. 若 manifest 显示某功能为 `skipped`，使用 `last_available` 指向的历史文件
4. 若 manifest 中有 `errors`，在分析报告中注明数据缺失，不硬中断

---

## 九、改造优先级路线图

### Phase 1（立即）：P0 基础能力
- [x] F1 图表生成（已完成）
- [ ] F2 策略信号 CSV 规范化（统一命名 + schema）
- [ ] F5 Manifest 生成

### Phase 2（近期）：P1 扩展能力
- [ ] F3 HMM 政体识别输出
- [ ] F4 回测绩效报告

### Phase 3（长期）：优化
- 图表生成速度优化（并行生成）
- 信号历史存档与趋势对比
- 因子贡献分解报告（季度任务专用）
