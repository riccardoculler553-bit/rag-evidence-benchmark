# 实验 1 分析：Adaptive Semantic Materialization

- 后端：deterministic-mock-semantic (zero-token)；矩阵：840 cells （domains=['ecom', 'finproc'], S=[1, 5, 10, 25, 50, 75, 100], reuse=[1, 10, 50, 100], patterns=5, breadth=[1, 2, 4]）
- 运行时长：446.2 s

## 1. 最优策略标签分布（含 oracle 作为下界）

```json
{
 "B": 336,
 "C": 342,
 "A": 162
}
```

## 2. 关键 regret（相对离线 clairvoyant oracle）

| 策略 | mean | min | max |
|---|---|---|---|
| A Eager-Persistent | 9.038 | 0 | 120.8 |
| B Late-Per-Query | 17.26 | 0 | 98.59 |
| C Late-Persistent | 0.00137 | 0 | 0.0042 |
| CBO Simple | 0.2615 | 0 | 0.9968 |
| D Adaptive | 0.8507 | 0 | 18.67 |
| D+ (privileged horizon, 诊断) | 0.7186 | 0 | 17.68 |

## 3. 核心检验：Adaptive vs Simple CBO（F1/F2）

- 逐 cell 比率 D/CBO：mean = **1.3961**
- D 严格优于 CBO 的 cell 数：**72**；相同：**609**；更差：**159**（共 840 cells）
- D+（额外知道真实视界 R）与 D 的 regret 差：**-0.13204**（≈0 → 残余 regret 不来自视界估计）

## 4. 按谓词模式的分解

| pattern | C/A(mean) | regret_D(mean) | regret_CBO(mean) |
|---|---|---|---|
| PRED_SHARED | 0.3805 | 2.864 | 0.7336 |
| PRED_DISTINCT | 0.7384 | 0.1419 | 0.2883 |
| PRED_NESTED | 0.4971 | 1.083 | 0.04033 |
| PRED_OVERLAP | 0.6728 | 0.1651 | 0.2452 |
| PRED_MUTEX | 0.7772 | 0.00025 | 0 |

## 5. 按能力广度（breadth）的分解

| breadth | regret_D(mean) | regime |
|---|---|---|
| c=1 | 0.8399 | 1.84 |
| c=2 | 0.8531 | 1.853 |
| c=4 | 0.859 | 1.859 |

## 6. 物化作用域 / 容量消融（解释旧实验 C/A > 1）

| scope | C/A mean | C/A min | C/A max |
|---|---|---|---|
| workload 级（无限，跨查询持久） | 0.6056 | 0.0082 | 1 |
| cell 级（每 query 重置 = 旧实验口径） | 11.98 | 0.0082 | 99.84 |
| LRU 容量 10%（跨查询持久） | 11.72 | 0.0082 | 99.84 |
| LRU 容量 1%（跨查询持久，强抖动） | 11.96 | 0.0082 | 99.84 |

> 结论：**C/A > 1 只在物化作用域被限制为 cell 级（旧实验）或缓存容量受限时出现**，
> 它是物化作用域/缓存容量现象，不是语义能力的性质。
