---
{
  "asset_key": "PAGE::project::agent_workspace::aios4game-evidence-gap-resolver-v0-2-sync",
  "links_to": [
    "project::agent_workspace::index",
    "project::agent_workspace::log",
    "project::agent_workspace::execution-readiness-report",
    "project::agent_workspace::handoff-risks-report"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::aios4game-evidence-gap-resolver-v0-2-sync",
  "page_type": "Report",
  "portfolio_key": "portfolio::default",
  "source_ids": [],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "AIOS4game Evidence Autopilot v0.3 Sync Brief"
}
---

# AIOS4game 交易证据自动驾驶 v0.3

更新时间：2026-05-26 14:00 +08:00

## 先说人话

v0.2 像一份检查报告：材料够不够、缺什么、谁去补。

v0.3 往前走了一步，变成一个本地 agent run。它会按固定流程把一单材料往前推，报告只是最后留下来的产物之一：

```Plain Text
Agent Run -> Evidence -> Claim Graph -> HITL Gate -> Human Task -> Decision Gate


```

这句话翻成人话就是：

> 系统先自己把本地材料读完、分类、校验、建图、找冲突、生成任务；碰到凭证、账号控制、支付、认证、远程写入、不可逆动作时停住，交给人。

所以它不是交易自动驾驶。它只是交易证据自动驾驶。

## 一张图看懂

```Plain Text
┌────────────────┐
│ 1. 收到 case   │  读取 case.json / evidence_manifest / policy
└───────┬────────┘
        ↓
┌────────────────┐
│ 2. agent run   │  记录 run_state 和 agent_events
└───────┬────────┘
        ↓
┌────────────────┐
│ 3. 找证据来源   │  本地可读 / 要人补 / 要授权导出 / 未来依赖 / 禁止碰
└───────┬────────┘
        ↓
┌────────────────┐
│ 4. 解析材料     │  JSON / CSV / Markdown / TXT；图片只登记，不识别
└───────┬────────┘
        ↓
┌────────────────┐
│ 5. 建 claim 图  │  evidence -> claim -> requirement -> gap
└───────┬────────┘
        ↓
┌────────────────┐
│ 6. 过 HITL gate│  高风险动作停住；禁入材料直接挡住
└───────┬────────┘
        ↓
┌────────────────┐
│ 7. 出任务和报告 │  谁补、补什么、验收标准、当前能不能进下一审
└────────────────┘


```

## 这次到底升级了什么

| 模块 | v0.2 | v0.3 |
|-|-|-|
| 产品形态 | 证据缺口报告 | 本地 agent workflow |
| 主界面 | `static_report.html` | `run_console.html` |
| 过程记录 | `audit_log.json` | `run_state.json` + `agent_events.jsonl` |
| 证据关系 | 缺口矩阵 | claim graph |
| 来源判断 | 只看 evidence/requirement | source resolution |
| 风险边界 | policy 里声明才挡 | 关键敏感/账号/支付类材料全局挡 |
| 飞书 | 只归档 | 仍然只归档，不进 runtime |

## 现在的产物

v0.3 跑完一个 case 后，会生成这些文件：

| 文件 | 给谁看 | 用来干什么 |
|-|-|-|
| `run_console.html` | 运营/审核人 | 第一屏看当前卡点、已完成步骤、需要人做的事 |
| `run_state.json` | 系统/开发 | 记录这一轮 run 的状态和边界 |
| `agent_events.jsonl` | 审计/排查 | 每一步 agent 做了什么、产物是什么 |
| `source_resolution.json` | 审核/开发 | 每个来源是本地可读、要人补、要授权、未来依赖还是禁止 |
| `parsed_claims.json` | 审核/开发 | 从本地结构化材料里得到的保守声明 |
| `claim_graph.json` | 审核/开发 | evidence、claim、requirement、gap 之间的关系 |
| `gate_decision.json` | 审核/运营 | 当前是 clear、HITL required，还是 no-go |
| `report.html` / `evidence_gap_report.md` | 归档 | 给飞书或内部文档保存 |

## case_001 现在是什么状态

| 项目 | 结果 | 人话解释 |
|-|-|-|
| 当前结论 | `no-go` | 证据包还不能进入下一步人工审核 |
| 当前卡点 | 缺绑定状态证明 | blocker 不补，后面不能判断 |
| 第二卡点 | 缺平台订单导出 | 需要授权导出，或者人工明确拿不到 |
| 自动完成 | 已完成 | 已读取 case、选 policy、分类来源、登记材料、生成 claim graph 和报告 |
| 需要人做 | 有 | 补绑定状态证明、补平台订单导出 |
| 禁止碰 | 有 | 凭证、身份、人脸、支付、账号控制类动作不进 runtime |

这单的意思不是“账号有问题”。意思只是：现在证据不够，不能继续往下判断。

## 9 个 fixture 的跑批结果

| Case | 结果 | 说明 |
|-|-|-|
| `case_go_complete` | `go` |  |
| `case_legacy_manifest` | `go` | 老 manifest 仍兼容 |
| `case_future_dependency` | `hold` | 有缺口要靠未来能力解决 |
| `case_hold_image_only_binding` | `hold` | 只有图片，不够；图片只登记，不抽事实 |
| `case_integration_missing` | `hold` | 需要授权导出或集成 |
| `case_001` | `no-go` | blocker 证据缺失 |
| `case_blocked_secret` | `no-go` | 出现禁入敏感材料 |
| `case_conflict_bad_export` | `no-go` | 导出文件坏了或不满足验收 |
| `case_no_go_missing_blocker` | `no-go` | blocker 证据缺失 |

## 最重要的边界

v0.3 的“自动驾驶”只发生在本地证据流程里。

它能做：

| 能力 | 说明 |
|-|-|
| 读本地 case folder | 只读人给的文件 |
| 校验结构化材料 | JSON / CSV / Markdown / TXT |
| 登记图片 |  |
| 生成 claim graph | 只是材料之间的声明关系，不是真假裁判 |
| 找证据缺口 | 对照 required evidence policy |
| 生成任务 | 写清谁补、补什么、验收标准 |
| 生成报告和 console | 本地 HTML / Markdown / CSV / JSON |

它不能做：

| 不做的事 | 原因 |
|-|-|
| 登录游戏或平台账号 | 涉及账号安全和凭证 |
| 付款、退款、放款、确认收货 | 涉及资金和不可逆动作 |
| 换绑、转移、找回账号 | 涉及账号控制权 |
| 判断价格一定准确 | 没有市场成交数据和评测闭环 |
| 判断买卖双方心理状态 | 当前证据不能可靠证明 |
| 默认写飞书 | 远程写入必须另行确认 |

## 这次修掉的安全问题

6 个 reviewer 里，Safety / Privacy reviewer 提了一个真正的 blocker：

> 如果普通文本文件里藏了 token、验证码、身份证、人脸等敏感标记，旧逻辑会先 hash 和 normalize，再在 validator 里发现问题。

这次已经改成：

```Plain Text
先做敏感内容预检查
命中后直接 quarantine
不 hash
不 normalize
不进 inventory
不进 claim graph
不进公开 HTML


```

另一个问题也一起修了：

> 支付、放款、确认收货、换绑、转移、找回这类材料，即使 policy 没写 forbidden，也不能被当普通证据处理。

现在这些类型全局阻断，不依赖单个 case 的 policy 是否写对。

## 测试结果

| 检查项 | 结果 |
|-|-|
| Unit tests | 52 个通过 |
| v0.2 旧 CLI | 保留 |
| v0.3 单 case CLI | 通过 |
| v0.3 batch CLI | 通过，已跑 9 个 fixture |
| `run_console.html` | 已生成 |
| `agent_events.jsonl` | 已生成 |
| `claim_graph.json` | 已生成 |
| 禁止越界承诺扫描 | 通过 |
| 飞书写入 | 不在 runtime 内，只做这次人工确认后的同步 |

本地验证命令已经跑过：

```Bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m aios4game_evidence.cli \
  --autopilot \
  --cases-root cases \
  --run-dir runs


```

## 现在怎么用

旧方式还在：

```Bash
PYTHONPATH=src python3 -m aios4game_evidence.cli \
  --case-dir cases/case_001 \
  --output-dir output/case_001


```

新方式是：

```Bash
PYTHONPATH=src python3 -m aios4game_evidence.cli \
  --autopilot \
  --case-dir cases/case_001 \
  --run-dir runs/case_001


```

批量跑：

```Bash
PYTHONPATH=src python3 -m aios4game_evidence.cli \
  --autopilot \
  --cases-root cases \
  --run-dir runs


```

## 下一步建议

不要马上做交易平台，也不要把它包装成“能替人做交易”。

下一步最值的是拿 5 到 10 个真实但脱敏的 case folder 试跑，盯三件事：

1. 从收到材料到生成可执行任务，时间有没有下降。
2. 上架或估价前，关键证据完整率有没有提高。
3. 因缺证据导致的返工、升级、纠纷有没有减少。

如果这三项没有改善，它还是工具；如果改善明显，再考虑把 `run_console.html` 做成真正的多人工作台。
