# T2 Forecasting 行动计划（2026-09-05 起）

截止：Development 到 9 月 28 日；Final（唯一一次正式提交）9 月 29 日 – 10 月 12 日。今天离 Development 结束还有约 3 周。

## 阶段 0 · 准备（第 1 天）

1. 确认账号已在网站上加入/创建 Team（拿到 Team ID 和 Key），否则不能提交也上不了榜。
2. 本地环境：Python 3.11+（用到 `tomllib`）、Docker Desktop。
3. 安装两个包（在 `starter-repos/track2-forecasting-public/` 下）：
   ```bash
   pip install "qfbench2-common @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git@v2.3.1#subdirectory=common"
   pip install .
   ```
4. 阅读顺序：`README.md` → `docs/CONCEPTS.md`（CRPS / variogram / tail 的数值例子）→ `docs/CATEGORIES.md`（F1–F4）→ `docs/SOLVER-PLAYBOOK.md`（组织方反推出的赢法）→ `SUBMISSION_CLI.md`（Docker 合同）。

## 阶段 1 · 跑通参考流水线（第 1–2 天）

目标：不写任何模型代码，先让"提交—评分"闭环转起来。

```bash
cd units/t2-EXAMPLE-ust-curve-1m && bash run_example.sh        # 示例单元端到端
python -m qfbench2_track_forecasting.cli \
  --panels units/t2-EXAMPLE-ust-curve-1m/ \
  --text   units/t2-EXAMPLE-ust-curve-1m/text/ \
  --asof 2024-06-28 --out out/forecast.parquet                  # 参考 CLI（只看数字、不看文本）
python scoring/scoring.py score \
  --card units/t2-EXAMPLE-ust-curve-1m/card.toml \
  --forecast out/forecast.parquet                               # 期望 g0–g3 全部 pass
docker build -t t2-agent . && docker run --rm --network=none t2-agent forecast --help
```

注意：本地拿不到分数（真实结果未公开），只能验证"合规"。准确度只能靠提交到 Development 榜看。

## 阶段 2 · 写一个"能打败随机游走"的统计骨架（第 3–7 天）

在 `qfbench2_track_forecasting/cli.py` 基础上改，不要从零开始。对每张卡：

1. 读 `forecast_spec.json`：`asset_ids`、`horizons`、`target_type`（`level` 还是 `log_return`，直接决定输出是什么量）、`n_draws_min`。
2. 载入面板，取 as-of 当天的 spot；算历史上 h 日变化的标准差（基线宽度）；用 EWMA 估当前波动 regime；检查是否有均值回复。
3. 生成路径：对去均值的日度变化做**平稳块 bootstrap**（块长 5–10 天，天然保留肥尾和自相关），或用 Student-t(ν≈5) 冲击；把"近期高波动窗口"和"全历史"按约 6:4 混合。
4. 多资产 / 多 horizon 卡片：用**一个相关冲击**（协方差来自近期日度变化）同时驱动所有序列；长 horizon = 短 horizon 路径 + 独立延续。绝对不要每个资产独立抽样——variogram 那 30% 就是罚这个的。
5. 抽 2000+ draws（下限 200，多抽 CRPS 更稳），写三个文件。
6. 自检：90% 区间半宽 ≈ 1.6 × horizon 标准差；`log_return` 目标输出的是累计对数收益，不是价格水平。

做完这一步就先提交一次，拿到每张卡的归一化分数（1.0 = 与文本盲基线持平）。这时你应该已经在 1.0 附近。

## 阶段 3 · 接入文本 —— 这才是 T2 的题眼（第 8–18 天）

只允许调组织方托管的开源模型（`MODEL_ENDPOINT` + `MODEL_NAME`，OpenAI 兼容接口，从环境变量读，不要写死）。本地开发时可以自己用 vLLM/Ollama 起一个同类模型替代，正式跑时换成环境变量即可。

让 LLM 读 `/input/text/`（每篇都有日期和 `corpus_index.json`），**只输出三个数值旋钮**，不要让它讲故事：

