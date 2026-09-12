# 队友上手指南

Agenthon 2026 · Track 2 (Forecasting) · 队伍 297 Cornfield Chase

这个仓库只装**我们自己写的 agent**。主办方的练习数据和评分器是另一个公开仓库，
单独克隆到旁边——不要把它塞进这个仓库（57 MB，而且它自带 `.git`）。

## 目录应该长这样

```
Agenthon2026/
├── starter-repos/
│   └── track2-forecasting-public/   ← 主办方的，单独克隆
└── t2-agent/                        ← 这个仓库
```

## 1. 装环境

需要 **Python 3.13 及以上**（主办方的工具包用了 `tomllib` 等新特性）。

```bash
mkdir -p ~/Desktop/Agenthon2026/starter-repos && cd ~/Desktop/Agenthon2026/starter-repos
git clone https://github.com/Agenthon-2026/track2-forecasting-public.git

cd ~/Desktop/Agenthon2026
git clone <这个仓库的地址> t2-agent

cd t2-agent
python -m venv .venv && source .venv/bin/activate     # 或用 conda/uv
pip install "qfbench2-common @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git#subdirectory=qfbench2-common"
pip install ../starter-repos/track2-forecasting-public   # 主办方的工具包 + 评分器
pip install -e .                                        # 我们的 agent
```

## 2. 跑一张卡片

```bash
U=../starter-repos/track2-forecasting-public/units/t2-F4-covid-mkt-2020
python -m t2agent.cli --panels $U --text $U/text --asof 2020-02-21 \
  --out /tmp/t2/forecast.parquet --no-text
ls /tmp/t2/     # 必须正好三个文件，多一个第一道门 g0 就判不合规
```

## 3. 跑全部 104 张并打分

```bash
python scripts/build_realized.py          # 先重建本地真值（见下面的说明）
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public \
  --runs runs_base --baseline --realized-dir dev/realized     # 主办方基线，当分母
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public \
  --runs runs_notext --no-text --realized-dir dev/realized     # 我们，不读文件
python scripts/evaluate.py runs_base/summary.csv runs_notext/summary.csv
```

引擎约 0.4 秒/单元，加上评分器全跑一轮几分钟。**分数越低越好**，1.0 = 和基线打平。

要带上文本层（需要一个 OpenAI 兼容的端点，本地用 Ollama）：

```bash
export MODEL_ENDPOINT=http://localhost:11434/v1 MODEL_NAME=qwen2.5:7b
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public \
  --runs runs_text --realized-dir dev/realized
```
7B 模型下约 100 秒/单元，全跑一轮约 3 小时。模型输出会缓存在 `runs_text/_textcache/`，
所以改护栏之后可以秒速重放，不用重新调模型。

## 4. 关于 `dev/`——请认真读

`scripts/build_realized.py` 从**姊妹单元的公开面板**里重建出 104 张练习卡片中 94 张的真实结果
（主办方自己的 README 承认 75/103 的练习答案原样出现在别的单元的面板里）。没有它，本地只能
检查"合不合规"，看不到任何分数。

规矩：

- `dev/` 在 `.gitignore` 和 `.dockerignore` 里，**不要提交，不要打进镜像**。每个人在本地自己生成。
- 只用来看**聚合统计**（整体均值、分族均值、校准诊断），**绝不针对单张卡片的答案调参**。
  那既踩规则第 7 条的边，也毫无意义——最终评测用的是另一个封存的时间窗。
- 主办方的 Team Key 是口令性质的东西，**永远不要写进代码、配置或提交信息**。

## 5. 协作方式

- `main` 保持随时可提交的状态。
- 改动走分支 + PR：`git checkout -b 描述性名字`。
- **任何声称提高了分数的改动，PR 里必须附上前后对比**，格式照 `scripts/evaluate.py` 的输出贴：
  ```
  runs_notext   ALL 0.9148  F1 0.773  F2 0.991  F3 0.829  F4 1.004
  runs_mychange ALL 0.9xxx  ...
  ```
  引擎是确定性的（固定 seed），所以同样的代码任何人跑出来的数字都一样。对不上就说明环境有问题。
- 只在一个半样本上变好的改动多半是过拟合——104 张卡片很容易被调参调出假象。

## 6. 交付格式

提交的是一个 **digest 固定的 linux/amd64 Docker 镜像**，不是代码。完整步骤在 `README.md` 末尾。
本地冒烟测试：

```bash
docker build --build-arg TEXT=off -t t2-agent:smoke .
```

真正推的时候必须带 `--platform linux/amd64 --provenance=false --sbom=false`。
