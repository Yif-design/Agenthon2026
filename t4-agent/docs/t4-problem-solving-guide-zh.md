# Track 4 各题型解法与工具设计

> 当前代码实现以 `family-model-contracts-zh.md` 为准。本文保留较完整的领域研究与候选框架，用于理解题目；其中难以从材料稳定取得的参数不再进入运行流程。

本文把 Track 4 官方公开的 11 个 unit、10 个题型族逐一拆成可以实现的解题流程。它不是一份“把答案背下来”的知识库，而是一份运行时决策和计算规格：模型从题目与冻结语料中提取事实，程序使用固定公式、规则或小型统计模型生成预测，再由引用模块把结论绑定到原文片段。

官方明确说明：公开题型只是格式示例，隐藏测试包含更多未公开的 family。因此系统需要两层能力：

1. 已知题型使用专用解题器，提高准确率和稳定性。
2. 未知题型使用通用解题器，至少保证理解目标、正确输出、引用合规并给出合理基线。

## 一、所有问题共用的解题流程

每个 unit 都提供 `task.json`、表格行和冻结语料。最终需要对每个 `entity_id` 输出标签或数值、90% 区间和至少一条可验证引用。

```text
读取 task.json
    ↓
解析 target、labels、单位、cutoff、每行特征
    ↓
识别题型（专用解题器或通用解题器）
    ↓
按 entity 检索且先过滤 doc_date <= cutoff_date
    ↓
模型把证据提取成结构化参数 JSON
    ↓
固定工具计算 point_forecast、label、interval 或 rank
    ↓
引用工具定位支持结论的原文 span
    ↓
逐行校验 → 生成 answer.json
```

### 模型和程序的分工

模型适合负责：

- 理解题目到底预测什么、单位是什么、比较基准是什么。
- 从文档中识别趋势、管理层指引、风险、事件和限定语。
- 把非结构化证据转成规定字段的 JSON。
- 在没有专用题型时生成一份通用预测计划。

固定程序适合负责：

- 阈值、百分比、基点、异常收益等公式。
- 标签合法性、单位换算和数值范围检查。
- 多行统一排序。
- 置信区间生成和 schema 校验。
- 日期截断、文档 ID、字符 span 的精确验证。

不要让 7B 模型直接自由生成整份 `answer.json`。更稳妥的方式是让它只输出少量结构化参数，然后由程序完成计算和格式化。

## 二、公开题目总表

| 公开 unit | 题型族 | 行数 | 输出类型 | 核心工具 |
|---|---|---:|---|---|
| `t4-EXAMPLE-eps-beat` | EPS 相对一致预期 | 1 | 分类 | `solve_eps_consensus` |
| `t4-eps-yoy-2023Q2-mixed` | EPS 同比方向 | 6 | 分类 | `solve_eps_yoy_direction` |
| `t4-eps-growth-2024Q3-banks` | 银行 EPS 同比增速 | 8 | 回归 | `solve_eps_growth` |
| `t4-credit-event-2023` | 12 个月信用事件 | 8 | 分类+概率 | `solve_credit_event` |
| `t4-postearn-20240201-megacap` | 财报后异常收益 | 3 | 分类 | `solve_earnings_reaction` |
| `t4-fomc-curve-20220728` | 国债收益率曲线变化 | 6 | 回归 | `solve_rate_curve` |
| `t4-fomc-curve-20240918` | 国债收益率曲线变化 | 6 | 回归 | `solve_rate_curve` |
| `t4-cpicomp-202410-us11` | CPI 分项 nowcast | 11 | 回归 | `solve_cpi_components` |
| `t4-macrorev-20240930-us6` | 宏观数据修订方向 | 12 | 分类+数值 | `solve_macro_revision` |
| `t4-auction-btc-202411-us7` | 国债拍卖需求 | 7 | 回归 | `solve_auction_demand` |
| `t4-cotpos-202411-us10` | COT 仓位变化排名 | 10 | 排名 | `solve_positioning_rank` |

11 个 unit 对应 10 个 family，因为两道 FOMC 题共用 `rate_curve_cross_section`。

## 二点一、这些计算框架从哪里来

本文中的“计算框架”有三种来源，可信度和用途不同，开发时必须分开：

### A. 官方目标定义和确定性换算

这部分直接来自官方 `task.json`、prompt、row 字段和 `CATEGORIES.md`，应原样实现，不需要模型猜：

- EPS beat/miss/inline 的 consensus、阈值和标签条件。
- EPS 同比方向是目标 EPS 与 `prior_year_q_eps` 的比较。
- EPS 同比增速公式。
- 异常收益是公司收益减 SPY 收益，公开题 flat 阈值为正负 1%。
- 国债题输出收益率变化的基点数，不是最终收益率。
- auction target 是 `total bids tendered / amount accepted`。
- COT target 是净非商业仓位变化占起始 OI 的百分比，并按连续预测值排序。
- 所有任务的 target type、合法标签、单位、cutoff、interval level 和 roster。

这些属于“工具的最终换算层”，只要输入预测值已经产生，结果就是确定的。

### B. 官方提示的预测因子和语料内容

