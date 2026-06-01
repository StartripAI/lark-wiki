from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sqlite3

from .config import AppConfig
from .utils import read_text_safe

# HARD BOUNDARY: this module is 100% deterministic and NEVER calls an LLM
# provider / API / model subprocess. Per the project's locked design rule, the
# "LLM" is the host IDE agent (Claude Code / Codex) that is already operating the
# repo and follows AGENTS.md. These helpers only gather grounded source context,
# lift claims, and emit an explicit *agent task block* for that host agent to
# fill in. The tool performs no model inference of any kind.

AGENT_SYNTHESIS_MARKER = "AGENT SYNTHESIS TASK"


@dataclass(frozen=True)
class AssetContext:
    asset_key: str
    title: str
    asset_class: str
    namespace_key: str
    snippet: str


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _asset_text_from_row(config: AppConfig, row: sqlite3.Row) -> str:
    local_path = str(row["local_path"] or "")
    if local_path:
        full_path = config.root / local_path
        if full_path.exists():
            suffix = full_path.suffix.lower()
            if suffix in {".md", ".txt", ".csv", ".json", ".html"}:
                raw_text = read_text_safe(full_path)
                if suffix == ".json":
                    try:
                        payload = json.loads(raw_text)
                    except json.JSONDecodeError:
                        payload = {}
                    for key in ("markdown", "body", "text", "summary"):
                        value = payload.get(key)
                        if isinstance(value, str) and value.strip():
                            return value
                return raw_text
    metadata_json = row["metadata_json"] or ""
    if metadata_json:
        try:
            payload = json.loads(metadata_json)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            for key in ("markdown", "summary", "description", "title"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return str(row["title"] or "")


def collect_asset_context(
    conn: sqlite3.Connection,
    config: AppConfig,
    asset_keys: list[str],
) -> list[AssetContext]:
    contexts: list[AssetContext] = []
    seen: set[str] = set()
    for asset_key in asset_keys:
        if not asset_key or asset_key in seen:
            continue
        seen.add(asset_key)
        row = conn.execute(
            """
            SELECT asset_key, title, asset_class, namespace_key, local_path, metadata_json
            FROM assets
            WHERE asset_key = ?
            """,
            (asset_key,),
        ).fetchone()
        if not row:
            continue
        snippet = _truncate(_asset_text_from_row(config, row), config.agent_max_chars_per_asset)
        contexts.append(
            AssetContext(
                asset_key=row["asset_key"],
                title=row["title"] or row["asset_key"],
                asset_class=row["asset_class"] or "unknown",
                namespace_key=row["namespace_key"] or "",
                snippet=snippet,
            )
        )
        if len(contexts) >= config.agent_max_assets_per_prompt:
            break
    return contexts


def agent_synthesis_task(*, title: str, source_keys: list[str], page_keys: list[str] | None = None) -> str:
    """Return a deterministic task block instructing the host IDE agent to write
    the synthesis. No model is called here — the agent (Claude Code / Codex)
    fills this in while operating the repo, per AGENTS.md."""
    refs = ", ".join(f"`{key}`" for key in source_keys) or "（无来源）"
    lines = [
        f"> 🧠 **{AGENT_SYNTHESIS_MARKER}** — 由当前操作仓库的 IDE agent（Claude Code / Codex）按 `AGENTS.md` 完成；本工具不调用任何 LLM provider/API。",
        "> 阅读下列来源，写出 grounded 综合（结论 / 证据 / 矛盾 / 待解问题），非显然结论用 `(source: KEY)` 标注。",
        f"> 主题：{title}",
        f"> 来源：{refs}",
    ]
    page_keys = page_keys or []
    if page_keys:
        lines.append("> 相关页：" + ", ".join(f"`{key}`" for key in page_keys))
    return "\n".join(lines)


_CLAIM_PATTERN = re.compile(r"Claim:\s*(.+?)\s*=>\s*(.+)")


def detect_claim_contradictions(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deterministically flag conflicting ``Claim: <key> => <value>`` lines across pages.

    LLM-free so this contradiction check can run on every lint, even with no provider —
    this is the "noting where new data contradicts old claims" property of the wiki.
    """
    claim_map: dict[str, set[tuple[str, str]]] = {}
    for page in pages or []:
        page_id = str(page.get("page_id", ""))
        body = str(page.get("body", ""))
        for match in _CLAIM_PATTERN.finditer(body):
            lhs = match.group(1).strip()
            rhs = match.group(2).strip()
            claim_map.setdefault(lhs, set()).add((rhs, page_id))
    contradictions: list[dict[str, str]] = []
    for lhs, rhs_pairs in claim_map.items():
        values = {rhs for rhs, _ in rhs_pairs}
        if len(values) > 1:
            contradictions.append(
                {
                    "claim": lhs,
                    "page_ids": ", ".join(sorted({page_id for _, page_id in rhs_pairs})),
                    "values": "; ".join(sorted(values)),
                    "detail": "Conflicting claim values across pages",
                }
            )
    return sorted(contradictions, key=lambda item: item["claim"])


def compile_page_markdown(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    title: str,
    page_type: str,
    base_body: str,
    source_ids: list[str],
) -> str:
    """Emit an agent synthesis task for a page (no model call). Empty when there
    are no grounded sources to synthesize."""
    contexts = collect_asset_context(conn, config, source_ids)
    if not contexts:
        return ""
    return agent_synthesis_task(title=title, source_keys=[context.asset_key for context in contexts])


def compile_query_markdown(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    keyword: str,
    asset_keys: list[str],
    graph_context: dict[str, object] | None = None,
) -> str:
    """Emit an agent synthesis task for a query report (no model call)."""
    contexts = collect_asset_context(conn, config, asset_keys)
    page_contexts: list[dict[str, object]] = []
    if graph_context:
        raw_page_contexts = graph_context.get("related_page_contexts", [])
        if isinstance(raw_page_contexts, list):
            page_contexts = [item for item in raw_page_contexts if isinstance(item, dict)]
    if not contexts and not page_contexts:
        return ""
    page_keys = [str(item.get("page_id", "")) for item in page_contexts if item.get("page_id")]
    return agent_synthesis_task(
        title=f"Query: {keyword}",
        source_keys=[context.asset_key for context in contexts],
        page_keys=page_keys,
    )
