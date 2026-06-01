---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-data-objects",
  "links_to": [
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-ai-judgment-matrix",
    "project::agent_workspace::aios-os-privacy-pii-governance"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-data-objects",
  "page_type": "Entity",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS Data Objects (7 minimal)"
}
---

# 数据对象 / Data Objects（P0 最小集）

> **依据 / Source:** 《AI-native 游戏账号交易控制面》§5.5。父页：Overview。  
> 核心对象稳定、SOP 可变；新游戏只加字段定义和 SOP 版本，不重建表。游戏特有字段进 `asset_facts_json`。

Claim: 最小数据对象数量 => 7

## AccountAsset（这个号是什么）

字段：`asset_id`、`game_id`、`game_family`、`account_type`、`server_region`、`asset_summary`、`asset_facts_json`、`source`、`current_status`、`schema_version`。

## DealCase（围绕账号/需求的一次处理）

字段：`case_id`、`case_type`、`asset_id`、`demand_id`、`current_step`、`case_status`、`sop_version`、`owner_id`、`priority`、`created_at`。

## Evidence（支撑价值/安全/风险判断的证据）

字段：`evidence_id`、`case_id`、`asset_id`、`evidence_type`、`file_url`、`extracted_text`、`extracted_facts_json`、`confidence`、`privacy_level`、`created_at`。

> 证据含 PII（截图/聊天/手机号），`privacy_level` 的治理见 隐私/PII 治理。

## BuyerDemand（买家想要什么号）

字段：`demand_id`、`user_id`、`game_id`、`budget_min`、`budget_max`、`must_have_json`、`nice_to_have_json`、`urgency`、`parsed_from`、`created_at`。

## AIRun（AI 做过什么判断）

字段：`ai_run_id`、`case_id`、`feature_name`、`model_name`、`prompt_version`、`input_context_id`、`output_json`、`confidence`、`latency_ms`、`status`、`created_at`。

> 每次 AI 调用绑定 `input_context_id`（AI 阅读材料包 `ai_case_context`），实现 grounding 与可复盘。

## HumanDecision（人是否采纳 AI，为什么）

字段：`decision_id`、`case_id`、`ai_run_id`、`decision_type`、`decision_result`、`reason_code`、`operator_id`、`created_at`。

## CaseOutcome（这单最后怎么样）

字段：`outcome_id`、`case_id`、`result`、`gmv`、`revenue`、`gross_profit`、`days_to_sell`、`dispute_flag`、`refund_flag`、`risk_loss`、`closed_at`。

## 串联关系

`Seller submits DealCase` · `DealCase has Evidence` · `BuyerDemand matches AccountAsset` · `AIRun produces suggestion → HumanDecision → CaseOutcome`。每个 case 能串起账号、证据、AI 判断、人审、结果、成本。