官方 prompt 会明确告诉参赛者应从哪些方向推理，例如银行题提到 NII、拨备、投行业务、费用；信用题提到 liquidity、debt maturity、covenant 和 going concern；auction 题提到历史 BTC、发行规模、new/reopening 和 indirect bidders。

这些说明某类证据是相关的，但不保证每个 entity 的材料都完整包含每一项，也不提供统一数值权重。模型必须允许字段为 `null` 或 `unknown`，检索不到时不能编造。

### C. 我们设计的预测器和启发式分解

文中的 `risk_score`、curve beta、persistence、mean-reversion adjustment、各种 signal 权重和 confidence 都是待实现的工程方案，不是官方公式。它们来自常见领域建模思路，并根据公开题目的提示改造成适合小模型抽取、程序计算的结构。

这些参数需要通过以下方式产生：

1. 能从该 unit 的历史表格计算时，优先现场计算，例如 auction 的 tenor 历史均值、宏观 vintage 的历史修订分布。
2. 能从文档明确提取时，让模型提取事实或方向，同时保存引用。
3. 没有历史数据时，使用我们预先配置的保守先验或简单规则。
4. 将来拿到可评分的开发结果后，再对权重、beta 和误差尺度做校准。

因此目前文档描述的是“候选模型结构”，并不表示这些启发式参数已经经过训练或证明最优。

## 二点二、哪些参数一定有，哪些不一定有

| 题型 | 官方 row 明确给定 | 官方语料明确包含或题目明确要求利用 | 不保证存在、需要提取或估计 |
|---|---|---|---|
| EPS beat | `consensus_eps`、`threshold_pct`、条件公式 | 截止日前公司文件 | 目标 EPS、目标期完整指引、利润率/费用/股数调整 |
| EPS 同比方向 | `prior_year_q_eps`、季度信息 | 最近 10-Q | 目标 EPS、所有经营驱动、一次性项目影响 |
| 银行 EPS 增速 | `prior_year_q_eps` | 银行 10-Q/8-K；prompt 要求关注 NII、拨备、费用等 | 目标 EPS、各驱动的数值变化和权重 |
| 信用事件 | 公司、行业、CIK | SEC 文件；prompt 指定偿债能力信号 | 完整财务比率、评级数据、风险权重、真实概率 |
| 财报后反应 | SPY、event window、flat 阈值、财报前股价 | 截止日前 SEC 文件 | 一致预期、估值拥挤度、期权信号、最终异常收益 |
| 国债曲线 | maturity、`start_yield_pct` | FOMC、SEP 或宏观快照，具体随 unit 变化 | 市场完整定价、factor shock、各期限 beta、最终 bps |
| CPI 分项 | 上月首次公布 MoM、component、月份 | vintage 表、BLS release；公开题另有汽油价格 | 每个分项完整高频数据、季调影响、persistence 权重 |
| 宏观修订 | 当前估值、vintage、ref month、解决日期 | ALFRED vintage 表；公开题另有 BLS benchmark 公告 | 下一次修订值、公告对各行的精确调整量 |
| 国债拍卖 | tenor、日期、new/reopening；部分行有 size | 各 tenor 历史 auction 表和公告信息 | row 中并非每行都有 size；需求调整权重和最终 BTC |
| COT 排名 | 起始净仓位、OI、净仓位占比、过去 4 周变化 | COT 历史表和宏观快照 | 未来仓位变化、事件影响系数和最终排序值 |

“语料明确包含”也只对当前公开 unit 成立，不能推导为隐藏题型的永久保证。隐藏题目只保证遵守共同输入输出契约，不保证沿用公开题的字段名或证据种类。

程序应把参数分成四种状态，而不是强迫每个字段都有值：

```text
given       题目 row 直接提供
computed    从 row 或历史表格确定性计算
extracted   从语料提取，必须关联引用
estimated   模型或先验估计，带来源和不确定性
missing     材料中找不到，触发 fallback
```

每个专用解题器都应声明 `required_fields` 和 `optional_evidence_fields`。只有官方契约中的字段才能列为 required；NIM、going-concern、valuation setup 等均应是 optional，缺失时降低置信度并扩大区间，而不是让模型补全一个看似合理的值。

## 二点三、自建预测框架的来源与参数可得性审计

下面专门审计第三类框架。这里的“可得性”指公开 unit 的冻结材料，不代表隐藏题一定相同。

### 1. EPS consensus anchor + 文本修正

**来源**：分析师一致预期本身就是 earnings surprise 的常用基准；当一致预期不可用时，季度 EPS 预测常使用 seasonal random walk 或 ARIMA 一类时间序列基线。我们的方案将题目给出的 consensus 作为 anchor，再让模型根据收入、利润率、费用和股数证据做小幅修正。

**不是现成模型的部分**：从某一句“服务收入增长”映射成 EPS 增加多少，没有官方或通用固定系数；目前的修正幅度和历史 EPS 防错规则是我们自己设计的。

**参数可得性**：

