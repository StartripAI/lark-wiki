---
{
  "asset_key": "PAGE::project::agent_workspace::ai-native-trade-control-plane-v0-2026-05-28",
  "links_to": [
    "project::agent_workspace::index",
    "project::agent_workspace::log",
    "project::agent_workspace::aios-os-overview",
    "project::agent_workspace::aios-os-data-objects",
    "project::agent_workspace::aios-os-ai-judgment-matrix",
    "project::agent_workspace::aios-os-risk-taxonomy",
    "project::agent_workspace::aios-os-ue-cost-model"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::ai-native-trade-control-plane-v0-2026-05-28",
  "page_type": "Report",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AI-native 游戏账号交易控制面：第一性原理、上线门槛与 8 周执行方案"
}
---

# AI-native 游戏账号交易控制面：第一性原理、上线门槛与 8 周执行方案

> 核心结论：普通 H5/App 交易平台可以上线；但只有完成 P0，上线版本才能对内对外称为 AI 交易平台 V0。P0 的本质不是“大而全 AIOS”，而是让每个账号交易 case 从第一天开始有 ID、有证据、有 AI 判断、有人审边界、有成本记录、有结果回流。

> 管理口径：号商是试验田，平台是规模化交易网络，AI 团队不是聊天插件小组，而是 AI-native 交易控制面 DRI。AI 团队负责 AI 数据标准、SOP 到 AI opportunity map、HITL 边界、模型调用、成本记录、AI 评测和平台复用能力。业务负责 SOP 与结果，产品负责用户流程，研发负责主系统交付。

---

## 1. 执行摘要

| 管理问题 | 新结论 | 需要拍板 |
|-|-|-|
| 平台到底能不能上线 | 普通平台可以上线；AI 交易平台 V0 必须通过 P0 上线闸门。 | 确认 6 月上线目标是 AI 交易平台 V0，不是完整 AIOS。 |
| P0 是什么 | P0 是上线前最低门槛：有 case、有证据、有 AI 判断、有人审、有结果、有成本。 | 确认 P0 阻断 AI 版上线；P1/P2/P3 分阶段补。 |
| 飞书表格怎么处理 | 飞书表格不作为长期业务生产数据源；新平台数据直接进 MySQL。 | 确认飞书只做历史迁移或短期过渡，不继续扩大依赖。 |
| AI 团队预算怎么要 | 8 周 AI 专项预算推荐 ¥15–30 万；研发支持不足时预留到 ¥50 万。 | 确认 AI 团队只背 AI 增量成本，不背流量、托管、生产、法务、质检和主站研发。 |
| 非人力 UE 怎么接 | 不重写公司 UE 公式，只把 token、AI 服务器、AI 第三方服务成本记清楚并接入现有公式。 | 确认 `ai_cost_ledger` 是 P0 核心表。 |
| 今天组会怎么开 | 45 分钟，只对齐 SOP 输入格式、AI 判断矩阵、产品形态想法、全栈技术规范桥接、激励与风险想法。 | 不在第一次会里硬定 7 天交付，也不让 AI 团队重拆业务 SOP。 |

---

## 2. OKR 原文转录与对齐

> 以下以 2026-05-28 用户提供的截图为准。本地旧 harness 只作为边界和验证方法参考，不作为最新业务目标。

### 2.1 O2 智能号商（有布有趣）

| 层级 | 内容 |
|-|-|
| Objective | 非人力 UE 为正（流量、托管、生产），6 人团队 + 号商基建（产研不进一步投入）。 |
| KR1 | 号商的最小单元结构化数据，为全面 AI 平台服务。 |
| KR2 | 游戏分布：腾讯 45%（top5）、网易 10%（top3）、米哈游 10%（top3）、巨人 5%（top1）、Steam 30%（top30）。 |
| KR3 | 资金占用 150 万：成品号（库存 75 万 + 抵押 20 万），Steam（库存 30 万 + 应收 10 万 + 备用金 15 万）。 |
| KR4 | 业务规模：成品号售卖 20 单/天、回收 20 单/天、库存 500 个；手机卡 300 张；Steam 售卖 150 单/天、生产 150 单/天、库存 4000 个。 |
| 备注 | 实体张 25 张，云栈 150 张，集控 50 张，泰优汇 150 万，200 张卡。 |

### 2.2 O3 AI 交易平台（深度/子瓜）

| 层级 | 内容 |
|-|-|
| Objective | 12 月底 MRR ¥1000 万，10 月底非人力 UE 为正（流量、token、服务器、第三方服务）。 |
| KR1 | H5 版 6 月下旬上线，App 版 6 月底上线。 |
| KR2 | 初始库存成品号 1 万个（腾讯、网易、米哈游、巨人），初始库存 Steam 4000 个。 |

### 2.3 AI 团队在 O2/O3 之间的定位

| 对象 | 定位 | AI 团队要沉淀的资产 |
|-|-|-|
| O2 号商 | 平台试验田，不是单纯卖号团队。 | SOP 输入模板、AI 判断矩阵、证据链、风险标签、人工决策记录、成本账本、结果标签。 |
| O3 平台 | 规模化交易网络，不是聊天工具。 | AI 估值、风控、匹配、推荐接口，HITL 工作流，评测样本，成本归因，前端 AI 表达规范。 |
| AI 团队 | AI-native 交易控制面 DRI。 | 数据对象、AI Gateway、AI 阅读材料包、模型与 prompt 版本、AI 成本、HITL 边界、产品 AI 感知点。 |

---

## 3. 各 PT 的第一性原理

| PT | 第一性原理 | 不能妥协 | 北极星指标 |
|-|-|-|-|
| 号商 PT | 用最少资本、最短周转、可控风险，把非标账号转成可解释毛利。 | 每个交易动作必须可记录、可复盘、可归因。 | 单号预期毛利、资金占用、周转天数、风险损失。 |
| 平台 PT | 提高非标账号交易的流动性与信任。 | 账号必须结构化、证据化、可估值、可匹配。 | MRR、成交 GMV、转化率、纠纷率、复购率。 |
| AI PT | AI 参与“证据 - 判断 - 动作建议 - 人审 - 反馈”的闭环。 | AI 不碰凭证、支付、自动成交、不可解释最终定价。 | AI 覆盖率、采纳率、节省时间、风险拦截率、成本/单。 |
| 数据 PT | 数据是 AI 的证据、状态机、记忆和评测燃料。 | 业务生产数据不能长期散在飞书、聊天、人工备注里。 | case 覆盖率、字段完整率、证据完整率、结果回流率。 |
| 团队 PT | 小团队必须拥有闭环责任，而不是接临时需求。 | AI 团队不能沦为提示词/机器人支持组。 | 从 SOP 到 AI 组件上线周期、复用率、业务指标影响。 |
| UE PT | AI 成本必须能归因到 case、功能、模型和业务线。 | 不重写公司 UE 公式，也不能只看 token。 | AI 成本项完整率、成本/有效 case、AI 入口转化。 |

---

## 4. 平台上线分级：P0 / P1 / P2 / P3

> 这部分是本文档的核心更新。平台能上线，但必须分级上线。P0 是能不能叫 AI 交易平台 V0；P1 是能不能运营和迭代；P2 是能不能支撑 UE 与 MRR 放大；P3 是未来壁垒，不拖当前上线。

### 4.1 总表

| 阶段 | 时间 | 定义 | 是否阻断上线 | 预算口径 |
|-|-|-|-|-|
| P0 | 现在到 6 月底 | AI 交易平台 V0 的上线闸门。 | 阻断 AI 版上线；不阻断普通平台上线。 | ¥5–15 万，包含 AI Gateway、最小 MySQL 表、成本账本、AI 阅读材料包、基础模型调用。 |
| P1 | 7 月，上线后 2–4 周 | 让 AI 从“能跑”变成“能运营、能迭代”。 | 不阻断 V0，但不做会导致规模化失控。 | ¥10–20 万，包含工作台、OCR/视觉、gold cases 工具、成本看板。 |
| P2 | 8–9 月 | 支撑非人力 UE 与 MRR 放大。 | 不阻断当前，但现在必须留口子。 | ¥5–20 万/月，随业务量上升。 |
| P3 | 10 月后 | 长期壁垒和更高自动化。 | 不阻断当前。 | 单独立项。 |

### 4.2 六层 MECE 框架

| 层 | 业务语言 | P0 要求 |
|-|-|-|
| A. 业务动作层 | SOP 每一步 AI 能不能做 | 业务/产品给 SOP v0，AI 团队转 AI 判断矩阵。 |
| B. 数据对象层 | 每笔交易留下什么结构化对象 | 固定 7 个最小对象，避免按每个 SOP 重建系统。 |
| C. 系统承载层 | 数据、文件、AI 调用放哪里 | MySQL、OSS/现有文件服务、AI Gateway。 |
| D. AI 能力层 | AI 具体做什么 | 抽取、估价、风控、推荐、话术建议，不越权执行。 |
| E. 产品体验层 | 用户/运营如何感知 AI | 卖家 AI 估号、买家 AI 找号、AI 账号卡。 |
| F. 指标与 UE 层 | 怎么证明 AI 有价值且成本可算 | 埋点、`ai_cost_ledger`、采纳率、结果回流。 |

### 4.3 P0 详细清单

| P0 项 | 为什么需要 | 做什么 | 怎么做 | Owner | 预算归属 | 验收 | 不做后果 |
|-|-|-|-|-|-|-|-|
| SOP v0 输入 | AI 不能拍脑袋拆业务流程。 | 业务/产品交付 SOP v0，AI 团队转判断矩阵。 | SOP 至少包含步骤名、输入、输出、判断标准、风险、耗时、常见错误、结果验证。 | 业务/产品主责，AI 审核。 | 人力为主。 | 覆盖成品号回收、售卖、买家找号、Steam 售卖；Steam 生产可粗版。 | AI 能力和真实业务脱节。 |
| AI 判断矩阵 | 把 SOP 变成 AI 能力边界。 | 给每一步打标签。 | 标注 AI-assisted、AI+HITL、Human-only、Forbidden；写清 required_data、required_evidence、product_surface、data_to_store。 | AI 负责人 + 数据风控。 | 人力为主。 | 每个核心步骤都有自动化等级和人审理由。 | 产品/研发会把 AI 做成孤立功能。 |
| 7 个最小对象 | 核心对象稳定，SOP 可变。 | 定义 AccountAsset、DealCase、Evidence、BuyerDemand、AIRun、HumanDecision、CaseOutcome。 | AI 定义字段，研发落 MySQL，业务确认含义。 | AI 定义，研发落库。 | MySQL 增量。 | 每个 case 能串起账号、证据、AI 判断、人审、结果。 | 数据散在聊天、飞书、人工备注里，无法复盘。 |
| 版本口子 | SOP 只有 80% 准，新游戏会变。 | 配置 `sop_template`、`sop_step`、`game_field_definition`。 | 新游戏加配置，不重建表；游戏特有字段放 `asset_facts_json`。 | AI + 数据 + 研发。 | 小额开发。 | 新增游戏只需新增字段定义和 SOP 版本。 | 后续每加游戏都要重构。 |
| MySQL 落地 | H5/App/API/成本账本不能靠表格。 | 新平台数据直接进 MySQL。 | 优先现有主库/RDS；如主库不便，加同云同 VPC 的 schema/database；不另起野系统。 | 研发主责，全栈桥接。 | AI 表增量可计入 AI 预算，主库基础成本不计入。 | 新 case、证据、AI 调用、成本可写入。 | 平台上线后数据不可控。 |
| 飞书处理 | 业务刚起步，应做减法。 | 飞书不做长期主数据源。 | 历史数据一次性导入；短期最多 2–4 周单向同步；新数据不再写飞书。 | 数据 + 全栈。 | 可选迁移脚本。 | 明确飞书退场时间和迁移路径。 | 表格包袱变成长期架构债。 |
| 证据存储 | AI 估价和风控必须有证据链。 | 截图、视频、聊天、账号证明进入文件服务。 | 文件放 OSS/现有文件服务；MySQL 存 `evidence_id`、`file_url`、类型、抽取结果、隐私等级。 | 研发。 | OSS/文件服务增量很小。 | 每个证据能追到 case 和 asset。 | 证据散落，无法核验。 |
| AI 阅读材料包 | AI 只应读必要材料。 | 建 `ai_case_context`。 | 每次 AI 判断前生成资产摘要、证据摘要、需求摘要、价格上下文、风险上下文、允许动作、屏蔽字段。 | AI + 全栈。 | 小额开发。 | 每次 AI 调用绑定 `context_id`。 | 敏感信息乱进模型，输出不可复盘。 |
| AI Gateway | 防止 H5/App/脚本散调模型。 | 所有模型调用统一入口。 | 接口包括 `/ai/extract_asset`、`/ai/estimate_value`、`/ai/risk_check`、`/ai/match_demand`、`/ai/generate_listing_copy`。 | 全栈。 | ¥1k–6k/月服务器或复用现有服务。 | 每次调用有 `ai_run_id`、模型、prompt 版本、token、耗时、结果。 | 换模型、算成本、查错误都困难。 |
| 成本账本 | 接公司非人力 UE 公式。 | 建 `ai_cost_ledger`。 | 记录 case、功能、模型、输入/输出/cache token、模型成本、服务器分摊、第三方服务、UE bucket。 | AI + 全栈。 | P0 核心。 | 能回答今天 AI 花多少钱、哪个功能最贵、单 case AI 成本多少。 | 10 月非人力 UE 无法归因。 |
| HITL 边界 | 防止越权事故。 | 明确 AI 可建议、不可执行的动作。 | 最终价格、支付、退款、赔付、成交承诺、密码、验证码、自动交付全部人审或禁止。 | AI 定规则，业务执行。 | 无直接预算。 | 禁区清单进产品和研发需求。 | AI 自动化越权，风险不可控。 |
| 前端 AI 感知点 | 不能只是后端调模型。 | 至少上线卖家 AI 估号、买家 AI 找号；最好有 AI 账号卡。 | 估号展示识别结果、缺失证据、估值区间、风险提示；找号展示需求标签、推荐理由、风险说明。 | 产品 + 前端 + AI。 | 主站开发不计入 AI 预算。 | 用户能看到 AI 帮你估、帮你找、帮你看证据和风险。 | 对外仍像普通交易平台。 |
| 基础埋点 | 后续转化、采纳、UE 都靠它。 | 建卖家、买家、运营三条漏斗事件。 | 事件带 `event_id`、`user_id`、`case_id`、`asset_id`、`demand_id`、`ai_run_id`、`feature_name`、`source`、`timestamp`。 | 产品 + 研发。 | 现有埋点优先。 | 三条漏斗能查完整链路。 | AI 效果只能靠感觉。 |
| 上线样本 | P0 验收不是大规模评测。 | 30–50 个真实 case 端到端跑通。 | 覆盖成品号回收 10、售卖 10、买家找号 10、Steam 10、高风险/异常 5–10。 | AI + 数据风控 + 业务。 | 模型小成本。 | 每个样本有输入、AI 输出、成本、人审、结果。 | Demo 能跑，真实业务不能跑。 |

### 4.4 P1：上线后 2–4 周补齐

| P1 项 | 做什么 | Owner | 验收 | 预算口径 |
|-|-|-|-|-|
| AI Deal File 工作台 | 一单一页看账号、证据、AI 判断、人工决策、结果。 | 全栈 + AI。 | 运营能处理真实 case。 | 工程人力为主。 |
| 200–500 个 gold cases | 建人工确认过的标准样本。 | 数据风控 + 业务。 | 覆盖主流程。 | 不应全算 AI 预算。 |
| 风险标签 v1 | 找回、证据不足、价格异常、绑定异常、卖家异常。 | 数据风控 + 业务。 | 高风险 case 都有标签。 | 人力为主。 |
| AI 采纳/拒绝原因 | 运营拒绝或修改 AI 必须选原因。 | 产品 + 运营。 | 拒绝/修改原因可统计。 | 小。 |
| OCR/视觉抽取 | Top 游戏截图字段抽取。 | AI + 全栈。 | 可抽关键字段。 | ¥2k–20k/月。 |
| 库存 AI 丰富 | 1 万成品号 + 4000 Steam 加标签、卖点、风险。 | 运营 + AI。 | 70%+ 库存有 AI 标签。 | 模型批处理。 |
| AI 成本看板 | 按功能、模型、case 看成本。 | 全栈 + 数据。 | 每日可看成本。 | 小。 |
| 前端反馈 | 推荐准不准、估价是否接受。 | 产品。 | 有反馈按钮和数据。 | 小。 |

### 4.5 P2：8–9 月留口子并放大

| P2 项 | P0 现在留什么口子 | 后续做什么 |
|-|-|-|
| 游戏字段本体 | `game_field_definition`。 | 扩展腾讯、网易、米哈游、巨人、Steam。 |
| 相似案例检索 | 保存 case、asset、outcome、summary。 | 找历史相似账号和成交价。 |
| 向量库 | 保留文本摘要和 ID。 | 语义找号、相似案例检索。 |
| 工作流状态机 | `current_step`、`sop_step`。 | 更复杂半自动流程。 |
| BI/数据仓库 | 事件和成本数据完整。 | MRR、UE、风险、转化分析。 |
| A/B 实验 | 埋点带版本号。 | 推荐/估价策略对比。 |
| 商家能力 | 区分 `merchant_id`。 | 外部商家 SaaS 化。 |

### 4.6 P3：未来壁垒，现在不做

| P3 项 | 为什么现在不做 |
|-|-|
| 自动砍价 | 涉及承诺和价格风险，P0/P1 不成熟时不适合自动执行。 |
| 自动最终定价 | 先 AI 建议、人审；数据够了再逐步放权。 |
| 自动交付 | 涉及账号控制权、密码、纠纷，高风险。 |
| 大规模微调 | 没有足够高质量 gold cases 前意义有限。 |
| 私有化大模型 | 当前最大问题不是模型，而是数据闭环和交易动作闭环。 |
| 全自动 agent | 先让 AI 做判断，再逐步放动作权限。 |
| 完整商家 AIOS | 内部号商试验田跑通后再产品化。 |

---

## 5. 数据架构：为什么新平台数据直接进 MySQL

> 飞书表格的问题不是“不好用”，而是不适合作为 AI 交易平台的生产数据底座。业务刚起步，没有必要把临时表格做成长期架构。

### 5.1 目标架构

```text
H5 / App / 内部工作台
        ↓
现有后端 API
        ↓
现有 MySQL / RDS
        ↓
AI Gateway
        ↓
DeepSeek / Qwen / OCR / 视觉模型
```

证据文件：

```text
截图 / 视频 / 聊天文件 / 账号证明
        ↓
OSS / 现有文件服务
        ↓
MySQL evidence 表保存文件地址和元数据
```

### 5.2 MySQL 的必要性

| 平台需要 | 继续靠飞书的后果 | MySQL 的价值 |
|-|-|-|
| 稳定唯一 ID | case、账号、证据、AI 判断对不起来。 | 天然支持主键和关联关系。 |
| 状态流转 | 不知道 case 到哪一步。 | 可以记录 `current_step` 和状态变化。 |
| 多对象关联 | 账号、买家、证据、订单、AI 判断全散。 | 可以把 AccountAsset、DealCase、Evidence 等串起来。 |
| API 稳定读写 | H5/App 绕表格 API，风险高。 | 后端可稳定查询和写入。 |
| 成本账本 | 非人力 UE 算不清。 | `ai_cost_ledger` 可按 case、功能、模型归因。 |
| 字段版本 | 表格改列容易破坏历史数据。 | `game_field_definition` 可版本化。 |
| 事件日志 | 用户如何使用 AI 不可追踪。 | `event_log` 支撑转化、采纳、UE 分析。 |

### 5.3 飞书表格退场策略

| 情况 | 处理 |
|-|-|
| 6 月以前已有飞书数据 | 一次性导入 MySQL。 |
| 短期业务还在飞书录入 | 最多 2–4 周临时单向同步。 |
| H5/App 新产生的数据 | 直接写 MySQL。 |
| 长期平台数据 | 不再走飞书表格。 |
| 飞书文档和 Wiki | 可以继续做知识管理、会议纪要、决策文档。 |

如果必须迁移飞书旧数据：

```text
飞书原始表
   ↓
MySQL import_feishu_xxx 临时表
   ↓
清洗成 account_asset / deal_case / evidence 等正式业务表
```

### 5.4 AI 阅读材料包：`ai_case_context`

AI 阅读材料包不是复杂合规系统，而是每次 AI 判断前给模型的一份案件材料。AI 只读必要信息，不直接读全部原始表。

| 字段 | 说明 |
|-|-|
| `context_id` | 材料包 ID。 |
| `case_id` | 属于哪个 case。 |
| `asset_summary` | 账号摘要。 |
| `evidence_summary` | 证据摘要。 |
| `buyer_demand_summary` | 买家需求摘要。 |
| `price_context` | 价格相关信息。 |
| `risk_context` | 风险相关信息。 |
| `allowed_actions` | AI 允许做什么。 |
| `blocked_fields` | 哪些字段不允许给 AI。 |
| `version` | 材料包版本。 |
| `created_at` | 生成时间。 |

AI 可以看：游戏、区服、段位、皮肤、卖家报价、证据完整度、历史类似成交、风险标签、当前步骤。

AI 不应该看：密码、验证码、token、cookie、支付账号、完整手机号、身份信息、不相关的原始聊天全文。

### 5.5 P0 最小数据对象

| 对象 | 业务解释 | 最小字段 |
|-|-|-|
| AccountAsset | 这个号到底是什么。 | `asset_id`、`game_id`、`game_family`、`account_type`、`server_region`、`asset_summary`、`asset_facts_json`、`source`、`current_status`、`schema_version`。 |
| DealCase | 围绕账号或需求的一次业务处理。 | `case_id`、`case_type`、`asset_id`、`demand_id`、`current_step`、`case_status`、`sop_version`、`owner_id`、`priority`、`created_at`。 |
| Evidence | 支撑价值、安全、风险判断的证据。 | `evidence_id`、`case_id`、`asset_id`、`evidence_type`、`file_url`、`extracted_text`、`extracted_facts_json`、`confidence`、`privacy_level`、`created_at`。 |
| BuyerDemand | 买家到底想要什么号。 | `demand_id`、`user_id`、`game_id`、`budget_min`、`budget_max`、`must_have_json`、`nice_to_have_json`、`urgency`、`parsed_from`、`created_at`。 |
| AIRun | AI 做过什么判断。 | `ai_run_id`、`case_id`、`feature_name`、`model_name`、`prompt_version`、`input_context_id`、`output_json`、`confidence`、`latency_ms`、`status`、`created_at`。 |
| HumanDecision | 人是否采纳 AI，为什么。 | `decision_id`、`case_id`、`ai_run_id`、`decision_type`、`decision_result`、`reason_code`、`operator_id`、`created_at`。 |
| CaseOutcome | 最后这单到底怎么样。 | `outcome_id`、`case_id`、`result`、`gmv`、`revenue`、`gross_profit`、`days_to_sell`、`dispute_flag`、`refund_flag`、`risk_loss`、`closed_at`。 |

---

## 6. SOP → AI Opportunity Map

> SOP 本身由业务/产品拆。AI 团队不重拆业务流程，而是把 SOP 转成 AI 能力、数据对象、HITL 边界和平台可复用资产。

### 6.1 业务/产品交付 SOP 的模板

| 字段 | 说明 |
|-|-|
| `step_id` | 步骤编号。 |
| `step_name` | 步骤名称。 |
| `business_line` | 成品号回收、成品号售卖、Steam 生产、Steam 售卖、买家找号等。 |
| `game_scope` | 腾讯、网易、米哈游、巨人、Steam 或具体游戏。 |
| `current_operator` | 现在谁在做。 |
| `input` | 这一步需要什么信息。 |
| `output` | 这一步产出什么。 |
| `decision_rule` | 人现在怎么判断。 |
| `risk_level` | 是否涉及钱、密码、验证码、支付、账号控制权、纠纷。 |
| `current_time_cost` | 大概耗时。 |
| `common_error` | 常见错误。 |
| `final_result` | 怎么证明这一步做对了。 |

### 6.2 AI 团队的判断矩阵

| 判断项 | 要回答的问题 | 可选结果 |
|-|-|-|
| 步骤类型 | 这一步本质是什么。 | 信息抽取、估价、风险判断、推荐匹配、话术生成、执行动作、复盘。 |
| 输入数据 | AI 要看什么。 | 文本、截图、聊天、库存、历史成交、人工判断。 |
| 输出结果 | 这一步要沉淀什么。 | 字段、标签、建议价、风险分、推荐列表、下一步动作。 |
| 自动化等级 | AI 能做到哪一步。 | AI-assisted、AI+HITL、Human-only、Forbidden。 |
| 人审边界 | 为什么需要人审。 | 涉钱、涉密码验证码、涉最终承诺、高金额、低置信、高风险。 |
| 数据沉淀 | 是否能成为平台资产。 | 只服务号商、可复用到平台、可训练评测、可进 UE 计算。 |
| 产品入口 | 用户或运营在哪里感知。 | 卖家估号、买家找号、AI 账号卡、内部 Deal File。 |
| 验收方式 | 怎么知道这一步有用。 | 采纳率、准确率、时间下降、成交提升、风险减少、成本可控。 |

### 6.3 四类边界

| 类型 | 定义 | 例子 |
|-|-|-|
| AI-assisted | AI 可直接完成低风险结构化或生成建议。 | 截图字段抽取、买家需求解析、标题卖点生成。 |
| AI+HITL | AI 给建议，人做最终判断。 | 估价区间、风险判断、砍价话术、推荐排序。 |
| Human-only | 必须人操作或审批。 | 最终报价、高风险账号、纠纷处理、上架承诺。 |
| Forbidden | AI 不允许接触或执行。 | 密码、验证码、支付、退款、自动成交、保证安全。 |

---

## 7. 产品 V0 与前端 AI 感知

> 用户不应该只看到一个“AI 聊天框”。AI-native 的前端表达应该让用户直接感知：AI 帮你估、帮你找、帮你比、帮你看证据、帮你看风险。

### 7.1 卖家 AI 估号

```text
我要卖号
  ↓
选择游戏
  ↓
上传截图 / 填基础信息
  ↓
AI 识别账号资产
  ↓
展示识别结果、缺失证据、估值区间、风险提示
  ↓
提交人工复核 / 继续补充材料
```

前端必须展示：

- AI 已识别出的资产。
- 还缺什么证据。
- 初步估价区间。
- 价格依据。
- 风险提示。
- 提交人工复核入口。

### 7.2 买家 AI 找号

```text
我要买号
  ↓
输入预算、游戏、偏好
  ↓
AI 解析需求
  ↓
展示需求标签
  ↓
推荐账号卡
  ↓
记录点击、联系、下单、反馈
```

前端必须展示：

- 预算标签。
- 游戏标签。
- 必须条件。
- 推荐理由。
- 风险或证据完整度。
- 2–3 个账号对比。

### 7.3 AI 账号卡

| 模块 | 内容 |
|-|-|
| AI 卖点 | 这个号最值钱的点。 |
| AI 风险 | 证据缺失、绑定风险、异常价格。 |
| AI 价格说明 | 为什么是这个价。 |
| AI 匹配理由 | 为什么适合买家。 |
| 证据完整度 | 有哪些证据，还缺什么。 |

### 7.4 三条基础埋点漏斗

| 漏斗 | 事件 |
|-|-|
| 卖家漏斗 | `sell_ai_entry_view`、`sell_ai_start`、`sell_game_selected`、`sell_evidence_uploaded`、`sell_ai_extract_done`、`sell_missing_evidence_shown`、`sell_ai_price_shown`、`sell_submit_review`、`sell_quit`。 |
| 买家漏斗 | `buy_ai_entry_view`、`buy_ai_start`、`buy_demand_input`、`buy_demand_parsed`、`buy_recommendation_shown`、`buy_listing_click`、`buy_contact_or_order`、`buy_no_match_feedback`。 |
| 运营漏斗 | `ops_case_created`、`ops_ai_suggestion_view`、`ops_ai_accept`、`ops_ai_modify`、`ops_ai_reject`、`ops_escalate_risk`、`ops_case_closed`、`ops_outcome_recorded`。 |

每个事件都要带：`event_id`、`user_id`、`case_id`、`asset_id`、`demand_id`、`ai_run_id`、`feature_name`、`source`、`timestamp`。

---

## 8. 如果 Palantir 来做，会怎么做

> 这不是让 Palantir 背书，而是借鉴它的核心逻辑：先把真实业务拆成 Objects、Links、Actions、Decisions、Metrics，再用真实纵切片证明 AI 能进入业务动作闭环。

### 8.1 Palantir 式核心框架

| 概念 | 含义 | 游戏账号交易映射 |
|-|-|-|
| Object | 真实世界对象或事件。 | AccountAsset、DealCase、Seller、Buyer、Evidence、Listing、Order、Dispute。 |
| Property | 对象属性。 | 游戏、区服、段位、皮肤数、报价、风险分、状态、负责人。 |
| Link | 对象关系。 | Seller submits DealCase；DealCase has Evidence；BuyerDemand matches AccountAsset。 |
| Action | 改变对象或关系的业务动作。 | create_case、request_evidence、extract_asset、estimate_value、approve_quote、publish_listing。 |
| Decision | 人或 AI 对动作的判断。 | 收/不收、补证、砍价、上架、推荐、升级风险。 |
| Metric | 动作是否有效。 | 采纳率、估价误差、成交率、周转天数、纠纷率、AI 成本/单。 |

### 8.2 5 天打法

| 时间 | 他们会做什么 | 你们对应产物 |
|-|-|-|
| Day 1 | 贴业务跟单，找最高价值决策点，不开空泛需求会。 | 回收、售卖、找号三条流程的决策地图。 |
| Day 2 | 建 Ontology v0：对象、关系、动作、指标。 | 7 个最小对象 + 核心 actions + P0 表结构。 |
| Day 3 | 做卖家 AI 估号纵切片。 | 上传证据 → AI 抽取 → 估价/风险 → 人审报价 → 记录成本。 |
| Day 4 | 做买家 AI 找号纵切片。 | 需求解析 → 库存匹配 → 推荐解释 → 点击/转化埋点。 |
| Day 5 | 用真实 case 验收。 | 30–50 个 case，形成 P0 缺口清单和 P1 backlog。 |

### 8.3 三条纵切片

卖家 AI 估号：

```text
卖家提交账号
→ 上传截图/填写基础信息
→ 创建 DealCase + AccountAsset + Evidence
→ 生成 ai_case_context
→ AI 抽取资产字段
→ AI 输出缺失证据、估值区间、风险标签、下一步动作
→ 人审报价/拒绝/补证
→ 记录 HumanDecision
→ 关闭后写 CaseOutcome
→ 写入 AIRun + ai_cost_ledger
```

买家 AI 找号：

```text
买家输入预算、游戏、偏好
→ 创建 BuyerDemand
→ AI 解析 must_have / nice_to_have
→ 匹配 AccountAsset / Listing
→ 生成推荐理由和风险说明
→ 用户点击/联系/下单
→ 记录转化事件和 AI 成本
```

内部 AI Deal File：

```text
运营打开一个 case
→ 看到账号、证据、AI 估价、风险、历史类似 case、推荐动作
→ 选择采纳/修改/拒绝
→ 必填原因
→ 系统把人工决策回流为训练/评测数据
```

### 8.4 可借鉴原则

| 原则 | 对你们的意义 |
|-|-|
| 先纵切片，后平台化 | 不要先做半年大平台，先跑通真实交易动作闭环。 |
| 先动作闭环，后自动化 | AI 先做判断和建议，不急着执行高风险动作。 |
| 先可观测，后规模化 | 每次 AI 调用都要有输入、输出、成本、采纳、结果。 |
| 先业务对象，后功能清单 | 平台第一性原理是交易对象与动作，不是功能按钮。 |

---

## 9. 预算、UE 与激励

### 9.1 AI 团队该背的成本

| 成本项 | 是否 AI 团队预算 | 说明 |
|-|-|-|
| 模型 token | 是 | DeepSeek / Qwen / 其他模型调用成本。 |
| AI Gateway 增量服务 | 是或平台共享 | 如果独立部署，算 AI 服务服务器；如果复用现有后端，只算增量。 |
| AI 调用日志与成本账本 | 是 | `AIRun`、`ai_cost_ledger`、prompt 版本、token 记录。 |
| AI 相关 MySQL 增量 | 是，通常很小 | AI 表、上下文表、少量存储增量，不背整个数据库成本。 |
| OCR / 视觉识别 | P1 起算 | 只限账号截图识别、资产抽取等 AI 直接功能。 |
| 向量检索 / 相似案例 | P2 后算 | 用于估价、找号、推荐后进入 AI 预算。 |
| 外部 AI 工程/架构支持 | 可选 | 只在内部研发资源不足时采购。 |

### 9.2 AI 团队不该背的成本

| 成本项 | 应归属 |
|-|-|
| 平台流量 / CDN | 平台或增长。 |
| 主站 H5/App 研发 | 产品研发。 |
| 托管 / 生产 / 库存资金 | 业务。 |
| 法务 / 安全审计 / 备份体系 | 公司基础设施或职能部门。 |
| 标注 / 抽检 / 质检人力 | 业务 / 运营 / 数据共担，AI 只定义标准。 |
| 主数据库基础成本 | 平台基础设施。 |
| 客服 / 售后 / 仲裁人工 | 业务运营。 |

### 9.3 预算档位

| 档位 | 8 周预算 | 适用情况 |
|-|-|-|
| 极简版 | ¥5–10 万 | 研发资源充足，AI 只做模型调用、表、日志。 |
| 推荐版 | ¥15–30 万 | 最合理，覆盖 P0 + 部分 P1。 |
| 加速版 | ¥30–50 万 | 研发配合不足，需要外部工程补位。 |

对 CEO 的建议口径：

> AI 团队申请 8 周 AI 专项预算 ¥15–30 万，只覆盖模型、AI Gateway、AI 成本账本、AI 表结构、OCR/视觉和少量外部工程支持；如果现有研发资源无法及时配合，最高预留到 ¥50 万。

### 9.4 UE 口径

不重写公司非人力 UE 公式。AI 团队只负责把 AI 相关成本准确记账，并接入公司现有公式。

AI 侧只提供三类成本：

```text
token 成本
AI 服务器成本
AI 第三方服务成本
```

`ai_cost_ledger` 至少记录：

```text
case_id
feature_name
model_name
input_tokens
output_tokens
cache_hit_tokens
model_cost_rmb
server_cost_allocated_rmb
third_party_cost_rmb
ue_bucket
created_at
```

### 9.5 激励方案

6 月 P0 激励：

| 权重 | 指标 |
|-|-|
| 35% | P0 完成：AI Gateway、成本账本、AI 阅读材料包、HITL 边界。 |
| 25% | H5/App 至少 2 个 AI 前端感知点上线。 |
| 20% | 30–50 个真实 case 跑通，有输入、输出、成本、人审。 |
| 10% | 接入现有研发规范，不另起野系统。 |
| 10% | 无越权：不碰支付、密码、验证码、最终承诺。 |

7–8 月 P1 激励：

| 权重 | 指标 |
|-|-|
| 30% | AI 覆盖率：回收、售卖、找号 case 中 AI 处理比例。 |
| 25% | 数据质量：字段完整率、结果回流、gold cases 数量。 |
| 20% | AI 采纳率：业务是否采纳或有效使用 AI 建议。 |
| 15% | 成本：token、服务器、第三方服务能进入 UE 公式。 |
| 10% | 风险：高风险 case 召回，无 P0 事故。 |

Q4 激励：

| 指标 | 说明 |
|-|-|
| AI-attributed MRR | AI 估号、找号、推荐、商家工具带来的收入。 |
| AI 成本/有效 case | token、服务器、第三方服务是否可控。 |
| AI 贡献非人力 UE | 接公司现有公式，不另造。 |
| 转化提升 | AI 入口 vs 非 AI 入口。 |
| 效率提升 | 初判、上架、匹配、复盘时间下降。 |

---

## 10. 团队定位、组织流程与 45 分钟组会

### 10.1 RACI

| 事项 | AI 团队 | 业务 | 产品 | 研发 | CEO |
|-|-|-|-|-|-|
| SOP v0 | 审核并转 AI 判断矩阵 | DRI | 共创产品流程 | 评估系统承载 | 授权优先级 |
| AI 数据对象 | DRI | 确认业务含义 | 对齐产品字段 | 落库和接口 | 授权 |
| AI Gateway / 成本账本 | DRI | 使用结果 | 用于产品指标 | 实现和发布 | 预算拍板 |
| 最终交易动作 | 给建议和门禁 | DRI | 设计操作体验 | 保障系统执行 | 关键规则拍板 |
| H5/App 体验 | 定义 AI 表达和埋点 | 反馈流程 | DRI | DRI | 目标拍板 |
| AI 禁区 | 定义规则 | 执行 | 文案避险 | 权限和日志 | 组织授权 |

### 10.2 三人小组定位

| 角色 | 当前重点 | 不要做成 |
|-|-|-|
| AI 负责人 | AI 战略、OKR、CEO 对齐、P0 闸门、SOP 到 AI 判断矩阵、预算口径。 | 亲自重拆全部业务 SOP。 |
| 数据风控小伙伴 | 字段、风险标签、case 结果、gold cases、质量看板。 | 把所有标注、质检人力都背到 AI 团队。 |
| 全栈工程师 | AI 小组和原研发体系的规范桥梁：主库、API、auth、部署、日志、埋点、review、AI Gateway 归属。 | 另起一套 AI demo 野系统。 |

### 10.3 第一次组会：45 分钟

| 时间 | 议题 | 产出 |
|-|-|-|
| 0–5 分钟 | 定调 | AI 团队不拆业务 SOP，而是把 SOP 转成 AI opportunity map。 |
| 5–15 分钟 | SOP 输入格式 | 业务/产品交给 AI 团队的 SOP 必须包含输入、输出、判断标准、风险、结果验证。 |
| 15–25 分钟 | SOP → AI 判断矩阵 | 统一每一步怎么判断：AI-assisted / AI+HITL / Human-only / Forbidden。 |
| 25–32 分钟 | 产品形态想法 | 只讨论 AI-native 怎么被用户感知：估号、找号、账号卡、风险/证据提示。 |
| 32–40 分钟 | 全栈作为研发规范桥梁 | 问清技术栈、数据库、API、登录、埋点、部署、review、回滚规范。 |
| 40–45 分钟 | 激励和风险想法 | 收集大家对 AI 团队评价指标、最大机会、最大风险的判断。 |

你可以开场说：

> 今天不讨论“大而全 AI 平台”。我们只对齐一件事：业务/产品拆 SOP，AI 团队把每一步转成 AI 能力、数据对象、HITL 边界和平台可复用资产。

### 10.4 问全栈同学的问题

| 主题 | 要问的问题 |
|-|-|
| 技术栈 | 现在后端语言、框架、服务拆分方式是什么。 |
| 数据库 | 主库是不是 MySQL，是阿里云 RDS 还是自建。 |
| 表结构 | 有没有 migration 规范，谁 review 表设计。 |
| API | H5/App 调后端的接口规范是什么，有没有 OpenAPI/接口文档要求。 |
| 登录权限 | `user_id`、`merchant_id`、`operator_id` 怎么拿，AI 服务能否复用现有鉴权。 |
| 文件上传 | 账号截图、证据文件现在走什么文件服务。 |
| 埋点 | 有没有现成埋点体系；没有的话 P0 是否先落 MySQL `event_log`。 |
| 日志链路 | `trace_id`、`request_id`、`case_id` 现在怎么串。 |
| 密钥配置 | DeepSeek/Qwen/API key 放哪里，谁有权限。 |
| 部署环境 | dev / staging / prod 怎么发，谁负责发布。 |
| 灰度回滚 | AI 功能能否 feature flag，模型挂了怎么降级。 |
| 代码协作 | 分支、PR、review、发布节奏怎么跟原研发一致。 |
| AI Gateway | 应该独立服务，还是放进现有后端，边界怎么定。 |
| 禁止事项 | 哪些库、接口、流程 AI 小组不能绕过。 |

---

## 11. OKR / KR 建议

### 11.1 建议 AI Objective

> 建立 AI-native 账号交易平台 V0 的最小闭环，支撑 6 月 H5/App 上线，并让号商 SOP 成为平台 AI 数据和能力试验田。

### 11.2 AI KR

| KR | 指标 |
|-|-|
| KR1 | 6 月中旬前完成 SOP → AI opportunity map，覆盖回收、售卖、Steam 生产/售卖、买家找号关键步骤。 |
| KR2 | 6 月中旬前完成 MySQL 最小数据结构：AccountAsset、DealCase、Evidence、BuyerDemand、AIRun、HumanDecision、CaseOutcome。 |
| KR3 | 6 月中旬前完成 AI Gateway v0，所有模型调用可记录 token、成本、case、功能模块。 |
| KR4 | 6 月下旬 H5 上线至少 2 个用户可感知 AI 入口：卖家 AI 估号、买家 AI 找号。 |
| KR5 | 6 月底 App 复用同一 AI API，不另做一套。 |
| KR6 | 6 月底前完成 30–50 个真实 case 的 AI 验收样本。 |
| KR7 | 7 月完成 P1：AI Deal File 工作台、200+ gold cases、风险标签 v1、AI 成本看板。 |
| KR8 | 10 月前 AI 成本项能接入公司非人力 UE 公式，至少覆盖 token、AI 服务器、AI 第三方服务。 |

---

## 12. 禁止宣传与禁止自动化清单

| 类别 | 禁止内容 | 可替代表述 |
|-|-|-|
| 交易 | AI 自动成交、自动付款、自动退款、自动放款、自动确认收货。 | AI 生成建议和 checklist，人完成高影响动作。 |
| 账号控制 | 自动登录、自动换绑、自动找回、读取验证码、读取 cookie/token。 | AI 只处理必要、可追踪的证据摘要和人工确认结果。 |
| 估价 | 保证估价准确、保证能卖出。 | AI 给参考区间、依据和置信度，最终由人审。 |
| 风控 | 保证账号安全、保证无找回、保证无纠纷。 | AI 提示风险和缺失证据，高风险 case 升级人工。 |
| 产品表达 | AI-native = 聊天框、机器人、打字动画。 | AI-native = 事实结构化、证据缺口、风险解释、HITL 和结果回流。 |

---

## 13. 附录：用户问题覆盖矩阵

| 用户问题 | 覆盖章节 | 处理方式 |
|-|-|-|
| 各个 PT 因 AI-native 而来的第一性原理是什么 | 第 3 章 | 按号商、平台、AI、数据、团队、UE 六块拆。 |
| 号商工作第一性原理、最小单元 SOP、AI/HITL/结合 | 第 4、6 章 | P0 闸门 + SOP 到 AI 判断矩阵。 |
| 产品/平台第一性原理，核心功能由什么支持 | 第 7 章 | 卖家估号、买家找号、AI 账号卡和交易控制面。 |
| 团队第一性原理 | 第 10 章 | AI-native 交易控制面 DRI + RACI。 |
| OKR 拆 KR | 第 11 章 | Objective + 8 条 KR。 |
| 产品/平台设计路线图 | 第 4 章 | P0/P1/P2/P3 分级路线。 |
| 号商维持现状，AI 团队除了 SOP 还需要什么 | 第 4、5、6 章 | 数据对象、证据链、AI 判断、人审、结果、成本。 |
| AI 平台真正启动点、缺哪些基建、需要多久 | 第 4 章 | 普通平台 vs AI 交易平台 V0，P0/P1/P2/P3。 |
| 国内 AI 基建、预算、MECE 不漏不浅 | 第 5、9 章 | MySQL、文件服务、AI Gateway、成本账本、预算拆账。 |
| AI 团队激励方案 | 第 9.5 章 | 6 月、7–8 月、Q4 三阶段。 |
| 飞书多维表格以后是什么，MRR 1000 万时是什么 | 第 5.3 章 | 飞书退场策略，新平台数据直写 MySQL。 |
| 第一版产品上线前必须做什么，上线后做什么，前端 AI 元素 | 第 4、7 章 | P0 上线闸门 + P1 补齐 + 三个前端 AI 感知点。 |
| 预算预算预算 | 第 9 章 | AI 团队该背/不该背、预算档位、UE 成本接入。 |
| 今天第一次组会讨论什么，三人如何协作 | 第 10 章 | 45 分钟议程 + 三人定位。 |
| 全栈如何与旧研发保持规范一致，组织流程怎么搞 | 第 10.4 章 | 技术规范问题清单，定义全栈为研发规范桥梁。 |
| 需要和 CEO 说什么，团队地位是什么 | 第 1、10 章 | AI 交易控制面 DRI、P0 闸门、预算、成本口径。 |
| Q1：平台到底能不能上线，哪些 P0/P1/P2/P3 | 第 4 章 | 明确普通平台可上线；AI 交易平台 V0 必须过 P0。 |
| Q1：预算、时间线、激励要配套写好 | 第 4、9、10、11 章 | 阶段预算、阶段激励、阶段 KR。 |
| Q1：模型、云、数据、MySQL、AI 阅读材料包要讲清楚 | 第 5、9 章 | 优先现有 MySQL/RDS、OSS/现有文件服务、AI Gateway。 |
| Q1：不要把别的部门成本放进 AI 团队 | 第 9.1、9.2 章 | 明确该背和不该背。 |
| Q1：飞书表格是不是最优选 | 第 5.3 章 | 不是长期主数据源，只做迁移或短期过渡。 |
| Q1：组会改为 45 分钟，SOP 谁拆 | 第 6、10 章 | 业务/产品拆 SOP，AI 团队转判断矩阵。 |
| Q2：P0/P1/P2/P3 不够细，要讲怎么做 | 第 4 章 | P0 每项写为什么、做什么、怎么做、Owner、预算、验收、不做后果。 |
| Q2：SOP 80% 准，20% 怎么留口子 | 第 4.3、5.5、6 章 | `sop_template`、`sop_step`、`game_field_definition`、版本化。 |
| Q2：最小统一数据对象帮我定好 | 第 5.5 章 | 7 个最小对象。 |
| Q2：不用飞书表，用 MySQL 的必要性是什么 | 第 5.2、5.3 章 | 用唯一 ID、状态流转、关联关系、成本账本、API、事件日志解释。 |
| Q2：假设 Palantir 来做会怎么做 | 第 8 章 | Objects、Links、Actions、Decisions、Metrics + 5 天纵切片。 |

---

## 14. 参考来源与价格复核提醒

| 主题 | 官方来源 |
|-|-|
| DeepSeek API 价格 | [https://api-docs.deepseek.com/quick_start/pricing-details-cny](https://api-docs.deepseek.com/quick_start/pricing-details-cny) |
| 阿里云百炼模型价格 | [https://help.aliyun.com/zh/model-studio/model-pricing](https://help.aliyun.com/zh/model-studio/model-pricing) |
| 阿里云 RDS | [https://help.aliyun.com/zh/rds/](https://help.aliyun.com/zh/rds/) |
| 阿里云 OSS | [https://help.aliyun.com/zh/oss/](https://help.aliyun.com/zh/oss/) |
| Palantir Ontology | [https://www.palantir.com/docs/foundry/ontology/overview/](https://www.palantir.com/docs/foundry/ontology/overview/) |
| Palantir Actions | [https://www.palantir.com/docs/foundry/workshop/actions-overview/](https://www.palantir.com/docs/foundry/workshop/actions-overview/) |
| Palantir AIP Observability | [https://www.palantir.com/docs/foundry/aip-observability/overview/](https://www.palantir.com/docs/foundry/aip-observability/overview/) |
| Palantir AIP Bootcamp | [https://www.palantir.com/platforms/aip/bootcamp](https://www.palantir.com/platforms/aip/bootcamp) |

价格和模型能力变化很快，采购前必须重新看官方价格页。本文档只给预算口径，不把任何具体报价写成长期承诺。
