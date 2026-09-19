# Track 4 题型模型契约

本文是当前实现的设计依据。每个题型都独立声明：官方必有输入、容易从冻结材料取得的参数、允许进入计算器的白名单、计算方法、LLM 唯一需要完成的判断，以及缺失信息时的 fallback。

公共流程只负责读取题目、截止日期过滤、检索、精确引用、输出和校验。不同题型不能读取彼此的参数。

## 通用参数规则

允许的参数来源只有：

```text
given       task row 直接提供
computed    程序从冻结历史表确定性计算
extracted   从原文提取的明确数值，必须带逐字引用
text_signal 从原文判断的五档方向，非零必须带逐字引用
missing     找不到，触发本题 fallback
```

文字信号统一为：

```text
-2 strong_negative
-1 negative
 0 neutral_or_unknown
+1 positive
+2 strong_positive
```

LLM 不得直接输出最终 label、point forecast、interval、rank、beta、confidence 或未经原文明确给出的精确数字。

## 1. EPS beat / miss / inline

### 题目一定提供

- `consensus_eps`
- `threshold_pct`
- 合法标签和比较条件
- 公司、目标季度、cutoff

### 材料中容易找到

- 明确的目标期营收或毛利率指引
- 明确的目标期费用指引
- 最近已公布季度的 EPS，只能作为背景

### 计算器输入白名单

```text
consensus_eps                given
threshold_pct                given
target_period_earnings_signal text_signal
```

### 计算方法

一致预期是强基线。只有明确且强烈的目标期指引才跨越题目阈值：

```text
signal = +2 → forecast = consensus × (1 + 1.25 × threshold)
signal = -2 → forecast = consensus × (1 - 1.25 × threshold)
其他        → forecast = consensus
```

最终标签严格使用官方 beat/miss/inline 条件。

### LLM 只判断

目标季度盈利环境是否有明确的强正面或强负面指引。历史 EPS、泛泛的乐观措辞、没有目标期的增长描述都返回 0。

### 缺失时

`forecast = consensus`，标签 `inline`，扩大区间。

## 2. EPS 同比 up / down

### 题目一定提供

- `prior_year_q_eps`
- 目标季度和同比基准季度
- 公司、cutoff

### 材料中容易找到

- 最近已报告季度 EPS 相对其上年同期的方向
- 收入和经营利润是否同比改善
- 明确的一次性收益或费用

### 计算器输入白名单

```text
prior_year_q_eps        given
yoy_earnings_signal     text_signal
```

### 计算方法

这是分类题，不把模糊文字伪装成精确 EPS 模型：

```text
signal > 0 → up
signal < 0 → down
signal = 0 → 使用最新已报告季度的同比 EPS 方向；仍不可得则使用固定 down fallback
```

为了满足 point forecast 与标签一致：

```text
step = max(5% × abs(prior_year_q_eps), 0.01)
up   → prior_year_q_eps + step
down → prior_year_q_eps - step
```

`step` 只用于表达分类方向，不声称是精确 EPS 预测。

### LLM 只判断

根据明确同比文字判断目标期盈利方向，并识别强一次性项目。仅有环比信息时返回 0。

### 缺失时

优先使用最近报告季度同比方向；无法取得时输出 `down` 并使用宽区间。这个 fallback 是可复现 tie-breaker，不代表经济先验。

## 3. 银行 EPS 增速

### 题目一定提供

- `prior_year_q_eps`
- 目标季度和同比季度
- 银行、cutoff

### 材料中容易找到

- 最近一季 diluted EPS
- 最近一季上年同期 diluted EPS
- 这两个数通常出现在同一张 consolidated income statement

### 计算器输入白名单

```text
prior_year_q_eps               given
latest_reported_eps            extracted
latest_reported_prior_year_eps extracted
```

`entity_id`、`name`、`cik` 只用于把公司映射到正确文件，不参与数值预测。程序优先从同一张表确定性提取这两个数；表格格式无法解析时才让 LLM 按相同契约提取。