- consensus 和 threshold：公开 beat 题直接给，容易。
- 历史 EPS、收入和利润率：10-Q/8-K 通常能找到，容易到中等。
- 下一季度明确指引：不一定有，且 SEC 文档可能只给定性表述，中等到困难。
- 税率、股数、分部利润的完整 bridge：经常不完整，困难。

**结论**：适合作为稳定 baseline；适合预测分类阈值附近的方向，不足以单靠当前材料做精确 EPS 建模。可实施性：中等。

### 2. EPS 同比 seasonal baseline + operating bridge

**来源**：同季度上年 EPS 是官方给定基准，也对应季度盈利预测中常见的 seasonal persistence 思路。operating bridge 是会计驱动分解：收入、利润率、费用、税率、一次性项目和稀释股数共同决定 EPS。

**不是现成模型的部分**：不同公司各驱动对目标 EPS 的数值权重需要历史样本或完整财务模型；当前 unit 只有一份最近 10-Q，不能可靠估计公司级回归系数。

**参数可得性**：prior-year EPS 明确给定；历史损益项目在六份公开 10-Q 中都较丰富；目标季度指引和完整 bridge 不保证存在。

**结论**：方向分类比精确点预测更现实。使用 prior-year EPS 起步，文本只决定有限调整。可实施性：方向中高，精确 EPS 中低。

### 3. 银行 earnings bridge

**来源**：不是某个单独命名的预测模型，而是银行损益表结构：NII/NIM、信贷拨备、非息收入、非息费用、税和股数决定净利润与 EPS。官方 prompt 也明确要求从这些驱动推理。

**不是现成模型的部分**：`estimate_bank_eps()` 的权重必须由历史银行季度样本训练，或者使用可解释的弱规则；不能凭领域词典直接得到准确 EPS。

**参数可得性**：公开语料覆盖最好的一类。12 份银行 10-Q/8-K 均能检索到 NII、NIM、provision、noninterest expense 或 investment banking 等相关术语。但找到术语不等于拿到下一季度预测值，目标季度的量化指引仍然稀缺。

**结论**：驱动方向容易找，驱动幅度和目标 EPS 难。初版应做方向性 bridge，后续若能建立跨季度历史表再训练回归。可实施性：中等。

### 4. 信用事件 risk score

**来源**：财务比率部分借鉴 Altman Z-score 一类公司困境模型；going-concern、liquidity、debt maturity、covenant breach/default 等文本特征直接来自官方 prompt 和信用分析惯例。

**重要限制**：不能声称当前实现的是 Altman Z-score。标准 Z-score 需要一组完整、定义严格的财务比率和市场价值变量；公开 unit 只有每家公司一份 SEC 文件，未保证所有比率及市场价值都可得。我们的 `risk_score` 是文本和部分财务特征的自建打分器。

**参数可得性**：8 份公开文件全部能找到部分 liquidity/debt/covenant/default 类语言，但每家公司信号完整度不同。评级数据通常没有，真实事件概率也无法从 8 行样本校准。

**结论**：做高风险/低风险排序或分类有希望；输出精确且校准的 12 个月概率较难。应使用强规则识别 going concern、实际 breach/default 和短期现金缺口，概率只作保守映射。可实施性：分类中等，概率校准低。

### 5. earnings surprise → abnormal return

**来源**：event study 使用 benchmark-adjusted abnormal return；earnings-surprise 和 post-earnings-announcement drift 文献表明 EPS/营收 surprise 与异常收益有关。我们的框架进一步加入 guidance surprise 和 pre-event expectation setup。

**重要限制**：PEAD 主要研究公告后的漂移，公开题预测的是紧接公告的一日反应，两者不是同一个预测目标。要预测一日反应，通常还需要当期 analyst consensus、收入预期、guidance expectation、期权隐含波动率和财报前估值/仓位。

**参数可得性**：公开语料只有三家公司较早的 SEC 文件；没有当期 analyst consensus、期权数据或完整市场预期。`valuation_setup` 和 `crowded_positive` 等字段在当前材料中基本无法可靠提取。

**结论**：现有五因子框架理论上合理，但与材料不匹配。初版应删掉无法观测的假精确参数，改成“公司基本面趋势 + 低置信度 prior”，并让 `flat` 成为有竞争力的基线。可实施性：低。

### 6. yield curve factor decomposition

**来源**：期限结构的预期假说和 affine term-structure 模型通常把收益率理解为预期短端利率路径加期限溢价；宏观新闻、通胀和增长会改变这两部分。前端对政策路径更敏感、长端更受长期预期和期限溢价影响，也由官方 prompt 明确提示。

**重要限制**：真正估计 affine model 需要较长的收益率历史、OIS/联邦基金期货或调查预期，并要估计 latent factors 和 maturity loadings。公开 unit 只有起始曲线、FOMC/SEP 与一个宏观快照，不足以估计完整模型。因此文档中的 `beta_policy` 等不是已估系数，只是曲线平滑的规则参数。

**参数可得性**：起始收益率、期限和政策文字容易；市场已定价路径有时在 snapshot 中出现；期限溢价和成熟的 beta 不保证有。

**结论**：使用 front/belly/long 三档 sensitivity 和共同 factor shock 做一致性约束，不要冒充 affine model。可实施性：中低。

