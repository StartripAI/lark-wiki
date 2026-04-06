---
{
  "asset_key": "PAGE::project::agent_workspace::handoff-risks-report",
  "links_to": [
    "project::agent_workspace::index",
    "project::agent_workspace::execution-readiness-report"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::handoff-risks-report",
  "page_type": "Report",
  "portfolio_key": "portfolio::default",
  "source_ids": [
    "LOCAL::demo/agent_workspace_assets/agent_handoff_runbook.md",
    "LOCAL::demo/agent_workspace_assets/agent_ops_manifest.json",
    "LOCAL::demo/agent_workspace_assets/remote_mirror_registry.json",
    "LOCAL::demo/agent_workspace_assets/tool_inventory.csv",
    "LOCAL::demo/agent_workspace_assets/weekly_synthesis_brief.md"
  ],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "Handoff Risks Report"
}
---

# Handoff Risks Report

## Common failure modes

- remote docs drift from local canonical markdown
- base schemas change without refreshing snapshots
- project snapshots go stale and weaken synthesis quality
- LLM prompts over-expand if asset budgets are not capped
