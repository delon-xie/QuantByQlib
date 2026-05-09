# RD-Agent 因子发现：技术备忘录

> 文档版本：v2.0　　最后更新：2026-02-28　　作者：QuantByQlib 开发组

---

## 目录

1. [RD-Agent 在系统中的定位](#1-rd-agent-在系统中的定位)
2. [架构总览](#2-架构总览)
3. [数据流全链路](#3-数据流全链路)
4. [关键模块说明](#4-关键模块说明)
5. [因子验证与注入机制](#5-因子验证与注入机制)
6. [Qlib 表达式语法约束](#6-qlib-表达式语法约束)
7. [当前实现状态](#7-当前实现状态)
8. [运行环境与配置](#8-运行环境与配置)
9. [错误处理与降级策略](#9-错误处理与降级策略)

---

## 1. RD-Agent 在系统中的定位

RD-Agent（Research Direction Agent）是 QuantByQlib 的**自动化因子研究引擎**，其核心定位是"AI 量化研究员"：

- 运行在 Docker 容器中，调用 DeepSeek LLM 自主提出因子假设
- 在容器内使用 Qlib 数据对假设进行截面 IC 验证（Spearman 相关系数）
- 输出 Qlib 兼容的因子表达式及量化指标（IC 均值、IC 标准差、Sharpe）
- 通过因子注入器（FactorInjector）将通过验证的因子注入 LightGBM 选股策略

与 Alpha158 等**预定义因子集**的本质区别在于：RD-Agent 产出的是**动态发现的因子**，理论上可以捕获传统因子体系未覆盖的收益来源。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      UI 层（PyQt6）                               │
│                                                                   │
│  FactorPage（因子发现）          ScreeningPage（量化选股）          │
│  ├─ 启动 / 停止按钮               ├─ 策略卡片选择                  │
│  ├─ 实时日志面板                   ├─ 🧬 已注入因子面板（tooltip）  │
│  ├─ 因子发现结果表格               └─ 运行控制 + 进度              │
│  ├─ ✅ 注入选股策略 按钮                                           │
│  └─ 已注入因子清单（带 tooltip 通俗描述）                          │
└────────────────────────┬────────────────────────────────────────┘
                         │ Qt 信号 / EventBus
                         ↓
         ┌───────────────────────────────────────┐
         │  RDAgentWorker（QRunnable）             │
         │  FactorInjectWorker（QRunnable）        │
         └───────────────┬───────────────────────┘
                         ↓
     ┌───────────────────────────────────────────────┐
     │  RDAgentRunner              FactorInjector     │
     │  ├─ 环境变量装配             ├─ 语法预检         │
     │  ├─ Docker 前置检查          ├─ IC 验证（Qlib）  │
     │  └─ 日志流读取线程           ├─ 合并去重 + 重验  │
     │                             └─ 持久化 JSON      │
     └──────────┬────────────────────────────────────┘
                │
    ┌───────────┴────────────┐
    ↓                        ↓
┌──────────────────┐  ┌──────────────────────────────┐
│  DockerManager   │  │  SessionManager               │
│  容器生命周期管理 │  │  持久化因子会话（含描述字段）  │
│  日志流读取       │  │  ~/.quantbyqlib/rdagent_sessions.json │
└────────┬─────────┘  └──────────────────────────────┘
         ↓
┌──────────────────┐  ┌──────────────────────────────┐
│  Docker 容器      │  │  valid_factors.json           │
│  run_factor_     │  │  ~/.quantbyqlib/valid_factors.json │
│  discovery.py    │  │  通过验证的因子（表达式+名称+描述）│
│  （DeepSeek API）│  └──────────────────────────────┘
└──────────────────┘
```

---

## 3. 数据流全链路

### 3.1 因子发现流程（RD-Agent）

```
用户点击「启动因子发现」
  ↓
FactorPage._on_start()
  ↓ 创建 RDAgentWorker，投入 QThreadPool
  ↓
RDAgentRunner.start()
  ├─ check_docker()              → Docker Desktop 是否运行
  ├─ image_exists()              → local_qlib:latest 是否存在
  └─ DEEPSEEK_API_KEY 检查       → 必须非空，否则拒绝启动
  ↓
DockerManager.start_container(env_vars, workspace_dir)
  ├─ 删除同名旧容器（若存在）
  ├─ 镜像：local_qlib:latest（linux/amd64）
  ├─ Volume：~/.qlib/qlib_data → /root/.qlib/qlib_data（只读）
  ├─           ~/.quantbyqlib/rdagent_workspace → /workspace（读写）
  └─ 命令：python run_factor_discovery.py
  ↓
容器内 run_factor_discovery.py：
  ├─ Step 1：按优先级检测 Qlib 数据目录（/root/.qlib/qlib_data 等）
  ├─ Step 2：调用 DeepSeek API 生成 10 个因子候选（含 description）
  ├─ Step 3：语法预检（_precheck_expression）拦截已知错误模式
  ├─ Step 4：Qlib D.features 计算截面 Spearman IC（最近 252 交易日）
  └─ Step 5：写出 /workspace/discovered_factors.json
  ↓
容器退出 → RDAgentRunner._stream_loop() 读取结果文件
  ├─ SessionManager.add_session(factors)   → 完整保存所有字段（含 description）
  └─ done_cb(factors)
       ↓
  FactorPage._on_completed(factors)
       ├─ _populate_factor_table()         → 表格展示
       └─ _inject_btn 启用
```

### 3.2 因子注入流程（FactorInjector）

```
用户点击「✅ 注入选股策略」
  ↓
FactorInjectWorker.run()（QThreadPool 子线程）
  ↓
strategies/factor_injector.py → get_valid_factors()
  ├─ 读取 SessionManager 最新会话
  ├─ 构建 expression→{name,description} 映射（汇总全部历史会话）
  ├─ IC 预筛：ic_mean < 0.03 的直接淘汰
  ├─ 语法预检：_precheck_expression() 拦截非法表达式（不进入 Qlib）
  ├─ 合并历史库（load_valid_factors）：旧因子一并参与重验证
  └─ Qlib D.features 逐一验证截面 IC（joblib_backend=sequential）
       ├─ 通过（IC ≥ 0.03）→ 加入 valid_factors_list
       └─ 未通过或语法错误 → 淘汰
  ↓
save_valid_factors(valid_factors_list)
  → ~/.quantbyqlib/valid_factors.json
     {
       "updated_at": "...",
       "count": N,
       "expressions": [...],          # 向后兼容
       "factors": [                   # 新格式（含名称+描述）
         {"expression":"...", "name":"...", "description":"..."},
         ...
       ]
     }
  ↓
clear_cache()             → 清除旧模型预测缓存
EventBus.rdagent_factors_injected.emit(valid_factors_list)
  → ScreeningPage 自动刷新"已注入因子"面板
```

### 3.3 选股时加载自定义因子

```
ScreeningWorker → QlibStrategy.run()
  ↓
strategies/qlib_strategy.py → _run_with_qlib_or_fallback()
  ├─ load_valid_factors()     → 读取 valid_factors.json（TTL 24h）
  ├─ 若有有效因子且策略为 LightGBM：
  │   └─ _fit_with_extra_factors() → 拼接 Alpha158 + 自定义因子列
  └─ 否则：model.fit(dataset)（纯 Alpha158）
```

### 3.4 因子库"合并去重 + 重验证"策略

每次运行"注入选股策略"时：

1. **新候选**：当前 session 的预筛通过因子
2. **历史库**：`valid_factors.json` 中已有的全部因子（不受 TTL 限制）
3. **合并去重**：历史库中不在新候选里的因子加入候选池
4. **全部重验**：所有候选统一重跑 IC 验证
5. **自动淘汰**：历史中已失效的因子在重验后自然落选
6. **更新库**：将通过本轮验证的因子写回 `valid_factors.json`

这确保了因子库随时间**累积**而非替换，且不会保留已失效的因子。

---

## 4. 关键模块说明

### 4.1 DockerManager（`rdagent_integration/docker_manager.py`）

| 方法                                         | 说明                                          |
| ------------------------------------------ | ------------------------------------------- |
| `available`                                | 属性，Docker Desktop 是否连接                      |
| `check_docker()`                           | 返回 `(bool, status_msg)`                     |
| `image_exists()`                           | 检查 `local_qlib:latest` 是否存在                 |
| `start_container(env_vars, workspace_dir)` | 启动容器，挂载 Qlib 数据目录 + 工作目录                    |
| `stop_container()`                         | 停止容器                                        |
| `stream_logs(log_cb, stop_event)`          | 实时流式读取日志                                    |
| `container_status()`                       | 返回 `"running"` / `"exited"` / `"not_found"` |

**挂载关系：**
```
宿主机 ~/.qlib/qlib_data        → 容器 /root/.qlib/qlib_data  （只读）
宿主机 ~/.quantbyqlib/rdagent_workspace → 容器 /workspace  （读写）
```

### 4.2 RDAgentRunner（`rdagent_integration/rdagent_runner.py`）

1. `_build_env()` — 从 `.env` 文件读取 API Keys，构造容器环境变量
2. `start()` — 前置检查 → 启动容器 → 启动日志流线程
3. `_stream_loop()` — 持续读取日志；容器退出后读取 `discovered_factors.json`，调用 `SessionManager.add_session()`，再触发 `done_cb`
4. `stop()` — 置位 `_stop_event`，停止日志流，调用 `DockerManager.stop_container()`

### 4.3 SessionManager（`rdagent_integration/session_manager.py`）

持久化每次因子发现会话，存储路径：`~/.quantbyqlib/rdagent_sessions.json`

**`add_session(factors)`** — 完整保存所有字段（`name`、`expression`、`description`、`ic_mean`、`ic_std`、`sharpe`、`category`），不再丢弃任何字段。

会话 JSON 格式：
```json
{
  "id": 3,
  "timestamp": "2026-02-28T09:00:00",
  "status": "completed",
  "factor_count": 10,
  "factors": [
    {
      "name": "momentum_20d",
      "expression": "$close/Ref($close,20)-1",
      "description": "20日价格动量",
      "category": "动量",
      "ic_mean": 0.0412,
      "ic_std": 0.021,
      "sharpe": 1.96
    }
  ]
}
```

### 4.4 容器脚本（`~/.quantbyqlib/rdagent_workspace/run_factor_discovery.py`）

在 `local_qlib:latest` 容器内运行，流程：

1. **Qlib 初始化**：按优先级探测数据目录（`/root/.qlib/qlib_data` 等）
2. **DeepSeek 生成**：调用 API 生成 10 个候选因子（含 `description`、`category`）
3. **语法预检**：`_precheck_expression()` 拦截非法模式，输出 `PreCheckFail` 日志
4. **IC 验证**：10 只蓝筹股，最近 252 交易日，截面 Spearman IC
5. **写出结果**：`/workspace/discovered_factors.json`（含完整字段）

### 4.5 FactorInjector（`strategies/factor_injector.py`）

核心函数：

| 函数                                              | 说明                                                       |
| ----------------------------------------------- | -------------------------------------------------------- |
| `_precheck_expression(expr)`                    | 语法预检，返回 `(ok, reason)`，拦截 Max/Min 滥用、Abs(Ref) 嵌套、一元负号    |
| `validate_factor(expr, universe, threshold_ic)` | Qlib 实测截面 IC，强制 `sequential` 后端避免 macOS 多进程崩溃            |
| `get_valid_factors(min_ic, progress_cb)`        | 主流程：预筛 + 合并历史 + 逐一验证，返回 `list[dict]`                     |
| `save_valid_factors(factors)`                   | 持久化到 `valid_factors.json`（兼容 `list[dict]` 和 `list[str]`） |
| `load_valid_factors(max_age_hours)`             | 加载表达式列表（向后兼容，TTL 保护）                                     |
| `get_inject_status()`                           | 返回注入状态摘要，含 `factors` 列表（完整 name/description/expression）  |

### 4.6 FactorInjectWorker（`workers/factor_inject_worker.py`）

`QRunnable` 子类，后台执行：
1. Qlib 初始化检查
2. `get_valid_factors()` — 含进度回调
3. `save_valid_factors()` — 持久化
4. `clear_cache()` — 清除旧模型缓存
5. `EventBus.rdagent_factors_injected.emit()` — 广播刷新 UI

### 4.7 UI 层（因子相关页面）

**FactorPage（`ui/pages/factor_page.py`）：**
- 启动 / 停止控制
- 实时日志滚动显示（绿色终端风格）
- 因子发现结果表格（IC 彩色标注）
- `✅ 注入选股策略` 按钮 + 进度条
- **已注入因子清单**（带 tooltip）：每行显示因子名+表达式截断，鼠标悬停显示通俗描述+完整表达式
- 页面加载时自动读取历史会话 + 已注入状态

**ScreeningPage（`ui/pages/screening_page.py`）：**
- 策略卡片选择
- **🧬 已注入自定义因子面板**（同款 tooltip 标签列表）：显示当前库中因子，注明"仅 LightGBM 策略使用"
- 因子注入完成后通过 EventBus 自动刷新面板

---

## 5. 因子验证与注入机制

### 5.1 两层 IC 验证

| 层级    | 位置                                  | 时机      | 说明                       |
| ----- | ----------------------------------- | ------- | ------------------------ |
| 容器内验证 | `run_factor_discovery.py`           | 因子发现时   | 10 只股票，近 252 日，筛除明显无效因子  |
| 宿主机验证 | `factor_injector.validate_factor()` | 用户点击注入时 | 30 只蓝筹股，近 252 日，最终决定是否注入 |

两层均使用截面 Spearman IC，阈值均为 0.03。宿主机验证对每个候选因子独立运行，采用 `joblib_backend=sequential` 避免 macOS 多进程崩溃。

### 5.2 数据持久化一览

| 文件                                                         | 内容              | 生命周期       |
| ---------------------------------------------------------- | --------------- | ---------- |
| `~/.quantbyqlib/rdagent_sessions.json`                     | 全部历史会话（含完整因子字段） | 累积追加，不自动清除 |
| `~/.quantbyqlib/valid_factors.json`                        | 当前有效因子库（含名称+描述） | 每次注入时覆盖写入  |
| `~/.quantbyqlib/rdagent_workspace/discovered_factors.json` | 最后一次容器发现结果      | 每次容器运行覆盖   |

`valid_factors.json` 格式（v2，向后兼容 v1）：
```json
{
  "updated_at": "2026-02-28T09:11:02",
  "count": 6,
  "expressions": ["$close/Ref($close,20)-1", ...],
  "factors": [
    {
      "expression": "$close/Ref($close,20)-1",
      "name": "momentum_20d",
      "description": "20日价格动量"
    }
  ]
}
```

### 5.3 LightGBM 因子注入方式

自定义因子通过 `D.features()` 单独计算后，在 DataFrame 层面与 Alpha158 输出 `pd.concat(axis=1)` 拼接，再传入 `LGBModel.fit()`：

```python
# 伪代码
alpha158_df = dataset.prepare("train", col_set=["feature","label"])
custom_df   = D.features(universe, extra_exprs, start, end)
combined_df = pd.concat([alpha158_df["feature"], custom_df], axis=1)
model.fit_with_combined(combined_df, alpha158_df["label"])
```

**注意**：LSTM / GRU 策略不支持自定义因子注入（`d_feat` 固定为 158/360，追加列会导致维度错误）。

---

## 6. Qlib 表达式语法约束

本节记录 Qlib 0.9.7 不支持的表达式模式（已通过 `_precheck_expression()` 自动拦截）。

### 6.1 Max / Min — 只能做滚动极值，不能做逐元素比较

```python
# ❌ 错误：Max/Min 第二参数不能是表达式
Max(Ref($close,5), Ref($close,10))     # Error: window must be integer
Max($high, $low)                        # Error: window must be integer

# ✅ 正确：第一参数=字段，第二参数=整数窗口
Max($close, 20)                         # 20日滚动最大收盘价
Min($low, 5)                            # 5日滚动最低价

# ✅ 两序列取较大值 → 改用 If
If(Ref($close,5) > Ref($close,10), Ref($close,5), Ref($close,10))
```

### 6.2 Abs — 不能嵌套 Ref

```python
# ❌ 错误：Abs 内不能有 Ref
Abs($high - Ref($close,1))              # Error: window must be integer

# ✅ 正确：ATR 改用 Mean
Mean($high - $low, 14)                  # 简化 ATR
Mean($high - $low, 14) / Mean($close, 14)
```

### 6.3 一元负号

```python
# ❌ 错误：一元负号 -(expr)
-(A - B)

# ✅ 正确
(B - A)          # 调换操作数
0 - (A - B)      # 用 0 相减
(-1) * (A - B)   # 乘以 -1
```

### 6.4 预检逻辑（`_precheck_expression`）

使用括号深度追踪精确定位 Max/Min 的第二参数，非整数常量即拦截：

```python
for m in re.finditer(r'\b(Max|Min)\s*\(', expr):
    # 追踪括号深度，找到第一/第二参数分隔逗号
    # 检查第二参数是否匹配 r'^\d+\s*\)'
    if not integer_window:
        return False, "Max/Min 第二参数必须是整数窗口..."
```

同样的逻辑在容器 `run_factor_discovery.py` 和宿主机 `factor_injector.py` 中各有一份，覆盖两层验证。

---

## 7. 当前实现状态

### 已完成 ✅

| 功能                | 说明                                              |
| ----------------- | ----------------------------------------------- |
| Docker 容器完整生命周期管理 | 启动/停止/状态查询/日志流                                  |
| DeepSeek LLM 因子生成 | 含 description/category，备用内置因子兜底                 |
| 容器内 IC 验证         | 截面 Spearman，动态时间窗口（最近 252 交易日）                  |
| Qlib 数据目录自动检测     | 优先级列表探测，兼容不同挂载路径                                |
| 语法预检（双层）          | 容器内 + 宿主机均有 `_precheck_expression()`，清晰错误提示     |
| IC 验证（宿主机）        | Spearman IC ≥ 0.03，sequential 后端，multiindex 去重  |
| 合并去重 + 重验证        | 历史库自动纳入重验，失效因子自然淘汰                              |
| 因子持久化（完整字段）       | `valid_factors.json` v2 格式，含 name/description   |
| 会话完整字段保存          | `SessionManager.add_session()` 保留所有字段           |
| LightGBM 因子注入     | `_fit_with_extra_factors()` 拼接 Alpha158 + 自定义因子 |
| 模型缓存失效            | 注入后 `clear_cache()` 强制下次重训练                     |
| 已注入因子 UI 展示       | 因子发现页 + 量化选股页，带 tooltip 通俗描述                    |
| EventBus 实时刷新     | `rdagent_factors_injected` 信号驱动选股页自动更新          |
| 历史会话自动加载          | 页面打开时延迟 800ms 读取最新会话                            |
| 一键导出 CSV          | 因子发现页「📥 导出」按钮                                  |

### 不支持 / 不在范围内

| 功能 | 说明 |
|------|------|
| LSTM / GRU 因子注入 | `d_feat` 固定，追加列导致维度错误，需重构模型定义 |
| 因子贡献度追踪 | 注入前后 Sharpe 对比（Phase D，未实现） |
| 因子版本管理 | 跨会话因子 diff（未实现） |

---

## 8. 运行环境与配置

### 8.1 必要条件

| 条件 | 说明 |
|------|------|
| Docker Desktop | 必须运行，版本 ≥ 20.x |
| `local_qlib:latest` 镜像 | 首次通过 `pip install rdagent && rdagent fin_quant` 构建 |
| `DEEPSEEK_API_KEY` | 必填，在 `.env` 中配置 |
| Qlib 美股数据 | `~/.qlib/qlib_data`（宿主机），被挂载进容器用于 IC 验证 |
| ARM Mac（M 系列） | 自动使用 `linux/amd64` + Rosetta 2，性能略降 |

### 8.2 环境变量

```ini
# .env 文件中配置（均由 RDAgentRunner._build_env() 读取）

# 必填
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# 推荐配置
CHAT_MODEL=deepseek/deepseek-chat       # 默认值，可不填
FMP_API_KEY=xxxxxxxxxxxxxxxx
ALPHA_VANTAGE_API_KEY=xxxxxxxxxxxxxxxx

# 可选
OPENAI_API_KEY=sk-xxxxxxxx
FINNHUB_API_KEY=xxxxxxxxxxxxxxxx
```

### 8.3 目录挂载关系

```
宿主机：~/.qlib/qlib_data/
         ↓ 只读挂载
容器内：/root/.qlib/qlib_data/

宿主机：~/.quantbyqlib/rdagent_workspace/
         ↓ 读写挂载
容器内：/workspace/
  └─ discovered_factors.json  ← 容器写出，宿主机 SessionManager 读取
  └─ run_factor_discovery.py  ← 容器内执行的发现脚本
```

### 8.4 首次初始化步骤

```bash
# Step 1：安装 rdagent pip 包（包含镜像构建工具）
pip3 install rdagent

# Step 2：初次运行（自动构建 local_qlib:latest，约 2GB，需较长时间）
rdagent fin_quant

# Step 3：在 QuantByQlib .env 配置 DEEPSEEK_API_KEY
echo "DEEPSEEK_API_KEY=sk-xxx..." > /path/to/QuantByQlib/.env

# Step 4：确认 Qlib 美股数据已下载（用于宿主机 IC 验证）
# 在「参数配置」页面点击「下载数据」

# Step 5：启动 QuantByQlib，进入「因子发现」页面点击「启动因子发现」
# Step 6：发现完成后点击「✅ 注入选股策略」
# Step 7：进入「量化选股」，选择 LightGBM 策略（成长股/市场自适应），运行选股
```

---

## 9. 错误处理与降级策略

### 9.1 容器层级

| 错误情况 | 处理方式 |
|----------|----------|
| Docker Desktop 未运行 | `_init_client()` 捕获异常，`available=False`，所有方法返回 False/空 |
| 镜像不存在 | `image_exists()` 返回 False，RDAgentRunner 拒绝启动并提示构建命令 |
| 容器启动失败 | `start_container()` 返回 `(False, error_msg)`，触发 `signals.error` |
| Qlib 数据目录不存在 | 容器跳过 IC 验证，因子以 `ic_mean=None` 输出，宿主机信任预筛结果 |
| DeepSeek API 失败 | 回退到内置备选因子（10 个经典表达式）|

### 9.2 因子验证层级

| 错误情况 | 处理方式 |
|----------|----------|
| `DEEPSEEK_API_KEY` 未配置 | `_build_env()` 检查失败，启动被拒绝 |
| 表达式语法非法 | `_precheck_expression()` 预检失败，跳过该因子，记录 warn 日志 |
| `Max(expr, expr)` 等 Qlib 不支持的写法 | 预检拦截，给出清晰错误说明和正确写法示例 |
| `D.features()` 多进程崩溃（macOS） | 强制 `joblib_backend=sequential` 规避 |
| IC 数据不足（< 30 个样本） | `validate_factor()` 返回 False，因子被淘汰 |
| Qlib 未初始化 | `get_valid_factors()` 降级为信任 RD-Agent 报告的 `ic_mean` |

### 9.3 UI 层级

任何错误最终都通过 `signals.error.emit(msg)` 上报给对应页面，在日志面板以红色文字显示，不会导致应用崩溃。`FactorInjectWorker` 错误通过 `_inject_status_lbl` 展示给用户。

---

## 附录：关键文件路径速查

| 文件 | 说明 |
|------|------|
| `rdagent_integration/docker_manager.py` | Docker 容器管理 |
| `rdagent_integration/rdagent_runner.py` | 运行编排，环境变量装配，日志流，SessionManager 写入 |
| `rdagent_integration/session_manager.py` | 因子会话持久化（含完整字段） |
| `strategies/factor_injector.py` | 因子验证、语法预检、持久化、状态查询 |
| `workers/rdagent_worker.py` | Qt 线程桥接（因子发现） |
| `workers/factor_inject_worker.py` | Qt 线程桥接（因子注入） |
| `ui/pages/factor_page.py` | 因子发现 UI，含注入按钮和已注入因子清单 |
| `ui/pages/screening_page.py` | 量化选股 UI，含已注入因子面板 |
| `~/.quantbyqlib/rdagent_sessions.json` | 历史会话持久化 |
| `~/.quantbyqlib/valid_factors.json` | 当前有效因子库（v2 格式，含描述） |
| `~/.quantbyqlib/rdagent_workspace/` | 容器工作目录挂载点 |
| `~/.quantbyqlib/rdagent_workspace/run_factor_discovery.py` | 容器内因子发现脚本 |