### 7. CPI persistence + component adjustment

**来源**：Cleveland Fed inflation nowcasting 使用少量混频数据，包括近期 CPI/PCE、日频油价和周频汽油价格；核心通胀主要依赖近期历史，汽油分项使用当前油价和汽油价格再做季调。我们的 persistence + adjustment 继承了这个基本结构。

**重要限制**：Cleveland Fed 的公开说明主要覆盖 headline/core、food、gasoline，不等于能直接预测题目中的 11 个详细分项。shelter、used vehicles、apparel、medical care 需要各自高频数据或更长历史，而当前 unit 没有全部提供。

**参数可得性**：上月分项 MoM、历史 component vintage、BLS release 和汽油价格明确存在。汽油、headline/core 的输入较好找；其他分项只有历史惯性，component-specific adjustment 较难。

**结论**：使用分项 AR/persistence baseline；只对有明确高频证据的 gasoline/energy 做较强调整，其余维持小幅均值回归。可实施性：汽油和 aggregate 中高，其余中低。

### 8. macro revision empirical prior

**来源**：real-time vintage forecasting。对同一 series 比较连续 vintages，直接估计首次修订的平均值、中位数、方向频率和波动，再叠加 benchmark announcement 的已知影响。

**不是现成模型的部分**：如何给近期 vintages 加权、benchmark adjustment 如何分配到各月份，仍需我们设定；但核心统计量可直接从材料计算，不依赖模型想象。

**参数可得性**：公开 unit 给出六个系列的 ALFRED vintage 表和 BLS benchmark 公告，七份材料均包含 revision/vintage 信息。这是参数最容易找的一类。

**结论**：应以确定性 parser + 统计模型为主，LLM 只解释公告。可实施性：高。

### 9. auction tenor baseline + adjustments

**来源**：bid-to-cover 的历史水平具有 tenor-specific 分布；发行规模、new/reopening、indirect bidder participation 和近期拍卖结果是官方 prompt 指定的因子。公开研究和政府分析也会用 offering amount 等变量对 BTC 建立计量模型。

**不是现成模型的部分**：我们尚未训练 size/new-issue/indirect 的系数。简单相加的 adjustment 只是待验证的线性 baseline。

**参数可得性**：公开 unit 为七个 tenor 各提供约一年 TreasuryDirect 历史表，另有 upcoming announcement。历史 BTC、accepted/tendered、indirect 和 reopening 信息容易解析。部分 row 的 offering size 为 `null`，需要去 upcoming 文档提取；若公告里也没有，则不能强填。

**结论**：用每个 tenor 的滚动中位数或指数加权均值就能得到很强的第一版；有足够历史行后可拟合小型 ridge/robust regression。可实施性：高。

### 10. COT momentum/reversal + cross-asset factors

**来源**：CFTC 定义并发布 noncommercial long/short、open interest 和周变化；期货 time-series momentum 文献发现投机者仓位与趋势有关。我们提出用近期仓位动量、极端拥挤后的均值回归和事件因子预测未来仓位变化。

**重要限制**：没有一个公认稳定的公式能从当前 COT 精确预测五周后的 COT 变化。momentum 和 reversal 可能在不同市场、不同 regime 下方向相反；跨资产事件系数也需要历史样本训练。

**参数可得性**：10 个市场的起始净仓位、OI 和 trailing 4-week change 直接给定；各市场历史表和宏观快照存在。训练 asset-specific 系数所需的长历史有限。

**结论**：trailing change 是清楚的 baseline；可加入受限的 crowding mean-reversion，但事件影响保持小权重。连续数值预测后再统一排序。可实施性：中等偏低。

### 11. 置信区间模型

**来源**：理想做法是用每个 family 的历史 out-of-sample residual 分布校准 90% 区间。

**参数可得性**：公开 practice units 不提供 resolved outcomes，因此现在没有 residual 可以校准。当前 `sigma_family` 和区间 multiplier 都只能是启发式。

**结论**：这是目前所有框架共同的薄弱点。公开集只能检查区间结构是否合法，不能证明覆盖率正确。需要未来开发标签、组织方反馈或合成 backtest 才能校准。

### 方法来源链接

- EPS analyst consensus、ARIMA 和 seasonal random walk 比较：https://www.sciencedirect.com/science/article/pii/S0882611020300675
- Altman bankruptcy ratio model：https://doi.org/10.1111/j.1540-6261.1968.tb00843.x
- Federal Reserve three-factor nominal term-structure model：https://www.federalreserve.gov/data/three-factor-nominal-term-structure-model.htm
- Cleveland Fed inflation nowcasting：https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
- Treasury auction results中的 BTC 计算示例：https://www.treasurydirect.gov/instit/annceresult/press/preanre/
- CFTC COT 字段定义：https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/deanexplanatory.html
- Time-series momentum 与投机者 CFTC 仓位：https://doi.org/10.1016/j.jfineco.2011.11.003

## 三、逐题型解法

### 1. EPS 相对一致预期：beat / miss / inline

**题目要预测什么**

