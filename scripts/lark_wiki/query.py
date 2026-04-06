from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import AppConfig
from .db import upsert_asset, upsert_page
from .llm_compile import compile_query_markdown
from .markdown import write_canonical_page
from .portfolio import namespace_root_dir, namespaced_page_id, page_asset_key
from .utils import read_text_safe, relative_to_root, sha256_text, slugify


def query(conn: sqlite3.Connection, config: AppConfig, keyword: str, namespace_key: str | None = None) -> dict[str, object]:
    keyword = keyword.strip()
    if not keyword:
        raise RuntimeError("query command requires --query")
    namespace_key = namespace_key or config.default_project_namespace
    matches: list[dict[str, object]] = []
    for row in conn.execute(
        """
        SELECT asset_key, title, local_path, remote_url, asset_class, metadata_json
        FROM assets
        WHERE namespace_key = ?
        ORDER BY title
        """,
        (namespace_key,),
    ):
        haystacks = [row["title"], row["local_path"], row["remote_url"], row["metadata_json"]]
        if row["local_path"]:
            local_path = config.root / row["local_path"]
            if local_path.exists() and local_path.suffix.lower() in {".md", ".json", ".txt", ".csv"}:
                haystacks.append(read_text_safe(local_path))
        if any(keyword.lower() in (text or "").lower() for text in haystacks):
            matches.append(dict(row))
    short_id = f"query-{slugify(keyword)}"
    report_id = namespaced_page_id(namespace_key, short_id)
    rel_path = Path(relative_to_root(namespace_root_dir(config, namespace_key) / "reports" / f"{short_id}.md", config.wiki_src_dir))
    lines = [f"# Query Report: {keyword}", "", f"- 结果数：**{len(matches)}**", "", "## 命中资产", ""]
    for row in matches[:50]:
        lines.append(f"- `{row['asset_class']}` `{row['asset_key']}` | {row['title']} | {row['local_path'] or row['remote_url']}")
    source_ids = [row["asset_key"] for row in matches[:20]]
    synthesis = compile_query_markdown(
        conn,
        config,
        namespace_key=namespace_key,
        keyword=keyword,
        asset_keys=source_ids,
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
    return {"report_page": relative_to_root(full_path, config.root), "match_count": len(matches)}
