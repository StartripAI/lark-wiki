---
{
  "asset_key": "PAGE::project::agent_workspace::aios-os-overview",
  "links_to": [
    "project::agent_workspace::aios-os-data-objects",
    "project::agent_workspace::aios-os-ai-judgment-matrix",
    "project::agent_workspace::aios-os-risk-taxonomy",
    "project::agent_workspace::aios-os-ue-cost-model",
    "project::agent_workspace::aios-os-privacy-pii-governance",
    "project::agent_workspace::index"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios-os-overview",
  "page_type": "Concept",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS OS Canonical Knowledge (Overview)"
}
---

# AIOS OS Canonical Knowledge（总览 / 单一真相源）

> **依据 / Source:** 本页是从《AI-native 游戏账号交易控制面》OKR/上线方案编译出的结构化知识中枢，作为该 OS 业务口径的**单一真相源**。原文：`reports/ai_native_trade_control_plane_v0_2026_05_28.md`。  
> 任何代码、文档或下游页面与本页 `Claim:` 数字冲突时，以本页为准，并应被 `lint` 的跨页矛盾检查捕获。

## 这是什么

一个 **AI-native 游戏账号交易 OS**：让每个账号交易 case 从第一天起就有 ID、有证据、有 AI 判断、有人审边界、有结果回流、有成本记录。AI 不碰凭证/支付/自动成交，只参与「证据 → 判断 → 动作建议 → 人审 → 反馈」的闭环。

## 子页面（互链）

- 数据对象 / Data Objects — 7 个最小数据对象的字段契约。
- AI 判断矩阵与四类边界 — 每个 SOP 步骤的自动化等级与 HITL/Forbidden 边界。
- 风险 taxonomy — 风险标签与人审升级。
- UE 与成本模型 — `ai_cost_ledger` 与非人力 UE 归因。
- 隐私 / PII 治理 — PII 分级、留存、入模脱敏。

## 第一性原理（AI PT）

AI 参与「证据 - 判断 - 动作建议 - 人审 - 反馈」的闭环。**不能妥协**：AI 不碰凭证、支付、自动成交、不可解释最终定价。北极星：AI 覆盖率、采纳率、节省时间、风险拦截率、成本/单。

## 权威业务口径（Canonical Claims）

> 以下为机器可校验的单一真相源；`Claim: <键> => <值>` 会被跨页矛盾检查消费。

Claim: 游戏分布-腾讯 => 45%  
Claim: 游戏分布-网易 => 10%  
Claim: 游戏分布-米哈游 => 10%  
Claim: 游戏分布-巨人 => 5%  
Claim: 游戏分布-Steam => 30%  
Claim: 资金占用-总额 => 150万  
Claim: 成品号-日售 => 20单/天  
Claim: 成品号-日回收 => 20单/天  
Claim: 成品号-库存 => 500个  
Claim: 手机卡-数量 => 300张  
Claim: Steam-日售 => 150单/天  
Claim: Steam-日产 => 150单/天  
Claim: Steam-库存 => 4000个  
Claim: 平台-MRR目标-12月底 => ¥1000万  
Claim: 平台-非人力UE转正 => 10月底  
Claim: 初始库存-成品号 => 1万个  
Claim: 初始库存-Steam => 4000个

## 上线分级（P0/P1/P2/P3）

- **P0**（现在\~6月底）：AI 交易平台 V0 上线闸门——AI Gateway、最小 MySQL 表、`ai_cost_ledger`、AI 阅读材料包、HITL 边界、30–50 真实 case 跑通。阻断 AI 版上线。
- **P1**（7月）：AI Deal File 工作台、200+ gold cases、风险标签 v1、OCR/视觉、成本看板。
- **P2**（8–9月）：游戏字段本体、相似案例检索、向量库、BI、A/B。
- **P3**（10月后）：自动砍价/定价/交付等高风险自动化——数据闭环成熟后再逐步放权。

## 禁止自动化（硬边界）

自动成交/付款/退款/放款/确认收货、自动登录/换绑/找回、读取验证码/cookie/token、保证估价准确/保证账号安全——全部禁止或人审。详见 AI 判断矩阵。