预测目标季度的 diluted EPS，并与题目给出的 `consensus_eps` 和 `threshold_pct` 比较。公开例题为 Apple Q2 FY2024，阈值是 5%。

**输入**

- 公司和目标季度。
- `consensus_eps`。
- `threshold_pct`。
- 截止日前的 10-Q、8-K、管理层指引等语料。

**应检索的证据**

- 下一季度营收或毛利率指引。
- 分部增长、成本、费用、税率、回购和稀释股数。
- 最近同季 EPS 或最近季度 EPS，只能作为基准，不能当目标答案。
- 分析师预期若已作为表格特征提供，直接使用表格值。

**模型提取参数**

```json
{
  "revenue_growth_signal": "up|down|flat|unknown",
  "margin_signal": "up|down|flat|unknown",
  "expense_signal": "up|down|flat|unknown",
  "share_count_signal": "up|down|flat|unknown",
  "forecast_eps": 1.53,
  "confidence": 0.62,
  "evidence": []
}
```

**计算**

```text
beat_threshold = consensus_eps × (1 + threshold_pct)
miss_threshold = consensus_eps × (1 - threshold_pct)

forecast_eps > beat_threshold  → beat
forecast_eps < miss_threshold  → miss
其他                           → inline
```

**需要实现的工具**

- `extract_eps_drivers()`：从文档提取营收、利润率、费用、税率和股数信号。
- `forecast_eps()`：用一致预期作锚，根据证据作有限调整。
- `classify_eps_vs_consensus()`：严格按阈值计算标签。
- `validate_eps_period()`：防止把历史季度 EPS 误当目标季度 EPS。

**保守基线**

证据不足时令 `forecast_eps = consensus_eps`，标签为 `inline`。这是合理降级，不是最终的高分策略。

### 2. EPS 同比方向：up / down

**题目要预测什么**

预测目标季度 GAAP diluted EPS 是否高于同一财年上一年的同季度。这里比较的是同比，不是环比。

**输入**

- `prior_year_q_eps`。
- 目标季度和 prior-year quarter。
- 最近一期财报、管理层指引和经营趋势。

**解题步骤**

1. 确认目标季度和同比基准季度。
2. 从最近财报提取营收、毛利率、费用、税率、一次性项目和股数变化。
3. 以 `prior_year_q_eps` 为起点估计目标 EPS，而不是复制最近季度 EPS。
4. 用公式直接得到 `up` 或 `down`。

```text
forecast_eps > prior_year_q_eps → up
否则                            → down
```

**需要实现的工具**

- `extract_eps_drivers()`：与第一题复用。
- `estimate_target_quarter_eps()`。
- `classify_eps_yoy_direction()`。
- `detect_one_off_items()`：识别减值、税收收益、重组费等一次性项目。

当 prior-year EPS 接近 0 或为负时，不要用百分比变化判断方向，直接比较每股金额。

### 3. 银行 EPS 同比增速

**题目要预测什么**

预测银行目标季度 GAAP diluted EPS 相对上年同季度的增长百分比。

**为什么银行需要单独处理**

普通企业常从销量、价格、毛利率和费用推 EPS；银行的关键驱动不同，主要是：

- 净利息收入 NII 和净息差 NIM。
- 贷款和存款规模、存款成本。
- 信贷损失拨备 provision。
- 投行、交易、资管、卡业务等非息收入。
- 非息费用。
- 回购带来的摊薄股数变化。

**模型提取参数**

```json
{
  "nii_signal": "up|down|flat|unknown",
  "nim_signal": "up|down|flat|unknown",
  "provision_signal": "up|down|flat|unknown",
  "fee_signal": "up|down|flat|unknown",
  "expense_signal": "up|down|flat|unknown",
  "share_count_signal": "up|down|flat|unknown",
  "forecast_eps": 0.91,
  "confidence": 0.55,
  "evidence": []
}
```

**计算**

```text
eps_yoy_growth_pct =
    (forecast_eps - prior_year_q_eps) / abs(prior_year_q_eps) × 100
```

**需要实现的工具**

- `extract_bank_earnings_drivers()`。
- `estimate_bank_eps()`：最初可用规则加权；有训练样本后再换成回归模型。
- `eps_yoy_growth_pct()`。
- `stabilize_growth_near_zero()`：基准 EPS 很小时扩大区间并限制极端点预测。

初版不必假装能完整重建银行损益表。以 prior-year EPS 为锚，用 NII、拨备、费用和手续费的方向作有限调整，会比让 7B 模型凭空报一个增长率稳定。

### 4. 12 个月信用事件

**题目要预测什么**

预测截止日后 12 个月内是否发生官方定义的信用事件：Chapter 11/7、payment default 或评级机构认可的 distressed debt exchange。普通的经营困难、股价下跌或风险披露本身不等于信用事件。

**重点证据**

- 现金和可用授信。
- 经营现金流、持续亏损和现金消耗速度。
- 未来 12 个月债务到期墙。
- covenant headroom、waiver、breach、default 用词。
- going-concern 意见。
- 债务交换、重组谈判、评级下调。

**建议结构化特征**

