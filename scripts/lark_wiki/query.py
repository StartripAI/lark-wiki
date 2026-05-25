from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import AppConfig
from .db import upsert_asset, upsert_page
from .graphify import load_graphify_enrichment
from .llm_compile import compile_query_markdown
from .markdown import read_frontmatter, write_canonical_page
from .portfolio import namespace_root_dir, namespaced_page_id, page_asset_key
from .utils import read_text_safe, relative_to_root, sha256_text, slugify


def _asset_rows(conn: sqlite3.Connection, namespace_key: str) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT asset_key, title, local_path, remote_url, asset_class, metadata_json
            FROM assets
            WHERE namespace_key = ?
            ORDER BY title
            """,
            (namespace_key,),
        )
    ]


def _asset_matches(config: AppConfig, row: dict[str, object], keyword: str) -> bool:
    haystacks = [row.get("title"), row.get("local_path"), row.get("remote_url"), row.get("metadata_json")]
    local_path = str(row.get("local_path") or "")
    if local_path:
        full_path = config.root / local_path
        if full_path.exists() and full_path.suffix.lower() in {".md", ".json", ".txt", ".csv"}:
            haystacks.append(read_text_safe(full_path))
    return any(keyword.lower() in str(text or "").lower() for text in haystacks)


def _is_generated_query_asset_row(row: dict[str, object]) -> bool:
    asset_key = str(row.get("asset_key") or "")
    local_path = str(row.get("local_path") or "").replace("\\", "/")
    return "::query-" in asset_key or "/reports/query-" in local_path or Path(local_path).name.startswith("query-")


def _safe_page_frontmatter(path: Path) -> tuple[dict[str, object], str]:
    try:
        return read_frontmatter(path)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}, read_text_safe(path)


def _page_rows(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> list[dict[str, object]]:
    by_page_id: dict[str, dict[str, object]] = {}
    for row in conn.execute(
        """
        SELECT page_id, page_type, asset_key, local_path, metadata_json
        FROM pages
        WHERE namespace_key = ?
        ORDER BY page_id
        """,
        (namespace_key,),
    ):
        local_path = str(row["local_path"] or "")
        title = ""
        body = ""
        if local_path:
            full_path = config.root / local_path
            if full_path.exists():
                frontmatter, body = _safe_page_frontmatter(full_path)
                title = str(frontmatter.get("title") or "")
        by_page_id[str(row["page_id"])] = {
            "page_id": str(row["page_id"] or ""),
            "title": title or str(row["page_id"] or ""),
            "page_type": str(row["page_type"] or "Page"),
            "asset_key": str(row["asset_key"] or ""),
            "local_path": local_path,
            "body": body,
            "registered": True,
        }

    root = namespace_root_dir(config, namespace_key)
    if root.exists():
        for path in sorted(root.rglob("*.md")):
            frontmatter, body = _safe_page_frontmatter(path)
            page_id = str(
                frontmatter.get("page_id")
                or relative_to_root(path, config.wiki_src_dir).removesuffix(".md").replace("/", "::")
            )
            by_page_id[page_id] = {
                **by_page_id.get(page_id, {}),
                "page_id": page_id,
                "title": str(frontmatter.get("title") or path.stem.replace("_", " ").replace("-", " ").title()),
                "page_type": str(frontmatter.get("page_type") or by_page_id.get(page_id, {}).get("page_type") or "Page"),
                "asset_key": str(frontmatter.get("asset_key") or by_page_id.get(page_id, {}).get("asset_key") or ""),
                "local_path": relative_to_root(path, config.root),
                "body": body,
                "registered": bool(by_page_id.get(page_id, {}).get("registered", False)),
            }
    return sorted(by_page_id.values(), key=lambda row: (str(row["title"]).lower(), str(row["page_id"])))


def _page_matches(row: dict[str, object], keyword: str) -> bool:
    needle = keyword.lower()
    return any(
        needle in str(value or "").lower()
        for value in (row.get("title"), row.get("local_path"), row.get("page_type"), row.get("body"))
    )


def _is_generated_query_row(row: dict[str, object]) -> bool:
    page_id = str(row.get("page_id") or "")
    local_path = str(row.get("local_path") or "").replace("\\", "/")
    return _is_generated_query_page(page_id) or "/reports/query-" in local_path or Path(local_path).name.startswith("query-")


def _page_asset_maps(conn: sqlite3.Connection, namespace_key: str) -> tuple[dict[str, str], dict[str, str]]:
    page_to_asset: dict[str, str] = {}
    asset_to_page: dict[str, str] = {}
    for row in conn.execute(
        """
        SELECT page_id, asset_key
        FROM pages
        WHERE namespace_key = ?
        ORDER BY page_id
        """,
        (namespace_key,),
    ):
        page_id = str(row["page_id"] or "")
        asset_key = str(row["asset_key"] or "")
        if page_id and asset_key:
            page_to_asset[page_id] = asset_key
            asset_to_page[asset_key] = page_id
    return page_to_asset, asset_to_page


def _is_generated_query_page(page_id: str) -> bool:
    return "::query-" in page_id or page_id.endswith("::query")


def _graphify_related(
    conn: sqlite3.Connection,
    config: AppConfig,
    namespace_key: str,
    direct_asset_keys: list[str],
    direct_page_ids: list[str],
    excluded_page_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    excluded_page_ids = excluded_page_ids or set()
    page_to_asset, asset_to_page = _page_asset_maps(conn, namespace_key)
    seed_pages = {asset_to_page[key] for key in direct_asset_keys if key in asset_to_page}
    seed_pages.update(page_id for page_id in direct_page_ids if page_id)
    seed_pages.difference_update(excluded_page_ids)
    if not seed_pages:
        return []
    page_by_id = {str(row["page_id"]): row for row in _page_rows(conn, config, namespace_key)}
    enrichment = load_graphify_enrichment(conn, config, namespace_key=namespace_key)
    edges = enrichment.get("edges", []) if isinstance(enrichment, dict) else []
    best: dict[str, dict[str, object]] = {}
    for raw_edge in edges:
        if not isinstance(raw_edge, dict):
            continue
        from_page = str(raw_edge.get("from", ""))
        to_page = str(raw_edge.get("to", ""))
        if from_page in seed_pages and to_page not in seed_pages:
            neighbor = to_page
        elif to_page in seed_pages and from_page not in seed_pages:
            neighbor = from_page
        else:
            continue
        if _is_generated_query_page(neighbor):
            continue
        if neighbor in excluded_page_ids:
            continue
        asset_key = page_to_asset.get(neighbor, "")
        if asset_key and asset_key in direct_asset_keys:
            continue
        if not asset_key and neighbor in direct_page_ids:
            continue
        try:
            score = float(raw_edge.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        result_key = asset_key or f"PAGE::{neighbor}"
        current = best.get(result_key)
        if current and float(current["score"]) >= score:
            continue
        graphify = raw_edge.get("graphify", {}) if isinstance(raw_edge.get("graphify", {}), dict) else {}
        page = page_by_id.get(neighbor, {})
        best[result_key] = {
            "asset_key": asset_key,
            "page_id": neighbor,
            "title": str(page.get("title") or neighbor),
            "local_path": str(page.get("local_path") or ""),
            "score": score,
            "reasons": [str(reason) for reason in raw_edge.get("reasons", []) if str(reason)],
            "source_layer": str(raw_edge.get("source_layer") or "graphify"),
            "relation": str(graphify.get("relation") or ""),
            "confidence": str(graphify.get("confidence") or ""),
            "source_file": str(graphify.get("source_file") or ""),
        }
    return sorted(best.values(), key=lambda item: (-float(item["score"]), str(item["asset_key"]), str(item["page_id"])))[:10]


def _rows_by_asset(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["asset_key"]): row for row in rows}


def _related_page_contexts(config: AppConfig, related: list[dict[str, object]]) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    for item in related:
        local_path = str(item.get("local_path") or "")
        if not local_path:
            continue
        full_path = config.root / local_path
        if not full_path.exists():
            continue
        try:
            _frontmatter, body = read_frontmatter(full_path)
            snippet = body.strip()
        except (json.JSONDecodeError, ValueError, OSError):
            snippet = read_text_safe(full_path).strip()
        if len(snippet) > config.llm_max_chars_per_asset:
            snippet = snippet[: config.llm_max_chars_per_asset - 1].rstrip() + "…"
        contexts.append(
            {
                "page_id": str(item.get("page_id") or ""),
                "title": str(item.get("title") or item.get("page_id") or ""),
                "local_path": local_path,
                "relation": str(item.get("relation") or ""),
                "confidence": str(item.get("confidence") or ""),
                "source_layer": str(item.get("source_layer") or ""),
                "snippet": snippet,
            }
        )
        if len(contexts) >= config.llm_max_assets_per_prompt:
            break
    return contexts


def _page_contexts_from_rows(config: AppConfig, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    for row in rows:
        local_path = str(row.get("local_path") or "")
        snippet = str(row.get("body") or "").strip()
        if local_path and not snippet:
            full_path = config.root / local_path
            if full_path.exists():
                try:
                    _frontmatter, body = read_frontmatter(full_path)
                    snippet = body.strip()
                except (json.JSONDecodeError, ValueError, OSError):
                    snippet = read_text_safe(full_path).strip()
        if len(snippet) > config.llm_max_chars_per_asset:
            snippet = snippet[: config.llm_max_chars_per_asset - 1].rstrip() + "…"
        contexts.append(
            {
                "page_id": str(row.get("page_id") or ""),
                "title": str(row.get("title") or row.get("page_id") or ""),
                "local_path": local_path,
                "relation": "direct_keyword_match",
                "confidence": "DIRECT",
                "source_layer": "canonical",
                "snippet": snippet,
            }
        )
        if len(contexts) >= config.llm_max_assets_per_prompt:
            break
    return contexts


def query(conn: sqlite3.Connection, config: AppConfig, keyword: str, namespace_key: str | None = None) -> dict[str, object]:
    keyword = keyword.strip()
    if not keyword:
        raise RuntimeError("query command requires --query")
    namespace_key = namespace_key or config.default_project_namespace
    short_id = f"query-{slugify(keyword)}"
    report_id = namespaced_page_id(namespace_key, short_id)
    report_asset_key = page_asset_key(namespace_key, short_id)
    all_rows = _asset_rows(conn, namespace_key)
    page_rows = _page_rows(conn, config, namespace_key)
    matches = [
        row
        for row in all_rows
        if str(row.get("asset_key") or "") != report_asset_key and not _is_generated_query_asset_row(row) and _asset_matches(config, row, keyword)
    ]
    page_matches = [
        row
        for row in page_rows
        if str(row.get("page_id") or "") != report_id and not _is_generated_query_row(row) and _page_matches(row, keyword)
    ]
    direct_asset_keys = [str(row["asset_key"]) for row in matches]
    direct_page_ids = [str(row["page_id"]) for row in page_matches]
    related = _graphify_related(
        conn,
        config,
        namespace_key,
        direct_asset_keys,
        direct_page_ids,
        excluded_page_ids={report_id},
    )
    rows_by_asset = _rows_by_asset(all_rows)
    rel_path = Path(relative_to_root(namespace_root_dir(config, namespace_key) / "reports" / f"{short_id}.md", config.wiki_src_dir))
    lines = [
        f"# Query Report: {keyword}",
        "",
        f"- 结果数：**{len(matches)}**",
        f"- 命中资产：**{len(matches)}**",
        f"- 命中页面：**{len(page_matches)}**",
        "",
        "## 命中资产",
        "",
    ]
    for row in matches[:50]:
        lines.append(f"- `{row['asset_class']}` `{row['asset_key']}` | {row['title']} | {row['local_path'] or row['remote_url']}")
    if page_matches:
        lines.extend(["", "## 命中页面", ""])
        for row in page_matches[:50]:
            lines.append(f"- `{row['page_type']}` `{row['page_id']}` | {row['title']} | {row['local_path']}")
    if related:
        lines.extend(["", "## Graphify 相关页面", ""])
        for item in related:
            row = rows_by_asset.get(str(item["asset_key"]), {})
            reason_text = ", ".join(str(reason) for reason in item.get("reasons", [])) or "graphify"
            relation = f" | relation={item['relation']}" if item.get("relation") else ""
            confidence = f" | confidence={item['confidence']}" if item.get("confidence") else ""
            source_file = f" | source={item['source_file']}" if item.get("source_file") else ""
            source_layer = f" | layer={item['source_layer']}" if item.get("source_layer") else ""
            title = row.get("title") or item.get("title") or item["page_id"]
            location = row.get("local_path") or row.get("remote_url") or item.get("local_path") or ""
            lines.append(
                f"- `{item['page_id']}` `{item['asset_key'] or 'page'}` | {title} | {location} | score={item['score']} | {reason_text}{source_layer}{relation}{confidence}{source_file}"
            )
    direct_page_contexts = _page_contexts_from_rows(config, page_matches[:20])
    related_page_contexts = _related_page_contexts(config, related)
    if matches or direct_page_contexts or related_page_contexts:
        lines.extend(["", "## Synthesis Context", ""])
        if matches:
            lines.extend(["", "### Direct Asset Context", ""])
            for row in matches[:20]:
                lines.append(f"- `{row['asset_key']}` | {row['title']} | {row['local_path'] or row['remote_url']}")
        if direct_page_contexts:
            lines.extend(["", "### Direct Page Context", ""])
            for item in direct_page_contexts:
                lines.append(f"- `{item['page_id']}` | {item['title']} | {item['local_path']} | layer={item['source_layer']}")
        if related_page_contexts:
            lines.extend(["", "### Graphify Expanded Page Context", ""])
            for item in related_page_contexts:
                relation = f" | relation={item['relation']}" if item.get("relation") else ""
                confidence = f" | confidence={item['confidence']}" if item.get("confidence") else ""
                layer = f" | layer={item['source_layer']}" if item.get("source_layer") else ""
                lines.append(f"- `{item['page_id']}` | {item['title']} | {item['local_path']}{layer}{relation}{confidence}")
    source_ids = [str(row["asset_key"]) for row in matches[:20]]
    for item in related:
        asset_key = str(item["asset_key"])
        if not asset_key:
            continue
        if asset_key not in source_ids:
            source_ids.append(asset_key)
        if len(source_ids) >= 20:
            break
    graph_context = {
        "graphify_related": related,
        "direct_asset_keys": direct_asset_keys[:20],
        "direct_page_ids": direct_page_ids[:20],
        "related_page_contexts": direct_page_contexts + related_page_contexts,
    }
    synthesis = compile_query_markdown(
        conn,
        config,
        namespace_key=namespace_key,
        keyword=keyword,
        asset_keys=source_ids,
        graph_context=graph_context,
    ).strip()
    if synthesis:
        lines.extend(["", "## LLM Synthesis", "", synthesis])
    text = write_canonical_page(
        config.wiki_src_dir,
        report_id,
        f"Query Report: {keyword}",
        "Report",
        rel_path,
        page_asset_key(namespace_key, short_id),
        source_ids,
        [namespaced_page_id(namespace_key, "index"), namespaced_page_id(namespace_key, "log")],
        "\n".join(lines),
        namespace_key=namespace_key,
        portfolio_key=config.portfolio_key,
    )
    full_path = config.wiki_src_dir / rel_path
    upsert_asset(
        conn,
        asset_key=page_asset_key(namespace_key, short_id),
        asset_class="local_file",
        title=f"Query Report: {keyword}",
        local_path=relative_to_root(full_path, config.root),
        upstream_system="llm_wiki_query",
        source_hash=sha256_text(text),
        canonical_role="canonical_page",
        sync_mode="bidirectional_markdown_safe",
        namespace_key=namespace_key,
        classification_status="classified",
        portfolio_key=config.portfolio_key,
        metadata={"query": keyword},
    )
    upsert_page(
        conn,
        page_id=report_id,
        page_type="Report",
        asset_key=page_asset_key(namespace_key, short_id),
        local_path=relative_to_root(full_path, config.root),
        last_local_hash=sha256_text(text),
        sync_mode="bidirectional_markdown_safe",
        namespace_key=namespace_key,
        portfolio_key=config.portfolio_key,
        metadata={"query": keyword},
    )
    conn.commit()
    return {
        "report_page": relative_to_root(full_path, config.root),
        "match_count": len(matches),
        "page_match_count": len(page_matches),
        "graphify_related_count": len(related),
    }