### 计算方法

使用季度 seasonal change persistence：把最近已观察到的同比 EPS 变化额延续到目标季度。

```text
recent_yoy_delta = latest_reported_eps - latest_reported_prior_year_eps
forecast_target_eps = prior_year_q_eps + recent_yoy_delta
growth_pct = (forecast_target_eps - prior_year_q_eps)
             / abs(prior_year_q_eps) × 100
```

这比给 NII、拨备、费用任意设置权重更透明，也只需要两个容易核验的数字。

### LLM 只判断

不判断方向；只在程序无法解析表格时，从同一张表中提取最近季度 current/prior-year diluted EPS，并附原文引用。程序检查两者属于同一季度比较和 GAAP diluted EPS。

### 缺失时

只要两个数中任一个缺失，就预测 0% 增长并扩大区间。不让模型用 NII 等文字凭空换算 EPS 百分比。

## 4. 信用事件

### 题目一定提供

- 公司/发行人
- 事件定义和预测窗口
- cutoff

### 材料中容易找到

- 明确 going-concern 语言
- 明确流动性不足
- 实际 covenant breach 或 payment default
- 近期债务到期与已说明的资金来源

### 计算器输入白名单

```text
going_concern_present              text_signal/flag
liquidity_explicitly_insufficient  text_signal/flag
covenant_breach_or_payment_default text_signal/flag
near_term_debt_without_funding     text_signal/flag
```

### 计算方法

```text
实际 unresolved breach/default       → score 0.85, credit_event
going concern + 明确流动性不足        → score 0.70, credit_event
只有其中一个                         → score 0.40, no_event
只有无资金来源的近期到期债务           → score 0.20, no_event
没有强旗标                            → score 0.05, no_event
```

score 是固定分类分数，不宣称为已校准违约概率。

### LLM 只判断

四个旗标是否被原文明示。风险因素模板、可能违约、已经解决且当前合规的 waiver 都不算实际 breach/default。

### 缺失时

所有旗标 false，输出 `no_event`、0.05 和宽概率区间。

## 5. 财报后反应

### 题目一定提供

- `flat_threshold_abn_pct`
- benchmark、event window
- 公司、cutoff

### 材料中容易找到

- 明确的未来收入、利润率或费用指引

### 计算器输入白名单

```text
flat_threshold_abn_pct          given
explicit_forward_outlook_signal text_signal
```

### 计算方法

```text
signal = +2 → +1.25 × threshold, positive_reaction
signal = -2 → -1.25 × threshold, negative_reaction
其他        → 0, flat
```

### LLM 只判断

是否存在明确且强烈的前瞻指引。历史业绩、管理层一般性乐观表态都返回 0。

### 缺失时

预测 0% abnormal return 和 `flat`。当前冻结材料缺少分析师预期、期权和仓位，因此不使用这些参数。

## 6. 国债收益率曲线

### 题目一定提供

- `maturity_years`
- `start_yield_pct`
- cutoff 和 resolution

### 材料中容易找到

- FOMC statement/SEP 的政策方向
- snapshot 中明确写出的市场政策路径差距（若有）

### 计算器输入白名单

```text
maturity_years  given
policy_direction text_signal
```

### 计算方法

使用一个共同政策冲击并按期限衰减，保证同一题内曲线一致：

```text
hawkish +2 → +30 bps shock
hawkish +1 → +15 bps shock
neutral     → 0
dovish  -1 → -15 bps shock
dovish  -2 → -30 bps shock

0-2Y  × 1.0
>2-5Y × 0.8
>5-10Y × 0.6
>10Y × 0.4
```

这些是公开开发结果可用前的固定模型常数，不是从材料提取的 beta。

### LLM 只判断

政策信息对收益率是 hawkish、neutral 还是 dovish。不能输出 term premium 或市场隐含路径数字。

### 缺失时

所有期限预测 0 bps，区间保持较宽。

## 7. CPI 分项

### 题目一定提供

- `latest_published_mom_pct`
- component/series
- 目标月份

