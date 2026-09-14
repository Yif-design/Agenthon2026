# Agenthon 2026 — 队伍 297 Cornfield Chase

NeurIPS 2026 Competition Track · [agenthon.net](https://www.agenthon.net/)

队员：Yefei Zhang · Joe Zhou（队长）· Haotian Yi

## 仓库结构

每个赛道一个顶层目录，各自独立——自己的依赖、自己的 Dockerfile、自己的 SETUP.md。
互不影响，可以并行开发。

```
Agenthon2026/
├── README.md              ← 这个文件
├── t1-agent/              ← T1 Coding      （verb: solve）    待建
├── t2-agent/              ← T2 Forecasting （verb: forecast） ✅ 进行中
├── t3-agent/              ← T3 Simulation  （verb: simulate） 待建
├── t4-agent/              ← T4 Analysis    （verb: analyze）  待建
├── docs/                  ← 主办方的规则、指南、资源索引（从官网存下来的）
└── starter-repos/         ← 主办方的 5 个官方仓库（不在 git 里，见下）
```

**新建一个赛道**：照着 `t2-agent/` 的结构来——`<track>agent/` 放会打进镜像的代码，
`scripts/` 放只在本地跑的工具，`Dockerfile` + `SETUP.md` 放根目录。

## 环境准备（所有赛道通用）

主办方的仓库**不在这个 git 里**（307 MB，且自带 `.git`，嵌套会出问题）。
克隆完这个仓库之后，自己在旁边拉一份：

```bash
cd ~/Desktop/Agenthon2026        # 也就是这个仓库的根目录
mkdir -p starter-repos && cd starter-repos
git clone https://github.com/Agenthon-2026/Agenthon2026-public.git
git clone https://github.com/Agenthon-2026/track2-forecasting-public.git
# 需要哪个赛道就拉哪个：track1-coding-public / track3-simulation-public / track4-analysis-public
```

需要 **Python 3.13 及以上**（主办方的工具包用了 `tomllib`）。

各赛道的具体装法和跑法看它自己的 SETUP：**[t2-agent/SETUP.md](t2-agent/SETUP.md)**

## 三条规矩

**1 · 凭证不进仓库。** Team Key（在 My Team 页面上，口令性质）、PAT、API key 一律不许
写进代码、配置或提交信息。规则 §5：凭证不得在队外共享。

**2 · 重建出来的答案不进仓库。** T2 的 `dev/realized/` 是从公开面板里重建的练习答案，
`.gitignore` 和 `.dockerignore` 都挡着。每人在本地自己生成，**只看聚合统计，绝不针对
单张卡片调参**——规则 §7 禁止分享非公开测试材料，而且最终评测用的是另一个封存时间窗，
针对练习集调参毫无意义。

**3 · 声称提分的改动，PR 里必须附前后对比。** 直接贴评测脚本的输出：

```
runs_notext    ALL 0.9148  F1 0.773  F2 0.991  F3 0.829  F4 1.004
runs_mychange  ALL 0.9xxx  ...
```

引擎是固定 seed 的确定性程序，同样的代码谁跑出来都一样；对不上就是环境有问题。
104 张练习卡片很容易调出假象——只在一个半样本上变好的改动基本都是过拟合。

## 协作

- `main` 保持随时可提交的状态
- 改动走分支 + PR：`git checkout -b t2/描述性名字`（分支名带赛道前缀，四个赛道并行时好认）
- 仓库是 **private**。规则 §9 禁止私下分享非公开解法；§93 规定拿奖后 14 天内以 OSI
  许可证公开可复现代码——到那时再开源

## 当前进度

| 赛道 | 状态 | 分数 |
|---|---|---|
| T2 Forecasting | 引擎 + 文本层完成，104/104 合规，0 失败 | **0.909** |

分数是对主办方基线归一的比值，**越低越好**，1.0 = 和基线打平。在 94 张能本地验证的
练习卡片上测得。拆开看：

| 配置 | 总分 | F1 | F2 | F3 | F4 | log_return |
|---|---|---|---|---|---|---|
| 主办方基线 | 1.000 | — | — | — | — | — |
| 我们，不读文件 | 0.915 | 0.773 | 0.991 | 0.829 | 1.004 | 1.000 |
| 我们，完整版 | **0.909** | 0.786 | 0.975 | 0.852 | 0.973 | 0.961 |

文本层在 94 张里改善 35 张、拖累 23 张。**F3 跨资产是唯一还在亏的地方**
（0.829 → 0.852），多资产卡片上文本还没挣到它的位置。
| T1 / T3 / T4 | 未开始 | — |

提交入口（CodaBench）尚未开放，等主办方公告。
