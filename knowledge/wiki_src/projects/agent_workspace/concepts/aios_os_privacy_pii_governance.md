---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-privacy-pii-governance",
  "links_to": [
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-ai-judgment-matrix",
    "project::agent_workspace::aios-os-data-objects"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-privacy-pii-governance",
  "page_type": "Concept",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS Privacy & PII Governance"
}
---

# 隐私 / PII 治理

> **依据 / Source:** 《AI-native 游戏账号交易控制面》§5.4（AI 阅读材料包、`blocked_fields`）。父页：Overview。  
> 对照 OpenAI/Anthropic 的「数据最小化 / 最小权限 / 不臆造」原则落地。**范围说明**：本页只覆盖隐私/PII；平台 ToS / 反欺诈 / 防盗号合规按当前决定暂不纳入。

## 硬约束：PII 不出域

Claim: PII不出域 => 密码/验证码/token/cookie/支付账号/完整手机号/身份信息 不得入模  
Claim: AI可见字段 => 游戏/区服/段位/皮肤/报价/证据完整度/历史相似成交/风险标签/当前步骤

- **AI 可以看**：游戏、区服、段位、皮肤、卖家报价、证据完整度、历史类似成交、风险标签、当前步骤。
- **AI 不应看**：密码、验证码、token、cookie、支付账号、完整手机号、身份信息、不相关的原始聊天全文。
- 落地：`ai_case_context.blocked_fields` 不是建议而是**强约束（enforce）**——构造材料包时把上述字段从 payload 中剔除/脱敏，再交给模型；任何凭证类证据由 证据安全闸 在入库前拦截（见 evidence autopilot 的 forbidden-evidence gate）。

## PII 分级（privacy_level）

| 级别 | 例子 | 处理 |
|-|-|-|
| public | 游戏名、区服、段位 | 可入模、可展示 |
| internal | 报价、证据完整度、风险标签 | 可入模，限内部展示 |
| sensitive | 部分手机号尾号、聊天片段 | 脱敏后方可入模 |
| forbidden | 密码/验证码/token/cookie/身份证/人脸/完整手机号/支付账号 | 禁止入模、禁止进 build 产物、禁止外发 |

> `Evidence.privacy_level` 标注每条证据级别，见 数据对象。

## 留存、加密、访问

Claim: PII留存策略 => 最小留存 + 到期删除 + 加密存储 + 最小权限访问

- **最小留存**：证据/聊天只保留业务必需时长，到期自动删除或匿名化。
- **加密**：文件走 OSS/文件服务，静态加密；MySQL 只存 `file_url` + 元数据，不存明文凭证。
- **访问控制**：按 `operator_id`/角色最小授权；敏感字段访问留审计。
- **合规**：国内业务遵循 PIPL（告知-同意、最小必要、跨境评估）；模型供应商（DeepSeek/Qwen 等）调用前确认数据处理条款。

## 入模脱敏检查（落地动作）

1. 生成 `ai_case_context` 时按 `blocked_fields` 剔除/脱敏。
2. 禁止把 sensitive/forbidden 字段写入 `knowledge/build` 或同步到远端。
3. `AIRun.input_context_id` 可回溯「这次到底喂了什么」，便于审计与复盘。