### 材料中容易找到

- 同一分项的历史月环比表
- 汽油价格历史（公开 unit 中存在）

### 计算器输入白名单

```text
latest_published_mom_pct given
component_history        computed
gasoline_month_change    computed, only gasoline/energy
```

### 计算方法

```text
普通分项 = 0.7 × latest + 0.3 × 最近三月中位数
gasoline = 当月周频汽油均价相对上月变化，限制在 [-5, 5]
energy   = 0.4 × gasoline forecast
```

### LLM 只判断

不调用 LLM。

### 缺失时

没有历史表则 carry forward `latest_published_mom_pct`；没有汽油数据则汽油和能源也使用普通分项公式。

## 8. 宏观修订

### 题目一定提供

- `latest_precutoff_estimate`
- `series_id`、ref month、vintage、resolution date

### 材料中容易找到

- 同一系列的 ALFRED vintage 表
- 明确列出的历史 revision notes

### 计算器输入白名单

```text
latest_precutoff_estimate given
historical_first_revisions computed
```

### 计算方法

```text
revision = 历史连续 vintage 修订额的中位数
forecast = latest_estimate + revision
revision > 0 → up，否则 down
```

### LLM 只判断

不调用 LLM。V1 不处理难以量化到单月的 benchmark 公告。

### 缺失时

预测 revision=0，使用固定 `down` tie-breaker，并扩大区间。

## 9. 国债拍卖

### 题目一定提供

- tenor、auction date、new/reopening
- 部分行提供 offering size

### 材料中容易找到

- 同 tenor 历史 bid-to-cover 表

### 计算器输入白名单

```text
tenor                  given
same_tenor_btc_history computed
```

### 计算方法

```text
baseline = 最近六场同 tenor BTC 平均值
trend = (最近一场 - 倒数第三场) / 2，限制在 [-0.08, 0.08]
forecast = baseline + trend
```

V1 不使用发行规模和 indirect bidder 调整，因为尚未训练可靠系数。

### LLM 只判断

不调用 LLM。

### 缺失时

使用 2.5 通用 baseline 和宽区间。

## 10. COT 仓位排名

### 题目一定提供

- `trailing_4wk_net_change_pct_oi`
- 当前 net position、open interest、net %OI

### 材料中容易找到

- 同市场历史 net %OI 表

### 计算器输入白名单

```text
trailing_4wk_net_change_pct_oi given
current_net_pct_oi             given
historical_net_pct_oi          computed
```

### 计算方法

```text
forecast = trailing_4wk_net_change_pct_oi
如果 abs(current_net_pct_oi) 位于历史绝对值最高 10%：forecast × 0.5
所有行计算完成后，按 forecast 从大到小统一排名
```

### LLM 只判断

不调用 LLM。V1 不估选举、FOMC 等事件的资产级系数。

### 缺失时

没有历史表时直接使用 trailing 4-week 值；该字段也缺失时使用 0。

## 11. 未知题型

### 输入白名单

- target type、合法 labels、单位
- row 中所有有限数值字段；未知题型的白名单按“数值类型”声明，不把未识别的文字字段交给通用计算器
- 一个 `directional_signal`

### 计算方法

- classification：从允许标签中选择与方向相符的标签。
- regression：使用最近值或 prior 值，不做无依据的大调整。
- ranking：使用明确的连续 baseline 字段，再跨行排序。

### 缺失时

仍生成完整 roster、合法区间和引用，绝不因未知 family 崩溃。

## 隔离要求

每个 family 配置必须声明：

```text
allowed_entity_fields
generic_numeric_fields_policy
numeric_parameters
text_signals
solver
model_required
```

传给 LLM 的 `ENTITY_JSON` 只能包含 `allowed_entity_fields`；未知题型还可包含 `generic_numeric_fields_policy` 允许的有限数值字段。计算器只能收到过滤后的 row。语料检索、cutoff、引用和 answer builder 属于公共层；预测字段、规则和参数不得跨 family 共享。
