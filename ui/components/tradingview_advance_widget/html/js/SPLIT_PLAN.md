# indicator-engine.js 拆分方案

## 目标

将 1321 行的单文件拆分为 6 个模块文件，每个文件通过 `prototype` 扩展方式为 `IndicatorEngine` 类添加方法。

## 文件结构

```
html/js/
├── indicator-engine.js         # 主入口 (class定义 + 属性 + 公有API)
├── indicator-catalog.js        # catalog 构建与查找
├── indicator-calculator.js     # 组合指标计算 + 核心计算路由
├── indicator-renderer.js       # 渲染逻辑
├── indicator-lifecycle.js      # 显示/隐藏/状态管理
└── indicator-state.js          # 调试/自检/工具方法
```

## 依赖关系

```
indicator-engine.js (class 定义)
  ├── indicator-catalog.js   (依赖 this._catalog, this._indicators)
  ├── indicator-state.js     (依赖 this._activeMap, this._visibleMap)
  ├── indicator-calculator.js(依赖 catalog + state + renderer)
  ├── indicator-renderer.js  (依赖 chartManager, primitives)
  └── indicator-lifecycle.js (依赖 renderer + calculator)
```

## 行范围分配

| 文件 | 行范围 | 方法 |
|---|---|---|
| `indicator-engine.js` | 1-20, 125-158, 215-286, 640-662, 1232-1321 | constructor, init, toggle, calculateAndAdd, remove, search, setComputeSource, debug |
| `indicator-catalog.js` | 31-124, 159-214 | _findCalc, _buildCatalog, _requestPythonFallback, _requestPythonOnly, _findCatalogEntry, _resolveAlias |
| `indicator-calculator.js` | 287-638, 663-770 | _calculateBaseVolume, _calcSMA, _calculateSMACombo, _calculateEMACombo, _calculateSMAEMACombo, _calculateCompound, _calculateAndAdd, setBarData |
| `indicator-renderer.js` | 771-988 | _renderResult, _register |
| `indicator-lifecycle.js` | 1006-1231 | handlePythonResult, _hide, _show, _hideOne, _toggleLinked, _removeOne |
| `indicator-state.js` | (无提取) | 已有方法保持在主文件 |

## 加载顺序

`template.html` 中按依赖顺序加载:

```html
<script src="js/indicator-engine.js"></script>      <!-- class 定义 -->
<script src="js/indicator-state.js"></script>        <!-- 无外部依赖 -->
<script src="js/indicator-catalog.js"></script>      <!-- 无外部依赖 -->
<script src="js/indicator-renderer.js"></script>     <!-- 无外部依赖 -->
<script src="js/indicator-calculator.js"></script>   <!-- 依赖 catalog+renderer -->
<script src="js/indicator-lifecycle.js"></script>    <!-- 依赖 calculator+renderer -->
```

## 执行方式

使用 `delegate_task` 子智能体逐个创建文件。
