# Optional Analysis Capabilities

The core `lark-wiki` workflow is local Markdown plus `lark-cli`. The strongest analysis layer is simple: one part helps you understand papers, the other connects related knowledge.

## LLM Provider

Use an LLM provider to summarize supplied sources and flag possible conflicts.

```toml
[llm]
provider = "auto"
model = "gpt-5.4-mini"
timeout_seconds = 180
semantic_lint_enabled = true
```

## Knowledge Relation Map

Use generated links between pages, sources, projects, and reusable ideas to turn scattered documents into a navigable knowledge map.

## Paper Evidence Workspace

Use paper notes, claim notes, evidence tables, and related-work maps to organize research. The goal is not “summarize a PDF”; the goal is to remember what each paper actually supports and what is still uncertain.
