---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-ue-cost-model",
  "links_to": [
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-data-objects"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-ue-cost-model",
  "page_type": "Concept",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS UE & Cost Model"
}
---

# UE 与成本模型（ai_cost_ledger）

> **依据 / Source:** 《AI-native 游戏账号交易控制面》§9.1–9.4。父页：Overview。  
> 不重写公司非人力 UE 公式；AI 团队只把 AI 相关成本记清楚并接入现有公式。

Claim: 非人力UE口径 => 收入 − 非人力成本（>0 才为正）  
Claim: AI承担成本类型 => token, AI服务器, AI第三方服务  
Claim: ai_cost_ledger => P0核心表

## AI 团队该背 / 不该背

- **该背**：模型 token、AI Gateway 增量、AI 调用日志与成本账本、AI 相关 MySQL 增量；OCR/视觉（P1 起）、向量检索（P2 起）。
- **不该背**：平台流量/CDN、主站 H5/App 研发、托管/生产/库存资金、法务/安全审计、标注/质检人力、主库基础成本、客服/售后/仲裁。

## ai_cost_ledger 最小字段

`case_id`、`feature_name`、`model_name`、`input_tokens`、`output_tokens`、`cache_hit_tokens`、`model_cost_rmb`、`server_cost_allocated_rmb`、`third_party_cost_rmb`、`ue_bucket`、`created_at`。

> 与 `AIRun` 一一对应，使「今天 AI 花多少钱 / 哪个功能最贵 / 单 case AI 成本」可回答。见 数据对象。

## 预算档位（8 周）

Claim: AI专项预算-推荐档 => ¥15–30万  
Claim: AI专项预算-上限 => ¥50万

极简 ¥5–10万 / 推荐 ¥15–30万（覆盖 P0+部分 P1）/ 加速 ¥30–50万（研发配合不足时外部补位）。
