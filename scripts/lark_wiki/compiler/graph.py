from __future__ import annotations

from collections import Counter
import sqlite3

from ..config import AppConfig
from ..db import upsert_asset, upsert_page
from ..markdown import read_frontmatter, write_canonical_page
from ..portfolio import namespace_root_dir, namespace_root_relpath, namespaced_page_id, page_asset_key
from ..utils import json_dumps, relative_to_root, sha256_text


def build_graph(conn: sqlite3.Connection, config: AppConfig, namespace_key: str | None = None) -> dict[str, object]:
    namespace_key = namespace_key or config.default_project_namespace
    page_rows = conn.execute(
        "SELECT page_id, local_path FROM pages WHERE namespace_key = ? ORDER BY page_id",
        (namespace_key,),
    ).fetchall()
    graph: dict[str, list[dict[str, object]]] = {
        "nodes": [],
        "edges": [],
        "asset_nodes": [],
        "asset_edges": [],
        "page_asset_edges": [],
        "page_source_edges": [],
    }
    incoming: Counter[str] = Counter()
    page_map: dict[str, dict[str, object]] = {}

    for row in page_rows:
        path = config.root / row["local_path"]
        frontmatter, body = read_frontmatter(path)
        page_id = str(frontmatter.get("page_id", row["page_id"]))
        page_map[page_id] = {"frontmatter": frontmatter, "body": body, "path": path}
        graph["nodes"].append(
            {
                "page_id": page_id,
                "title": frontmatter.get("title", path.stem),
                "page_type": frontmatter.get("page_type", ""),
                "namespace_key": namespace_key,
            }
        )
        asset_key = str(frontmatter.get("asset_key", ""))
        if asset_key:
            graph["page_asset_edges"].append({"page_id": page_id, "asset_key": asset_key})
        for source_id in frontmatter.get("source_ids", []):
            graph["page_source_edges"].append({"page_id": page_id, "asset_key": source_id})
        for linked_page_id in frontmatter.get("links_to", []):
            graph["edges"].append({"from": page_id, "to": linked_page_id})
            incoming[linked_page_id] += 1

    index_title = "Portfolio 总索引" if namespace_key == config.account_namespace_key else f"{config.namespaces[namespace_key].display_name} 资产总索引"
    log_title = "Portfolio 运行日志" if namespace_key == config.account_namespace_key else f"{config.namespaces[namespace_key].display_name} 运行日志"
    index_lines = [f"# {index_title}", "", "## Canonical 页面", ""]
    for item in sorted(graph["nodes"], key=lambda node: (str(node["page_type"]), str(node["title"]))):
        frontmatter = page_map[str(item["page_id"])]["frontmatter"]
        rel_path = relative_to_root(page_map[str(item["page_id"])]["path"], config.root)
        incoming_count = incoming.get(str(item["page_id"]), 0)
        index_lines.append(
            f"- `{item['page_type']}` [{frontmatter.get('title', item['title'])}]({rel_path}) | inbound={incoming_count} | sources={len(frontmatter.get('source_ids', []))}"
        )

    latest_runs = conn.execute(
        "SELECT command_name, status, started_at FROM runs WHERE namespace_key = ? ORDER BY started_at DESC LIMIT 20",
        (namespace_key,),
    ).fetchall()
    log_lines = [f"# {log_title}", "", "## 最近运行", ""]
    if latest_runs:
        for row in latest_runs:
            log_lines.append(f"- `{row['started_at']}` | `{row['command_name']}` | `{row['status']}`")
    else:
        log_lines.append("- 还没有运行记录。")

    namespace_root = namespace_root_dir(config, namespace_key)
    rel_index_path = relative_to_root(namespace_root / "01_Index.md", config.wiki_src_dir)
    rel_log_path = relative_to_root(namespace_root / "02_Log.md", config.wiki_src_dir)
    index_page_id = namespaced_page_id(namespace_key, "index")
    log_page_id = namespaced_page_id(namespace_key, "log")
    home_page_id = namespaced_page_id(namespace_key, "home")
    index_text = write_canonical_page(
        config.wiki_src_dir,
        index_page_id,
        index_title,
        "Index",
        rel_index_path,
        page_asset_key(namespace_key, "index"),
        [],
        [str(node["page_id"]) for node in graph["nodes"] if str(node["page_id"]) != index_page_id],
        "\n".join(index_lines),
        namespace_key=namespace_key,
        portfolio_key=config.portfolio_key,
    )
    log_text = write_canonical_page(
        config.wiki_src_dir,
        log_page_id,
        log_title,
        "Log",
        rel_log_path,
        page_asset_key(namespace_key, "log"),
        [],
        [home_page_id, index_page_id],
        "\n".join(log_lines),
        namespace_key=namespace_key,
        portfolio_key=config.portfolio_key,
    )

    graph_path = config.build_dir / f"graph_{namespace_key.replace('::', '_')}.json"
    asset_rows = conn.execute(
        "SELECT asset_key, asset_class, title, canonical_role, namespace_key FROM assets WHERE namespace_key = ? ORDER BY asset_key",
        (namespace_key,),
    ).fetchall()
    edge_rows = conn.execute(
        """
        SELECT from_asset_key, to_asset_key, edge_type
        FROM asset_edges
        WHERE from_asset_key IN (SELECT asset_key FROM assets WHERE namespace_key = ?)
           OR to_asset_key IN (SELECT asset_key FROM assets WHERE namespace_key = ?)
        ORDER BY from_asset_key, to_asset_key
        """,
        (namespace_key, namespace_key),
    ).fetchall()
    graph["asset_nodes"] = [dict(row) for row in asset_rows]
    graph["asset_edges"] = [dict(row) for row in edge_rows]
    graph_path.write_text(json_dumps(graph), encoding="utf-8")

    upsert_asset(
        conn,
        asset_key=page_asset_key(namespace_key, "index"),
        asset_class="local_file",
        title=index_title,
        local_path=f"knowledge/wiki_src/{rel_index_path}",
        upstream_system="llm_wiki_compiler",
        source_hash=sha256_text(index_text),
        canonical_role="canonical_page",
        sync_mode="bidirectional_markdown_safe",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        metadata={"page_type": "Index", "page_id": index_page_id},
    )
    upsert_asset(
        conn,
        asset_key=page_asset_key(namespace_key, "log"),
        asset_class="local_file",
        title=log_title,
        local_path=f"knowledge/wiki_src/{rel_log_path}",
        upstream_system="llm_wiki_compiler",
        source_hash=sha256_text(log_text),
        canonical_role="canonical_page",
        sync_mode="bidirectional_markdown_safe",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        metadata={"page_type": "Log", "page_id": log_page_id},
    )
    upsert_asset(
        conn,
        asset_key=f"STATE::graph_manifest::{namespace_key}",
        asset_class="state_snapshot",
        title=f"graph manifest {namespace_key}",
        local_path=relative_to_root(graph_path, config.root),
        upstream_system="llm_wiki_compiler",
        source_hash=sha256_text(json_dumps(graph)),
        canonical_role="state_snapshot",
        sync_mode="local_only",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        metadata={"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])},
    )
    upsert_page(
        conn,
        page_id=index_page_id,
        page_type="Index",
        asset_key=page_asset_key(namespace_key, "index"),
        local_path=f"knowledge/wiki_src/{rel_index_path}",
        last_local_hash=sha256_text(index_text),
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        metadata={"title": index_title},
    )
    upsert_page(
        conn,
        page_id=log_page_id,
        page_type="Log",
        asset_key=page_asset_key(namespace_key, "log"),
        local_path=f"knowledge/wiki_src/{rel_log_path}",
        last_local_hash=sha256_text(log_text),
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        metadata={"title": log_title},
    )
    conn.commit()
    return {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "graph_path": relative_to_root(graph_path, config.root),
        "namespace_key": namespace_key,
    }
