# Optional Sidecars

The core `lark-wiki` workflow is local Markdown plus `lark-cli`. Sidecars are opt-in and should not replace canonical pages or human review.

## LLM Provider

Use an LLM provider for source-grounded synthesis and semantic linting.

```toml
[llm]
provider = "auto"
model = "gpt-5.4-mini"
timeout_seconds = 180
semantic_lint_enabled = true
```

## Graph Analysis

`graphifyy==0.5.0` can be used as an optional graph analysis sidecar. Treat outputs as structure hints and review inputs, not canonical truth.

## Research Evidence

`deepxiv-sdk==0.2.5` can be used as an optional research evidence sidecar. Treat outputs as evidence candidates and promote only after review.
