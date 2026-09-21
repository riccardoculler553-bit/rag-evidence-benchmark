---
doc_id: IT-ARCH-001
title: 系统架构说明
authority_level: 4
published_at: 2026-01-20
effective_from: 2026-02-01
effective_to: 长期
status: current
classification: internal
---

# 系统架构说明

## 一、系统与服务清单 <!-- a:sec-1 -->

| 系统 | 名称 | 服务 |
|---|---|---|
| SYS-OMS | 订单中台(OMS) | order-api, refund-api, inventory-api |
| SYS-PAY | 支付平台 | pay-api, settle-api |
| SYS-WMS | 仓务系统 | stock-api, pick-api |
| SYS-CRM | 客户关系系统 | customer-api |
| SYS-DATA | 数据仓库 | etl-job, report-api |
## 二、服务-数据库映射 <!-- a:sec-2 -->

| 服务 | 数据库 |
|---|---|
| order-api | oms_db |
| refund-api | oms_db |
| pay-api | pay_db |
| settle-api | pay_db |
| inventory-api | wms_db |
API 的调用与数据归属以上表为准；具体表结构见《数据库 Schema 说明》（IT-DB-001）。 <!-- a:xref-db -->