```json
{
  "liquidity_months": null,
  "liquidity_signal": "healthy|strained|severe|unknown",
  "near_term_debt_wall": "yes|no|unknown",
  "covenant_status": "clear|waiver|breach|default|unknown",
  "going_concern": "yes|no|unknown",
  "distressed_exchange_signal": "yes|no|unknown",
  "rating_signal": "positive|stable|negative|unknown",
  "credit_event_probability": 0.18,
  "evidence": []
}
```

**工具计算方式**

初版可以采用可解释的风险分数：

```text
score = liquidity_weight
      + maturity_weight
      + covenant_weight
      + going_concern_weight
      + exchange_or_rating_weight

probability = calibrate(score)
label = credit_event if probability >= 0.5 else no_event
```

公开题没有另外给出概率转标签的阈值，因此初版使用 0.5，并保证概率和标签方向一致。若隐藏题目的 prompt 或 card 明确给出其他阈值，则以题目定义为准。

**需要实现的工具**

- `extract_credit_signals()`。
- `credit_risk_score()`。
- `calibrate_credit_probability()`。
- `distinguish_waiver_breach_default()`：这是容易误判的关键规则。

由于信用事件稀少，缺少强烈违约信号时基线应偏向 `no_event`，但不能因此忽略明确的 going-concern、短期现金耗尽或实际 breach。

### 5. 财报公布后股价反应

**题目要预测什么**

预测财报公布后一个交易日的市场调整后异常收益：

```text
abnormal_return = company_total_return - SPY_return
```

公开题中：

```text
abnormal_return > +1% → positive_reaction
abnormal_return < -1% → negative_reaction
否则                  → flat
```

正负 1% 指的是相对 SPY 的异常收益区间，不是股票原始涨跌幅。

**解题逻辑**

1. 估计市场预期，而不只判断公司基本面好坏。
2. 预测 EPS、营收和指引相对预期的 surprise。
3. 判断财报前估值和拥挤程度：预期很高时，好财报也可能下跌。
4. 综合得到异常收益点预测，再用题目阈值转为标签。

**模型提取参数**

```json
{
  "eps_surprise": "positive|negative|neutral|unknown",
  "revenue_surprise": "positive|negative|neutral|unknown",
  "guidance_surprise": "positive|negative|neutral|unknown",
  "expectation_setup": "high|low|neutral|unknown",
  "abnormal_return_forecast_pct": -1.6,
  "confidence": 0.44,
  "evidence": []
}
```

**需要实现的工具**

- `extract_earnings_expectation_signals()`。
- `score_earnings_surprise()`。
- `forecast_abnormal_return()`。
- `classify_reaction()`。

公开语料只有截止日前的 SEC 文件，因此不能假设能获得实时期权隐含波动率、卖方明细预期或财报后的价格。这类题天然不确定，区间应比 EPS 题更宽。

### 6. FOMC 区间内国债收益率曲线变化

**题目要预测什么**

对 6 个期限分别预测从 cutoff close 到 resolution close 的收益率变化，单位为基点：

```text
yield_change_bps = (ending_yield_pct - start_yield_pct) × 100
```

输出的是“变化多少 bps”，不是最终收益率。

**主要驱动**

- 预期政策路径相对市场已定价路径的重新定价。
- FOMC statement 和 SEP 的偏鹰/偏鸽差异。
- 通胀、就业、增长信号。
- 期限溢价和供给压力。
- 曲线位置：前端对政策路径更敏感，长端更受长期通胀、增长和期限溢价影响。

**计算框架**

```text
change(maturity) =
    beta_policy(maturity) × policy_repricing
  + beta_inflation(maturity) × inflation_signal
  + beta_growth(maturity) × growth_signal
  + beta_term_premium(maturity) × term_premium_signal
```

初版可按 front / belly / long 三个 bucket 设置固定 beta，并要求同一题内 6 个期限共同推理，防止每行各自胡乱生成。

**需要实现的工具**

- `extract_fomc_regime()`。
- `maturity_bucket()`。
- `forecast_curve_factors()`。
- `apply_curve_betas()`。
- `curve_shape_sanity_check()`：检查期限间是否存在没有证据支持的剧烈锯齿。

两道公开 FOMC 题应复用同一个工具，差别由语料中当时的政策环境决定，不能按日期写死答案。

### 7. CPI 分项月环比 nowcast

**题目要预测什么**

预测指定月份各 CPI-U 分项首次公布的季调后月环比百分比。输入给出上一月首次公布值。

**不能用一个统一公式处理所有分项**

- 汽油/能源：高频汽油价格，注意季调和传导。
- shelter：OER、租金具有惯性和滞后。
- used vehicles：波动大，需要车辆价格或近期分项趋势。
- apparel：噪声较高，均值回归更明显。
- medical care：通常较稳定，但保险方法变化可能造成跳变。
- headline/core：应由主要分项加权思考，不能机械复制某一个分项。

**基本形式**

```text
forecast_component_mom =
    persistence × latest_published_mom
  + component_specific_adjustment
  + mean_reversion_adjustment
```

**需要实现的工具**

- `classify_cpi_component()`。
- `extract_component_driver()`。
- `forecast_energy_component()`。
- `forecast_sticky_component()`。
- `forecast_volatile_component()`。
- `forecast_cpi_aggregate()`。

