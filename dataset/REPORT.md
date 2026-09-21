# 数据集统计报告

- 注册文档：79；知识库文件：107
- 结构化表：10；实体：587；关系：1666
- 问题：300；Gold 记录：300

## 问题类型分布

| 类型 | 数量 |
|---|---|
| table | 74 |
| single_doc | 73 |
| temporal | 55 |
| sibling_structure | 45 |
| derivation | 44 |
| calculation | 36 |
| hr | 30 |
| multi_hop | 25 |
| scope | 22 |
| structured_join | 16 |
| structured | 15 |
| exception | 14 |
| snapshot | 9 |
| aggregation | 8 |
| entity_resolution | 8 |
| contrastive | 8 |
| numeric_trap | 7 |
| negative | 7 |
| adversarial | 7 |
| authority | 6 |
| claim_force | 6 |
| citation_attack | 6 |
| exhaustive | 5 |
| evidence_addition | 5 |
| permission | 5 |
| red_herring | 5 |
| conflict | 4 |
| hierarchy | 4 |
| numeric_precision | 3 |
| ranking | 3 |
| structured_vs_doc | 3 |
| synonym | 3 |
| counterfactual | 2 |
| role | 2 |
| pair | 2 |
| parser_error | 2 |
| definition | 2 |
| conflict_fake | 1 |
| hidden_exception | 1 |
| counter_evidence | 1 |
| extrapolation | 1 |
| role_extrapolation | 1 |
| conflict_resolution | 1 |
| audit | 1 |
| event_vs_record | 1 |
| causal | 1 |
| near_entity | 1 |
| cross_source | 1 |

## 难度分布

| 难度 | 数量 |
|---|---|
| L1 | 42 |
| L2 | 66 |
| L3 | 67 |
| L4 | 79 |
| L5 | 32 |
| L6 | 8 |
| L7 | 6 |

## Expected Action 分布

| 动作 | 数量 |
|---|---|
| ANSWER | 287 |
| UNKNOWN | 7 |
| CONFLICT | 2 |
| ABSENT | 2 |
| ACCESS_DENIED | 1 |
| CLARIFY | 1 |

## reasoning_signature 覆盖

| 能力 | 数量 |
|---|---|
| table_lookup | 123 |
| temporal_filter | 62 |
| entity_resolution | 59 |
| arithmetic | 46 |
| column_disambiguation | 45 |
| definition_retrieval | 32 |
| scope_filter | 30 |
| exception_override | 14 |
| structured_scan | 13 |
| authority_check | 11 |
| aggregation | 11 |
| multi_hop | 11 |
| snapshot_query | 9 |
| direct_lookup | 9 |
| claim_force_check | 8 |
| contrastive_dimension | 8 |
| abstention | 6 |
| citation_validation | 6 |
| role_filter | 5 |
| exhaustive_scan | 5 |
| document_relationship | 5 |
| permission_check | 5 |
| numeric_precision_check | 4 |
| evidence_addition | 4 |
| cross_reference | 3 |
| exception_lookup | 3 |
| currency_check | 3 |
| conflict_detection | 3 |
| unit_dependency | 3 |
| sort | 3 |
| condition_matching | 3 |
| synonym_resolution | 3 |
| conflict_resolution | 2 |
| coverage_check | 2 |
| hierarchy_traversal | 2 |
| structured_join | 2 |
| numeric_trap | 2 |
| scope_city | 2 |
| scope_role | 2 |
| scope_time | 2 |
| claim_refinement | 2 |
| near_entity | 2 |
| footnote_dependency | 1 |
| counter_evidence | 1 |
| counterfactual | 1 |
| regulation_check | 1 |
| conflict_surface | 1 |
| numeric_precision | 1 |
| scope_completeness | 1 |
| tie_handling | 1 |
| join | 1 |
| scope_region | 1 |
| scope_exception | 1 |
| event_vs_record | 1 |
| causal_reasoning | 1 |
| evidence_level_acl | 1 |
| cache_invalidation | 1 |
| parser_awareness | 1 |
| concept_disambiguation | 1 |
| clarification | 1 |
| cross_source_join | 1 |

## failure_target 覆盖

| 攻击目标 | 数量 |
|---|---|
| RETRIEVAL_MISS | 144 |
| NUMERIC_ERROR | 72 |
| TEMPORAL_LEAK | 63 |
| DERIVATION_ERROR | 41 |
| SCOPE_LEAK | 25 |
| EXCEPTION_MISS | 19 |
| OVERCLAIM | 17 |
| COMPLETENESS_ERROR | 13 |
| CONFLICT_IGNORE | 8 |
| AUTHORITY_MISS | 8 |
| ACCESS_CONTROL_LEAK | 2 |

## 文档域分布

| 域 | 数量 |
|---|---|
| policies | 15 |
| finance | 15 |
| faq | 8 |
| technology | 7 |
| projects | 7 |
| legal | 6 |
| procurement | 4 |
| hr | 4 |
| audit | 4 |
| conflicts | 3 |
| ecommerce | 3 |
| attachments | 2 |
| sales | 1 |
