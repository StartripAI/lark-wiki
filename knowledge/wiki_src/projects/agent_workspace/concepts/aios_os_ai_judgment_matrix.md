---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-ai-judgment-matrix",
  "links_to": [
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-risk-taxonomy",
    "project::agent_workspace::aios-os-data-objects"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-ai-judgment-matrix",
  "page_type": "Concept",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS AI Judgment Matrix & Action Boundaries"
}
---

# AI 判断矩阵与四类边界

> **依据 / Source:** 《AI-native 游戏账号交易控制面》§6.2–6.3、§12。父页：Overview。  
> 业务/产品拆 SOP；AI 团队把每一步转成「能力 + 数据对象 + HITL 边界 + 可复用资产」，不重拆业务流程。

## 四类自动化边界

Claim: 自动化边界类别数 => 4

| 类型 | 定义 | 例子 |
|-|-|-|
| AI-assisted | AI 可直接完成低风险结构化或生成建议 | 截图字段抽取、买家需求解析、标题卖点生成 |
| AI+HITL | AI 给建议，人做最终判断 | 估价区间、风险判断、砍价话术、推荐排序 |
| Human-only | 必须人操作或审批 | 最终报价、高风险账号、纠纷处理、上架承诺 |
| Forbidden | AI 不允许接触或执行 | 密码、验证码、支付、退款、自动成交、保证安全 |

## 判断矩阵（每个 SOP 步骤回答）

步骤类型（抽取/估价/风控/匹配/话术/执行/复盘）→ 输入数据 → 输出结果 → 自动化等级 → 人审边界（涉钱/涉密码验证码/涉最终承诺/高金额/低置信/高风险）→ 数据沉淀（只服务号商 / 可复用平台 / 可训练评测 / 可进 UE）→ 产品入口 → 验收方式（采纳率/准确率/时间下降/成交提升/风险减少/成本可控）。

## Forbidden 硬清单（与产品/研发需求对齐）

Claim: AI最终定价权 => 禁止（先建议，人审）  
Claim: AI支付与放款 => 禁止  
Claim: AI读取验证码/cookie/token => 禁止  
Claim: AI自动登录换绑找回 => 禁止  
Claim: AI对外保证（估价准/账号安全/无纠纷） => 禁止

- 交易：禁止 AI 自动成交、付款、退款、放款、确认收货 → 改为 AI 生成建议+checklist，人完成高影响动作。
- 账号控制：禁止自动登录/换绑/找回/读取验证码/cookie/token → AI 只处理必要、可追踪的证据摘要与人工确认结果。
- 估价/风控：禁止「保证」措辞 → AI 给区间、依据、置信度；高风险升级人工，见 风险 taxonomy。

## 与系统的连接

每次 AI 判断前生成 `ai_case_context`（资产摘要/证据摘要/需求摘要/价格上下文/风险上下文/`allowed_actions`/`blocked_fields`），AI 只读必要信息；调用落 `AIRun`，见 数据对象。`blocked_fields` 的强约束见 隐私/PII 治理。
