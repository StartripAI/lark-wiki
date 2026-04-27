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

A user-provided graph analysis sidecar can be used to produce structure hints and review inputs. Treat outputs as evidence to inspect, not canonical truth.

## Research Evidence

A user-provided research evidence sidecar can be used to collect external research inputs. Promote outputs only after review.
