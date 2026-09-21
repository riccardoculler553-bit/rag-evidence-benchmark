# 实验 3 分析：Prior-Art Boundary + Lifecycle

- experiment_id: `v1.3-final-three-experiments:e3:98fa60d8`；tier: Tier 2（结构性 proxy）+ Tier 1（Lifecycle 机制）
- ****未运行任何外部系统**。QuWARTS-like / ReDD-like / PLOP-like / DASE-like 均为结构性 proxy baseline，严禁表述为原论文系统实验。**

## 1. 逐工作负载：各 baseline 的总成本（ᴾ = structural proxy）

### Table C

| Workload | Eager | Late-Persistent | QuWARTS-like | ReDD-like | PLOP-like | DASE-like | Oracle |
|---|---:|---:|---:|---:|---:|---:|---:|
| W1_cold_query_driven | 5.1842 | 1.723 | 1.723ᴾ | 4.1045ᴾ | 1.723 (Late-Persistent) | 2.1313ᴾ | 1.7193 |
| W2_warm_high_reuse | 5.1842 | 4.6724 | 4.6725ᴾ | 206.66ᴾ | 4.6724 (Late-Persistent) | 4.8864ᴾ | 4.0924 |
| W3_mixed | 5.1842 | 3.7695 | 3.7697ᴾ | 70.885ᴾ | 3.7695 (Late-Persistent) | 4.0553ᴾ | 3.5812 |
| W4_unseen_capability | 5.1842 | 1.9711 | 2.0277ᴾ | 5.948ᴾ | 1.9711 (Late-Persistent) | 2.364ᴾ | 1.9608 |

ᴾ = structural proxy（**未运行原系统**）；其余为本次实现的 native baseline。

## 2. Source Drift

### Table D

| Drift | Full Rebuild | Affected-row Rebuild | Rebuild Ratio | Stale Rows (if no rebuild) | Freshness |
|---|---:|---:|---:|---:|---:|
| 0% | 5.1682 | 0 | 0 | 0 | 1.0 |
| 1% | 5.1682 | 0.031196 | 0.00604 | 158 | 1.0 |
| 5% | 5.1682 | 0.16433 | 0.0318 | 786 | 1.0 |
| 10% | 5.1682 | 0.32424 | 0.06274 | 1572 | 1.0 |
| 25% | 5.1682 | 0.80852 | 0.15644 | 3932 | 1.0 |

**结论**：受影响行重建成本随 drift 近似线性增长且恒 ≪ 全量重建 → 等价于经典 Incremental View Maintenance（不构成新机制）。

## 3. Unseen Capability 冷启动

| strategy | total | amortized/query | first-query | build rows | native/proxy |
|---|---:|---:|---:|---:|---|
| Eager | 5.1842 | 0.086404 | n/a | 20000 | native |
| Late-Persistent | 1.9711 | 0.032851 | 0.077159 | 7534 | native |
| QuWARTS-like | 2.0277 | 0.033795 | 0.035561 | 7752 | proxy |
| ReDD-like | 5.948 | 0.099134 | 0.038386 | 27660 | proxy |

**结论**：新能力首次出现时，Eager 需整表重建、Late 只对 survivor 增量补齐；
「能够动态创建」本身不是创新（ReDD/PLOP 均已覆盖）。
