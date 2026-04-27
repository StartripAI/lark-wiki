# lark-cli Recipes

These commands show the platform layer that `lark-wiki` builds on. Run them only after `lark-cli auth login`.

## Runtime

```bash
lark-cli --version
lark-cli doctor
lark-cli docs --help
lark-cli wiki --help
lark-cli base --help
```

## Docs And Wiki

```bash
lark-cli docs +search --help
lark-cli docs +fetch --help
lark-cli docs +create --help
lark-cli docs +update --help
lark-cli wiki spaces list --help
lark-cli wiki nodes list --help
```

`lark-wiki` wraps these into discovery, Markdown page building, and safe sync workflows.

## Base

```bash
lark-cli base +table-list --help
lark-cli base +field-list --help
lark-cli base +record-list --help
lark-cli base +record-upsert --help
```

`lark-wiki` uses Base as an optional ops control plane for sources, pages, runs, issues, and merge queues.
