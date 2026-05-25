# Optional Analysis Capabilities

`lark-wiki` 的主流程是本地 Markdown 加 `lark-cli`。可选分析层只做两件事：帮你把论文证据放稳，帮相关页面互相找到。

## LLM Provider

LLM provider 只处理你明确传入的来源，用来生成摘要、提示可能的冲突和遗漏。不开也可以跑确定性的编译、同步和 `inventory`。

```toml
[llm]
provider = "auto"
model = "gpt-5.4-mini"
timeout_seconds = 180
semantic_lint_enabled = true
```

## Knowledge Relation Map

Knowledge Relation Map 的第一版先回答四个实际问题：

- 这个 namespace 里有哪些页面和来源，可以用 `inventory` 先列出来
- 页面、来源、项目、可复用想法之间为什么有关，而不是只给一条链接
- 哪些页面缺来源、内容太薄、关系断开，适合放进后续修补
- 新人或项目接手时，应该先读哪些页面，再顺着哪些关系继续看

它不会替你画一个完整大图，也不会自动改正式页面。更适合把散在文件夹里的页面整理成可读、可补、可继续使用的知识线索。

## Paper Evidence Workbench

Paper Evidence Workbench 用论文笔记、结论笔记、证据表和关系说明来组织研究。目标不是“总结一个 PDF”，而是记清每篇论文实际支持了什么、证据在哪里、还有哪些地方不确定。