| 旋钮 | 问题 | 约束 |
|---|---|---|
| Drift（中心） | 文本是否暗示相对随机游走的方向性漂移？ | 赢家普遍只做"温和"漂移：horizon 标准差的一小部分 |
| Width（宽度/尾部） | 文本是否暗示不确定性上升/下降？窗口内有没有离散事件（议息、公投、挂钩）？ | 有事件就放宽并加肥尾 |
| Scenarios（形状） | 是否存在分叉结果（加息 vs 按兵不动）？ | 2–4 个带权情景混合，每个情景独立 center/width |

两条硬规则（来自组织方测得的失败模式）：
- **区分"陈述的"和"推断的"。** 文本明确说了的事实（已发布的数据、已作出的决定）可以收窄分布；从语气推断的只能移动中心，不能收窄。
- **面板和文本矛盾时，保留矛盾。** 不要把整个语料平均成一个"基调"再微调中心；这正是 `units-adversarial/` 里被"加盐"语料击穿的做法。应该放宽或拆成情景，并在 rationale 里写明哪篇文档站哪边。

工程上建议：一个固定 JSON schema 的 prompt（输出 drift_bp、vol_multiplier、scenarios[]、cited_doc_ids[]），温度和 seed 固定（可复现性是硬性要求），每题 token 预算 100 万输入 / 10 万输出。

## 阶段 4 · 消融、校准、按题型调优（第 19–23 天）

1. 提交一版**文本消融**（把语料换成空目录），和完整版逐卡对比——这就是官方要看的 information uplift，也是你判断文本模块有没有帮倒忙的唯一方法。
2. 按 F1–F4 分别看分：F3 主要看 variogram（相关结构），F4 主要看 tail（左尾要够肥，评测集里冲击绝大多数是下行）。
3. 覆盖率检查：跨所有卡，你的 90% 区间应该约 90% 命中；系统性偏窄就整体放宽。
4. 别把练习榜当排名：103 张练习卡里 75 张的答案能从兄弟卡的面板里直接查到，所以练习分只证明管道没坏。绝不要做查表——Final 用的是密封的、更晚的时间窗，查表得 0，而且 g4 类分布检查会把"过于精准的靶心"判为不合规。

## 阶段 5 · 打磨提交物（最后 5 天）

- `forecast_rationale.md`：每个方向性判断都引用 `doc_id`，说明方法和主要不确定性。不计分但必须非空，Verification 阶段人工会看。
- 时间预算：Development 整个提交 12 小时 / 约 100 张卡 ≈ **每卡 400 秒**（含镜像拉取 90–187 秒冷启动）。镜像要小，agent 要快；超时的卡按最差值 4.0 记，所以宁可粗一点也要每张都交。
- 镜像必须带 `LABEL qfbench2.interface_version="2.0"`，`forecast` 在 PATH 上，没有 GPU 也能启动。
- 模型版本、训练截止日期、温度、seed 全部写进提交元数据（`api` 类别用 bootstrap-CI 复现验证）。
- 提交前用 `scoring/scoring.py` 对全部 103 张卡跑一遍 g0–g3。
- Final 每个赛道只有一次机会，没有重交：用 Development 证明容器能无人值守跑完全程。

## 分工建议（如果是 2–3 人团队）

- A：数据/统计引擎（阶段 2）+ 评分与校准脚本。
- B：LLM 文本模块（阶段 3）+ prompt 与消融实验。
- C（或 A 兼）：Docker、时间预算、提交流程、rationale 生成。

## 关键文件速查

| 想知道 | 看 |
|---|---|
| 三个评分项怎么算 | `docs/CONCEPTS.md`、`scoring/scoring.py` |
| 四种题型和文本角色 | `docs/CATEGORIES.md`、`TASK-CATEGORIES.md` |
| 赢家方法论 | `docs/SOLVER-PLAYBOOK.md` |
| Docker/网络/LoRA 规则 | `SUBMISSION_CLI.md` |
| 参考实现 | `qfbench2_track_forecasting/cli.py`、`units/t2-EXAMPLE-ust-curve-1m/run_example.sh` |
| 人工审核看 rationale 的什么 | `docs/RATIONALE-REVIEW.md` |
| 每张卡的目标定义 | `units/<id>/forecast_spec.json`、`forecast_card.md` |
