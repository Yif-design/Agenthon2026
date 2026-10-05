# Track 4 最小可观测预测模型 V1

> 当前逐题输入白名单和公式以 `family-model-contracts-zh.md` 为准。本文保留总体设计原则。

本规格取代此前需要大量难找参数的重型预测框架，作为第一版实际实现标准。

核心原则：只使用题目直接给定的字段、能够从历史表格确定性计算的统计量，以及文档中一句话就能稳定判断的粗粒度信号。模型不估计 beta、不补全缺失财务数据、不自行生成精确概率，也不负责最终数学计算。

## 1. 允许进入模型的参数

参数只有四类：

```text
given       task row 直接给出的数值或类别
computed    程序从冻结历史表格计算的均值、中位数、趋势等
text_signal 模型从明确文字判断的少量离散信号，必须带引用
missing     找不到；按 neutral 处理并扩大区间
```

第一版不使用 `estimated` 数值参数。模型不能输出诸如“term premium = 18 bps”“估值拥挤度 = 0.7”或“下一季度 NIM 下降 6 bps”这类材料没有明确给出的数字。

## 2. 文本信号统一格式

所有文本判断统一为五档：

```text
-2  strong_negative
-1  negative
 0  neutral_or_unknown
+1  positive
+2  strong_positive
```

每个非零信号必须包含：

```json
{
  "signal": "positive",
  "reason": "Management expects gross margin to improve.",
  "doc_id": "...",
  "quote": "...",
  "span_start": 100,
  "span_end": 180
}
```

判断标准：

- 文档明确陈述改善、增长、上调、充足、下降的风险，才能给正向。
- 文档明确陈述恶化、下降、上升的成本、流动性压力或违约，才能给负向。
- 只有一般风险披露、没有方向、跨期不可比或找不到内容，一律为 0。
- 模型不能因为“公司通常表现很好”或自身常识生成信号。

## 3. 公共预测形式

所有 family 都采用：

```text
point_forecast = baseline_from_given_or_computed_data
               + capped_adjustment_from_simple_signal
```

`capped_adjustment` 必须有上限。文本信号只能轻微修正强基线，不能让一句话把预测推到不合理数值。

材料缺失时：

```text
signal = 0
point_forecast = baseline
interval = wider_interval
```

## 4. 各题型最小模型

### 4.1 EPS beat / miss / inline

**保留参数**

- given：`consensus_eps`、`threshold_pct`。
- text signal：`target_period_earnings_signal`，只判断目标期盈利环境整体偏正、偏负或不明确。

信号只使用容易识别的目标期文字：明确的收入/利润率指引、明确的成本恶化或改善。历史季度 EPS 本身不能直接产生非零信号。

**计算**

```text
signal_scale = signal / 2                         # [-1, 1]
forecast_eps = consensus_eps
             × (1 + 1.25 × threshold_pct × signal_scale)
```

含义：

- `strong_positive` 才足以跨过 beat 阈值。
- `strong_negative` 才足以跨过 miss 阈值。
- 普通正负信号仍落在 inline 区间。
- unknown 直接使用 consensus。

最终标签继续使用官方阈值公式。

### 4.2 EPS 同比方向

**保留参数**

- given：`prior_year_q_eps`。
- text signal：`yoy_earnings_signal`。

信号只判断收入与盈利能力相对上一年是否有明确改善/恶化。若证据只比较上一季度，设为 0。

**计算**

```text
step = max(0.10 × abs(prior_year_q_eps), 0.05)
forecast_eps = prior_year_q_eps + signal × step
```

- signal > 0 → `up`
- signal < 0 → `down`
- signal = 0 时 `forecast_eps = prior_year_q_eps`，并按“只有严格大于才是 up”的定义输出 `down`；不可让模型随机选择。

### 4.3 银行 EPS 同比增速

**保留参数**

- given：`prior_year_q_eps`。
- text signal 只保留三个：
  - `net_interest_income_signal`
  - `credit_cost_signal`，拨备上升记为负向
  - `noninterest_net_signal`，将手续费/交易收入与费用合并判断

缺少某项就记 0。三个信号等权，避免估计未知权重。

```text
combined = clip(nii_signal + credit_cost_signal + noninterest_net_signal, -2, 2)
step = max(0.10 × abs(prior_year_q_eps), 0.05)
forecast_eps = prior_year_q_eps + combined × step
growth_pct = (forecast_eps - prior_year_q_eps) / abs(prior_year_q_eps) × 100
```

不再单独要求 NIM、贷款增速、存款成本、投行收入、税率和回购全部存在。

### 4.4 信用事件

**保留参数**

只识别四个容易从文字确认的旗标：

```text
going_concern_present
liquidity_explicitly_insufficient
covenant_breach_or_payment_default
near_term_debt_without_stated_funding
```

一般性的风险因素、可能发生的违约、已获得 waiver 且当前合规，不能算 breach/default。

**固定概率档位**

