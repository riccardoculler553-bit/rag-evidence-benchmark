---
doc_id: IT-DB-001
title: 数据库 Schema 说明
authority_level: 4
published_at: 2026-01-22
effective_from: 2026-02-01
effective_to: 长期
status: current
classification: internal
---

# 数据库 Schema 说明

## 核心库表清单 <!-- a:sec-1 -->

| 数据库 | 表 | 字段 |
|---|---|---|
| oms_db | order_info | order_id, status, cancel_reason, updated_at, amount |
| oms_db | refund_order | refund_id, order_id, amount, state |
| pay_db | payment | pay_id, order_id, channel, state |
| wms_db | inventory | sku, warehouse, qty |
order_info.status 记录订单状态（PAID/SHIPPED/CANCELLED/REFUNDED）。 <!-- a:sec-note -->