证据完全不足时，carry forward 上月值是官方基线式的合理退化；高波动分项需要更宽区间。

### 8. 宏观指标下一次修订方向

**题目要预测什么**

预测统计机构下一次发布时，会把“同一个历史参考月份”的当前估值向上还是向下修订，并同时预测修订后的数值。

这不是预测下个月经济活动，也不是预测当前最新值。

**解题步骤**

1. 锁定 `series_id + ref_month + resolving_release_date`。
2. 读取 `latest_precutoff_estimate` 和对应 vintage。
3. 从 ALFRED vintage 表计算该系列历史首次修订的方向、均值和波动。
4. 检查 annual benchmark、季调更新或更完整源数据公告。
5. 预测 revision amount，再加回当前估值得到 revised value。

```text
revision_forecast = historical_revision_prior + announced_adjustment
revised_value = latest_precutoff_estimate + revision_forecast
label = up if revision_forecast > 0 else down
```

**需要实现的工具**

- `parse_vintage_table()`。
- `estimate_revision_prior()`：按 series 计算历史修订偏差和方差。
- `extract_benchmark_adjustment()`。
- `forecast_revised_value()`。
- `classify_revision_direction()`。

这是最适合统计工具的题型之一：历史 vintage 表的计算应由程序完成，模型只解释 benchmark 公告和特殊因素。

### 9. 美国国债拍卖 bid-to-cover

**题目要预测什么**

预测已经公告的国债 coupon auction 的 bid-to-cover ratio：

```text
bid_to_cover = total_bids_tendered / amount_accepted
```

它不是拍卖收益率、tail、indirect bidder 比例或 dealer takedown，后面几项只是辅助信号。

**解题步骤**

1. 按 tenor 分组，不要把 2Y 和 30Y 的历史分布混在一起。
2. 计算每个 tenor 最近若干场的中位数、加权均值、趋势和波动。
3. 区分 new issue 和 reopening。
4. 根据本次发行规模相对历史规模作供给调整。
5. 用 indirect bidder、tail 和利率吸引力作小幅调整。

```text
forecast_btc =
    recent_tenor_baseline
  + trend_adjustment
  + new_reopening_adjustment
  + size_adjustment
  + demand_quality_adjustment
```

**需要实现的工具**

- `parse_auction_history()`。
- `tenor_auction_baseline()`。
- `auction_size_adjustment()`。
- `auction_demand_adjustment()`。
- `forecast_bid_to_cover()`。

无证据时不应该所有 tenor 都固定填 2.5；应优先用各 tenor 自己的历史中位数。

### 10. CFTC COT 仓位变化排名

**题目要预测什么**

预测 10 个期货市场从起始 COT 周到目标 COT 周的非商业净仓位变化，占起始 open interest 的百分比，然后按该数值从大到小排名。

```text
change_pct_oi =
    (target_net_noncommercial - starting_net_noncommercial)
    / starting_open_interest × 100
```

**关键规则**

- `point_forecast` 必须填预测的 `change_pct_oi`，不能填 rank 整数。
- 最终 rank 由所有行的 `point_forecast` 统一排序得出。
- 必须使用相对 open interest 的变化，不能比较原始合约数量。

**解题步骤**

1. 读取当前净仓位占 OI、过去 4 周变化和拥挤程度。
2. 从宏观快照识别美元、利率、风险偏好、商品供需等共同因子。
3. 判断 event window 中选举、FOMC 等事件对不同资产的方向影响。
4. 先逐市场预测连续数值，再执行一次全局排序。

**需要实现的工具**

- `extract_positioning_features()`。
- `positioning_momentum_reversal_model()`。
- `apply_cross_asset_event_factors()`。
- `rank_point_forecasts()`。
- `validate_rank_permutation()`。

保守基线可以使用题目给出的 `trailing_4wk_net_change_pct_oi` 作为连续点预测，再统一排序。

## 四、置信区间怎么生成

官方要求每一行都有规定 level 的区间。区间必须和 `point_forecast` 使用相同单位。

初版建议按题型维护历史误差尺度：

```text
lo = point_forecast - z × sigma_family × uncertainty_multiplier
hi = point_forecast + z × sigma_family × uncertainty_multiplier
```

其中：

- `z` 由题目要求的 interval level 决定。
- `sigma_family` 来自该类问题的回测误差；没有结果集时先用经验尺度。
- `uncertainty_multiplier` 由证据缺失、目标跨度和异常状态决定。

分类题仍然需要区间。区间覆盖对应的连续点预测，例如 EPS、信用事件概率或异常收益，而不是对标签本身给区间。

官方 scorer 主要惩罚实际覆盖率偏离目标覆盖率，不奖励无限窄，也不应通过无限宽区间长期获得优势。因此后续必须利用可获得的开发结果校准每个 family 的误差尺度。

## 五、引用怎么做才不会被 faithfulness gate 拒绝

每条引用必须同时满足：

