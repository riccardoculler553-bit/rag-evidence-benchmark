---
doc_id: IT-API-001
title: 订单 API 文档
authority_level: 4
published_at: 2026-01-25
effective_from: 2026-02-01
effective_to: 长期
status: current
classification: internal
---

# 订单 API 文档

## 1. POST /orders/{{id}}/cancel —— 取消订单 <!-- a:sec-1 -->

2. 由订单中台 order-api 服务提供。 <!-- a:sec-svc -->
3. 处理流程：
   3.1 校验订单状态（仅“待发货”可取消）；
   3.2 调用 inventory-api 释放占用库存；
   3.3 将订单状态更新为 CANCELLED，并记录取消原因。 <!-- a:sec-flow -->
4. 服务与数据库的对应关系参见《系统架构说明》（IT-ARCH-001）。 <!-- a:xref-arch -->