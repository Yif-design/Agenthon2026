# External task-design references

These references inform task diversity. They do not supply hidden Agenthon tasks or labels.

| Reference | Design lesson used here | Catalog questions influenced |
|---|---|---|
| [Agenthon Track 4 categories](https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/CATEGORIES.md) | Preserve the classification/regression/ranking contract, cutoff-safe frozen corpus, intervals and exact citations; do not treat published families as a complete roster. | All; controls 01, 12, 13, 14, 15, 18 |
| [Agenthon Track 4 training policy](https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/TRAINING-POLICY.md) | Public licensed offline data is allowed with release-time provenance; inference inputs and citations stay inside the supplied task and corpus. | All |
| [M6 Financial Forecasting Competition](https://www.unic.ac.cy/iff/research/forecasting/m-competitions/m6/) | Cross-sectional relative returns, quintile probabilities, repeated origins and overconfidence control. | 19, 20 |
| [Jane Street Real-Time Market Data Forecasting](https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting) | Opaque features, time-forward evaluation, nonstationarity, fat tails and regime shifts. | 06, 08, 19, 20 and transformed schemas |
| [FinQA](https://finqasite.github.io/) | Multi-step numerical reasoning over mixed filing tables and prose. | 02, 03, 04, 07, 09 |
| [FinanceBenchmark methodology](https://financebenchmark.ai/methodology) | Long-document retrieval, verification, multi-document synthesis, numerical reasoning and end-to-end agent tasks. | 01-09 |
| [FinNLP 2026 Shared Task](https://www.finnlp2026sharedtask.info/) | Cross-document financial questions, implicit intent and robust entity/quantity recognition. | 08, 09, 10, 13 and transformed schemas |

The proxy benchmark converts these lessons into prediction tasks. It does not add ordinary document
QA outputs, trading actions or portfolio weights to the Track 4 answer contract.