```text
明确 payment default / unresolved covenant breach       → 0.85
going concern + 明确流动性不足                         → 0.70
只有 going concern 或明确流动性不足                    → 0.40
只有近端偿债压力                                      → 0.20
没有强风险旗标                                        → 0.05
```

`probability >= 0.5` 输出 `credit_event`，否则输出 `no_event`。

这不是校准后的真实违约概率，只是稳定、透明的分类 score。

### 4.5 财报后异常收益

当前材料缺少分析师预期、估值、期权和市场仓位，因此删除这些参数。

**保留参数**

- given：`flat_threshold_abn_pct`。
- text signal：`explicit_forward_outlook_signal`，只读取明确的前瞻指引改善或恶化。

**计算**

```text
signal = 0            → abnormal return forecast = 0.0，label = flat
signal = +1 or +2     → forecast = +1.25 × flat_threshold，positive_reaction
signal = -1 or -2     → forecast = -1.25 × flat_threshold，negative_reaction
```

只有历史业绩、没有明确前瞻信息时必须为 `flat`。这是低信息题型，不假装进行精确市场反应建模。

### 4.6 国债收益率曲线

删除不可观测的 term-premium 数值、市场隐含路径和训练 beta。

**保留参数**

- given：`maturity_years`、`start_yield_pct`。
- text signal：`policy_direction`，仅为 hawkish / neutral / dovish。
- computed：按期限映射固定 sensitivity bucket。

```text
policy shock: hawkish = +20 bps, neutral = 0, dovish = -20 bps

0-2Y sensitivity     = 1.00
>2-5Y sensitivity    = 0.80
>5-10Y sensitivity   = 0.60
>10Y sensitivity     = 0.40

forecast_bps = policy_shock × sensitivity
```

若 snapshot 明确写出市场已定价与 SEP 的差距，可把 hawkish/dovish 升为 strong，并将 shock 上限提高到 30 bps；否则不允许模型生成额外因子。

### 4.7 CPI 分项

**保留参数**

- given：`latest_published_mom_pct`、component。
- computed：该 component 在 vintage 表中的最近历史中位数。
- text/data signal：只对 gasoline/energy 使用实际汽油价格方向。

```text
一般分项 baseline = 0.7 × latest_mom + 0.3 × recent_component_median
gasoline/energy   = baseline + capped_gas_price_adjustment
```

不再要求模型判断二手车、服装、医疗等没有高频材料支持的特殊 adjustment。它们仅使用自身历史的 persistence/mean reversion。

### 4.8 宏观修订

无需 LLM 数值预测。

**保留参数**

- given：`latest_precutoff_estimate`、series、ref month。
- computed：同 series 历史首次修订的中位数、方向频率和绝对误差。
- text signal：仅识别 benchmark 公告明确说上调还是下调。

```text
revision = historical_median_first_revision
if explicit benchmark direction exists:
    revision = same-sign capped benchmark adjustment
revised_value = latest_estimate + revision
```

### 4.9 国债拍卖

无需 LLM 数值预测。

**保留参数**

- given：tenor、new/reopening、已公告 size（若存在）。
- computed：同 tenor 最近拍卖 BTC 的中位数、最近三场趋势和历史波动。

```text
baseline = weighted_median_or_mean(recent same-tenor BTC)
forecast = baseline + capped_recent_trend
```

只有在本次 size 和同 tenor 历史 size 都明确存在时，才加入一个小幅 size adjustment。indirect bidder 只作为解释，不作为第一版必需参数。

### 4.10 COT 仓位排名

**保留参数**

- given：`trailing_4wk_net_change_pct_oi`、当前 `net_pct_oi`。
- computed：从历史表计算当前拥挤度是否处于极端区间；历史不足时不使用。

```text
forecast_change = trailing_4wk_net_change_pct_oi

if statistically extreme crowding:
    forecast_change *= 0.5
```

第一版不让 LLM 预测选举、FOMC 等事件对每种资产的具体系数。所有市场先得到连续预测值，再统一排序。

## 5. 区间

公开集没有 resolved outcomes，第一版不能声称区间已经校准。

使用简单、可复现的规则：

- 有充分 computed history：使用历史变化的 5%/95% 分位数或 robust scale。
- 只有 given baseline：使用 family 固定宽度。
- text signal 缺失或冲突：宽度乘 1.5。
- 区间始终与 point forecast 使用同一单位。

## 6. V1 删除的参数

第一版明确删除：

- 任意未经训练的回归 beta。
- 模型自行生成的 confidence 小数。
- 无材料支持的 valuation/crowding score。
- 精确 term premium 和市场隐含政策路径。
- 要求所有银行都提供 NIM、贷款、存款、税率和回购的完整 bridge。
- 信用事件中的外部评级数据。
- CPI 每个分项的手工主观 adjustment。
- COT 事件影响系数。

## 7. 实现优先级

```text
第一批：macro revision、auction、CPI、COT
第二批：EPS consensus、EPS YoY、bank EPS、credit event
第三批：rates、post-earnings reaction
```

第一批主要依靠表格计算，最稳定；第二批使用少量文本信号；第三批材料本身信息不足，保持简单基线和宽区间。
