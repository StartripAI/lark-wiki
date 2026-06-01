---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-risk-taxonomy",
  "links_to": [
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-ai-judgment-matrix"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-risk-taxonomy",
  "page_type": "Concept",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS Risk Taxonomy"
}
---

# 风险 Taxonomy 与人审升级

> **依据 / Source:** 《AI-native 游戏账号交易控制面》§4.4（风险标签 v1）、§6.3（人审边界）。父页：Overview。

## 风险标签 v1

Claim: 风险标签集-v1 => 找回, 证据不足, 价格异常, 绑定异常, 卖家异常

| 标签 | 触发信号 | AI 动作 | 人审 |
|-|-|-|-|
| 找回风险 | 账号可被原主找回的迹象 | 标记 + 列缺失证据 | 高风险→必审 |
| 证据不足 | 关键证据缺失/置信低 | 列 evidence gap、请求补证 | 视缺口 |
| 价格异常 | 报价显著偏离历史成交 | 提示区间与依据 | 高金额→必审 |
| 绑定异常 | 实名/手机/二次绑定异常 | 标记，不读凭证 | 必审 |
| 卖家异常 | 卖家行为/历史异常 | 标记并升级 | 必审 |

## 人审升级原则

Claim: 高风险case处置 => 升级人工（AI不得自动放行）

- AI 只**提示**风险与缺失证据；**高风险 case 一律升级人工**。
- 涉钱、涉密码/验证码、涉最终承诺、高金额、低置信、高风险 → 进入 Human-only / Forbidden 边界。
- 风险标签写入 `Evidence`/`DealCase`，结果回流 `CaseOutcome.risk_loss`/`dispute_flag`，见 数据对象。

## 不做承诺

不保证账号安全、不保证无找回、不保证无纠纷——只做风险提示与证据完整度展示（与 Forbidden 清单 一致）。