1. `doc_id` 出现在 unit 的 manifest 中。
2. 文档日期不晚于 `cutoff_date`。
3. `span_start` 和 `span_end` 精确指向原文字符位置。
4. 引文支持本行预测所使用的关键前提。
5. 引文属于当前 entity，而不是拿另一家公司或另一分项的证据复用。

正确的 claim 应描述证据本身和它支持的方向，例如“管理层预计下一季度毛利率为 X–Y，支持利润率保持稳定”。不要声称引文本身证明“EPS 必然为 1.53”；财报前文档通常只能支持驱动因素，数值预测是模型和工具的推断结果。

需要实现：

- `filter_documents_by_cutoff()`。
- `retrieve_entity_spans()`。
- `locate_exact_span()`。
- `check_claim_span_consistency()`。
- `validate_manifest_doc_id()`。

## 六、隐藏题型的通用解题器

不能把系统写成 `if family in 10_known_families else crash`。官方说 `family` 只是描述字段，不是封闭 enum。

### 通用题型描述

先让模型只生成下面的计划：

```json
{
  "target_type": "classification|regression|ranking",
  "target_name": "string",
  "target_units": "string|null",
  "legal_labels": [],
  "comparison_baseline": "string|null",
  "row_level_or_cross_row": "row|cross_row",
  "candidate_baseline_field": "string|null",
  "important_features": [],
  "retrieval_queries": [],
  "calculation_plan": "string",
  "range_constraints": {},
  "uncertainty_level": "low|medium|high"
}
```

程序再执行通用流程：

- classification：生成合法标签，同时保留可解释的连续 score 或 point forecast。
- regression：从表格中的 prior/latest/baseline 值起步，根据证据做小幅调整。
- ranking：先预测连续指标，再跨行排序。
- 找不到可靠方向时，优先使用 row 中明确给出的最近值或历史均值作基线。
- 无论预测质量如何，都必须保证 roster、schema、interval、claims 和截止日期全部合法。

### 通用工具

- `infer_task_contract()`。
- `select_baseline_feature()`。
- `extract_generic_directional_signals()`。
- `generic_numeric_forecast()`。
- `generic_classification_forecast()`。
- `generic_ranking_forecast()`。

## 七、建议的代码结构

```text
t4agent/
  taskio.py                 读取 task、rows、card、manifest
  router.py                 已知 family 路由 + 未知 family 分析
  retrieve.py               截止日期过滤、按 entity 检索、span 定位
  extract.py                统一的模型 JSON 提取接口
  family_specs.py           每个 family 的目标、字段、工具和约束
  intervals.py              按 family 生成与校准区间
  citations.py              引用构造和一致性检查
  answer_builder.py         统一生成 answer.json
  validate.py               schema、roster、单位、日期、rank 检查
  tools/
    eps.py
    credit.py
    market_reaction.py
    rates.py
    cpi.py
    macro_revision.py
    auction.py
    positioning.py
    generic.py
```

## 八、开发顺序

建议按可复用性和确定性排序：

1. 先完成公共底座：task 解析、cutoff 过滤、检索、结构化提取、引用、校验和答案构造。
2. 完成三类 EPS 工具，因为它们共享大量字段与推理。
3. 完成宏观修订和拍卖工具，这两类最适合用表格统计得到稳定基线。
4. 完成 CPI 和曲线工具，它们需要跨行一致性与分项规则。
5. 完成信用事件和财报反应，它们更依赖语义判断和概率校准。
6. 完成 COT 连续预测与全局排名。
7. 最后实现隐藏题型通用解题器，并用修改 family slug、字段名和单位的方式做鲁棒性测试。

每完成一个 family，都至少验证四件事：参数提取 JSON 合法、计算公式单测通过、官方 smoke verifier 通过、没有引用 post-cutoff 文档。

## 九、知识库应该存什么

知识库主要存“方法知识”，不要提前存公开题目的答案：

- 每种 target 的定义、单位和常见误区。
- 各领域的驱动因素词典，例如银行 NIM/拨备、信用 covenant/default、CPI 分项驱动。
- 公式和计算规则。
- 检索 query 模板和证据优先级。
- 参数抽取 schema。
- 置信区间和校准方法。

运行时的公司财报、FOMC 文件、CPI vintage、拍卖历史等属于每个 unit 的冻结证据，不应混入永久知识库。它们应在运行时按 unit 建索引，并在检索前严格执行 cutoff 过滤。

## 十、最终系统的判断原则

这个比赛不是让模型在 4K 或更长上下文里一次性“想出答案”。稳定方案是：

```text
小模型负责理解和抽取
+
领域方法库负责告诉它该找什么
+
固定工具负责计算和约束
+
通用解题器处理未见题型
+
引用与 schema 校验保证答案有资格被评分
```

公开题型专用工具负责争取准确率；通用解题器负责避免隐藏题型完全失效；公共引用和验证层则决定输出能否进入评分。

## 官方依据

- `track4-analysis-public/README.md`
- `track4-analysis-public/docs/CATEGORIES.md`
- `track4-analysis-public/docs/CONCEPTS.md`
- `track4-analysis-public/docs/AUTHORING-GUIDE.md`
- `track4-analysis-public/units/*/task.json`
