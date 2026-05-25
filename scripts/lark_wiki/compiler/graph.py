from __future__ import annotations

from collections import Counter
from importlib import import_module
import json
import sqlite3

from ..config import AppConfig
from ..db import upsert_asset, upsert_page
from ..markdown import read_frontmatter, write_canonical_page
from ..portfolio import namespace_root_dir, namespace_root_relpath, namespaced_page_id, page_asset_key
from ..utils import json_dumps, relative_to_root, sha256_text


SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
NODE_FIELDS = {
    "page_id",
    "title",
    "page_type",
    "namespace_key",
    "local_path",
    "body_size",
    "source_count",
    "inbound_count",
    "outbound_count",
    "generated_report",
}


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _is_generated_query_page(page_id: str, local_path: str = "") -> bool:
    normalised = local_path.replace("\\", "/")
    return "::query-" in page_id or "/reports/query-" in normalised or normalised.split("/")[-1].startswith("query-")


def _select_namespace_enrichment(enrichment: dict[str, object], namespace_key: str) -> dict[str, object]:
    if any(key in enrichment for key in ("nodes", "edges", "issues")):
        return enrichment

    namespaces = enrichment.get("namespaces")
    if not isinstance(namespaces, list):
        return {}
    for raw_namespace in namespaces:
        if not isinstance(raw_namespace, dict):
            continue
        if str(raw_namespace.get("namespace_key", "")) == namespace_key:
            return raw_namespace
    return {}


def _load_inventory_enrichment(
    conn: sqlite3.Connection, config: AppConfig, namespace_key: str
) -> dict[str, object]:
    try:
        inventory = import_module("scripts.lark_wiki.inventory")
    except ModuleNotFoundError:
        return {}

    for helper_name in ("build_relation_inventory", "build_inventory", "analyze_inventory", "inventory"):
        helper = getattr(inventory, helper_name, None)
        if helper is None:
            continue
        try:
            result = helper(conn, config, namespace_key=namespace_key)
        except Exception:
            return {}
        if isinstance(result, dict):
            return _select_namespace_enrichment(result, namespace_key)
    return {}


def _load_graphify_enrichment(
    conn: sqlite3.Connection, config: AppConfig, namespace_key: str
) -> dict[str, object]:
    try:
        graphify = import_module("scripts.lark_wiki.graphify")
    except ModuleNotFoundError:
        return {}
    helper = getattr(graphify, "load_graphify_enrichment", None)
    if helper is None:
        return {}
    try:
        result = helper(conn, config, namespace_key=namespace_key)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}


def _normalise_reasons(value: object, fallback: str) -> list[str]:
    reasons = _as_string_list(value)
    return reasons or [fallback]


def _normalise_score(value: object, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _edge_key(edge: dict[str, object]) -> tuple[str, str]:
    return str(edge.get("from", "")), str(edge.get("to", ""))


def _merge_graphify_provenance(edge: dict[str, object], graphify: dict[str, object]) -> None:
    existing = edge.get("graphify_edges")
    provenances = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    if graphify not in provenances:
        provenances.append(graphify)
    edge["graphify_edges"] = provenances
    edge["graphify"] = max(provenances, key=lambda item: _normalise_score(item.get("confidence_score"), 0.0))


def _has_graphify_reason(reasons: object) -> bool:
    return any(str(reason).startswith("graphify:") for reason in _as_string_list(reasons))


def _merge_source_layer(edge: dict[str, object], incoming_layer: object, *, incoming_graphify: bool) -> None:
    current = str(edge.get("source_layer") or "")
    incoming = str(incoming_layer or "")
    if incoming_graphify:
        if current == "canonical" or incoming == "mixed":
            edge["source_layer"] = "mixed"
        elif current == "mixed":
            edge["source_layer"] = "mixed"
        else:
            edge["source_layer"] = "graphify"
        return
    if incoming == "mixed" or current == "mixed":
        edge["source_layer"] = "mixed"
    elif incoming == "canonical" and current == "graphify":
        edge["source_layer"] = "mixed"
    elif current in {"canonical", "graphify"}:
        edge["source_layer"] = current
    elif incoming in {"canonical", "graphify"}:
        edge["source_layer"] = incoming
    else:
        edge["source_layer"] = "canonical"


def _load_open_issues(conn: sqlite3.Connection, namespace_key: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT issue_id, issue_type, severity, asset_key, page_id, detail_json, status
        FROM issues
        WHERE namespace_key = ? AND status = 'open'
        ORDER BY severity, issue_type, page_id, asset_key, issue_id
        """,
        (namespace_key,),
    ).fetchall()
    issues: list[dict[str, object]] = []
    for row in rows:
        try:
            detail: object = json.loads(row["detail_json"] or "{}")
        except json.JSONDecodeError:
            detail = {}
        issues.append(
            {
                "issue_id": row["issue_id"],
                "issue_type": row["issue_type"],
                "severity": row["severity"],
                "asset_key": row["asset_key"],
                "page_id": row["page_id"],
                "detail": detail,
                "status": row["status"],
            }
        )
    return issues


def _register_disk_pages(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> None:
    root = namespace_root_dir(config, namespace_key)
    if not root.exists():
        return
    for path in sorted(root.rglob("*.md")):
        frontmatter, body = read_frontmatter(path)
        page_id = str(frontmatter.get("page_id") or "")
        if not page_id:
            continue
        page_namespace = str(frontmatter.get("namespace_key") or namespace_key)
        if page_namespace != namespace_key:
            continue
        title = str(frontmatter.get("title") or path.stem.replace("_", " ").replace("-", " ").title())
        page_type = str(frontmatter.get("page_type") or "Page")
        asset_key = str(frontmatter.get("asset_key") or page_asset_key(namespace_key, page_id.rsplit("::", 1)[-1]))
        local_path = relative_to_root(path, config.root)
        text = path.read_text(encoding="utf-8")
        source_hash = sha256_text(text)
        generated_report = _is_generated_query_page(page_id, local_path)
        upsert_asset(
            conn,
            asset_key=asset_key,
            asset_class="local_file",
            title=title,
            local_path=local_path,
            upstream_system="llm_wiki_disk_scan",
            source_hash=source_hash,
            canonical_role="generated_report" if generated_report else "canonical_page",
            sync_mode="local_only" if generated_report else "bidirectional_markdown_safe",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified",
            metadata={"page_type": page_type, "page_id": page_id, "generated_report": generated_report},
        )
        upsert_page(
            conn,
            page_id=page_id,
            page_type=page_type,
            asset_key=asset_key,
            local_path=local_path,
            last_local_hash=source_hash,
            sync_mode="local_only" if generated_report else "bidirectional_markdown_safe",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            metadata={"title": title, "generated_report": generated_report},
        )


def _sorted_issues(issues: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        issues,
        key=lambda issue: (
            SEVERITY_RANK.get(str(issue.get("severity", "")), 99),
            str(issue.get("issue_type", "")),
            str(issue.get("page_id", "")),
            str(issue.get("asset_key", "")),
            str(issue.get("issue_id", "")),
            json.dumps(issue, ensure_ascii=False, sort_keys=True),
        ),
    )


def _merge_inventory_enrichment(
    graph: dict[str, list[dict[str, object]]],
    enrichment: dict[str, object],
) -> None:
    enriched_nodes = enrichment.get("nodes")
    if isinstance(enriched_nodes, list):
        node_map = {str(node["page_id"]): node for node in graph["nodes"] if "page_id" in node}
        for raw_node in enriched_nodes:
            if not isinstance(raw_node, dict):
                continue
            page_id = str(raw_node.get("page_id", ""))
            if not page_id:
                continue
            if page_id not in node_map:
                node_map[page_id] = {"page_id": page_id}
                graph["nodes"].append(node_map[page_id])
            for key in NODE_FIELDS:
                if key in raw_node:
                    node_map[page_id][key] = raw_node[key]

    enriched_edges = enrichment.get("edges")
    if isinstance(enriched_edges, list):
        node_ids = {str(node.get("page_id", "")) for node in graph["nodes"]}
        edge_map = {_edge_key(edge): edge for edge in graph["edges"]}
        for raw_edge in enriched_edges:
            if not isinstance(raw_edge, dict):
                continue
            from_page = str(raw_edge.get("from", ""))
            to_page = str(raw_edge.get("to", ""))
            if not from_page or not to_page:
                continue
            if from_page not in node_ids or to_page not in node_ids:
                continue
            edge = edge_map.get((from_page, to_page))
            created = edge is None
            if edge is None:
                edge = {
                    "from": from_page,
                    "to": to_page,
                    "source_layer": str(raw_edge.get("source_layer") or "canonical"),
                }
                graph["edges"].append(edge)
                edge_map[(from_page, to_page)] = edge
            existing_score = _normalise_score(edge.get("score"))
            incoming_score = _normalise_score(raw_edge.get("score"), existing_score)
            edge["score"] = max(existing_score, incoming_score)
            if created:
                existing_reasons: set[str] = set()
            else:
                existing_reasons = set(_normalise_reasons(edge.get("reasons"), "frontmatter.links_to"))
            incoming_reasons = set(_normalise_reasons(raw_edge.get("reasons"), "inventory"))
            edge["reasons"] = sorted(existing_reasons.union(incoming_reasons))
            graphify = raw_edge.get("graphify")
            incoming_graphify = isinstance(graphify, dict) or _has_graphify_reason(raw_edge.get("reasons", []))
            if isinstance(graphify, dict):
                _merge_graphify_provenance(edge, graphify)
            _merge_source_layer(edge, raw_edge.get("source_layer"), incoming_graphify=incoming_graphify)

    enriched_issues = enrichment.get("issues")
    if isinstance(enriched_issues, list):
        inventory_issues = [
            dict(issue)
            for issue in enriched_issues
            if isinstance(issue, dict) and issue.get("issue_type") != "missing_graph_manifest"
        ]
        graph["issues"] = _sorted_issues([*graph["issues"], *inventory_issues])


def build_graph(conn: sqlite3.Connection, config: AppConfig, namespace_key: str | None = None) -> dict[str, object]:
    namespace_key = namespace_key or config.default_project_namespace
    _register_disk_pages(conn, config, namespace_key)
    page_rows = conn.execute(
        "SELECT page_id, page_type, local_path FROM pages WHERE namespace_key = ? ORDER BY page_id",
        (namespace_key,),
    ).fetchall()
    graph: dict[str, list[dict[str, object]]] = {
        "nodes": [],
        "edges": [],
        "issues": [],
        "asset_nodes": [],
        "asset_edges": [],
        "page_asset_edges": [],
        "page_source_edges": [],
    }
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    page_map: dict[str, dict[str, object]] = {}
    generated_page_ids = {
        str(row["page_id"] or "")
        for row in page_rows
        if _is_generated_query_page(str(row["page_id"] or ""), str(row["local_path"] or ""))
    }

    for row in page_rows:
        path = config.root / row["local_path"]
        frontmatter, body = read_frontmatter(path)
        page_id = str(frontmatter.get("page_id", row["page_id"]))
        generated_report = _is_generated_query_page(page_id, str(row["local_path"] or ""))
        if generated_report:
            generated_page_ids.add(page_id)
        raw_source_ids = _as_string_list(frontmatter.get("source_ids", []))
        raw_links_to = _as_string_list(frontmatter.get("links_to", []))
        source_ids = [] if generated_report else raw_source_ids
        links_to = [] if generated_report else [linked for linked in raw_links_to if linked not in generated_page_ids]
        page_map[page_id] = {
            "frontmatter": frontmatter,
            "body": body,
            "path": path,
            "source_ids": source_ids,
            "links_to": links_to,
        }
        graph["nodes"].append(
            {
                "page_id": page_id,
                "title": frontmatter.get("title", path.stem),
                "page_type": frontmatter.get("page_type", row["page_type"]),
                "namespace_key": namespace_key,
                "local_path": row["local_path"],
                "body_size": len(body),
                "source_count": len(source_ids),
                "inbound_count": 0,
                "outbound_count": len(links_to),
                "generated_report": generated_report,
            }
        )
        asset_key = str(frontmatter.get("asset_key", ""))
        if asset_key and not generated_report:
            graph["page_asset_edges"].append({"page_id": page_id, "asset_key": asset_key})
        for source_id in source_ids:
            graph["page_source_edges"].append({"page_id": page_id, "asset_key": source_id})
        for linked_page_id in links_to:
            graph["edges"].append(
                {
                    "from": page_id,
                    "to": linked_page_id,
                    "score": 1.0,
                    "reasons": ["frontmatter.links_to"],
                    "source_layer": "canonical",
                }
            )
            incoming[linked_page_id] += 1
            outgoing[page_id] += 1

    for node in graph["nodes"]:
        page_id = str(node["page_id"])
        node["inbound_count"] = incoming.get(page_id, 0)
        node["outbound_count"] = outgoing.get(page_id, 0)

    graph["issues"] = _load_open_issues(conn, namespace_key)
    _merge_inventory_enrichment(graph, _load_inventory_enrichment(conn, config, namespace_key))
    _merge_inventory_enrichment(graph, _load_graphify_enrichment(conn, config, namespace_key))
    node_ids = {str(node.get("page_id", "")) for node in graph["nodes"]}
    generated_page_ids = {str(node.get("page_id", "")) for node in graph["nodes"] if node.get("generated_report")}
    graph["edges"] = [
        edge
        for edge in graph["edges"]
        if str(edge.get("from", "")) in node_ids and str(edge.get("to", "")) in node_ids
        and str(edge.get("from", "")) not in generated_page_ids
        and str(edge.get("to", "")) not in generated_page_ids
    ]
    final_incoming: Counter[str] = Counter()
    final_outgoing: Counter[str] = Counter()
    for edge in graph["edges"]:
        final_outgoing[str(edge.get("from", ""))] += 1
        final_incoming[str(edge.get("to", ""))] += 1
    for node in graph["nodes"]:
        page_id = str(node.get("page_id", ""))
        node["inbound_count"] = final_incoming.get(page_id, 0)
        node["outbound_count"] = final_outgoing.get(page_id, 0)

    index_title = "Portfolio 总索引" if namespace_key == config.account_namespace_key else f"{config.namespaces[namespace_key].display_name} 资产总索引"
    log_title = "Portfolio 运行日志" if namespace_key == config.account_namespace_key else f"{config.namespaces[namespace_key].display_name} 运行日志"
    namespace_root = namespace_root_dir(config, namespace_key)
    rel_index_path = relative_to_root(namespace_root / "01_Index.md", config.wiki_src_dir)
    rel_log_path = relative_to_root(namespace_root / "02_Log.md", config.wiki_src_dir)
    index_page_id = namespaced_page_id(namespace_key, "index")
    log_page_id = namespaced_page_id(namespace_key, "log")
    home_page_id = namespaced_page_id(namespace_key, "home")
    index_lines = [f"# {index_title}", "", "## Canonical 页面", ""]
    canonical_index_nodes = [
        item
        for item in graph["nodes"]
        if not item.get("generated_report") and str(item.get("page_id", "")) != index_page_id
    ]
    generated_index_nodes = [item for item in graph["nodes"] if item.get("generated_report")]
    for item in sorted(canonical_index_nodes, key=lambda node: (str(node["page_type"]), str(node["title"]))):
        mapped_page = page_map.get(str(item["page_id"]), {})
        frontmatter = mapped_page.get("frontmatter", {})
        rel_path = relative_to_root(mapped_page["path"], config.root) if "path" in mapped_page else str(item.get("local_path", ""))
        index_lines.append(
            f"- `{item['page_type']}` [{frontmatter.get('title', item['title'])}]({rel_path}) | inbound={item['inbound_count']} | sources={item['source_count']}"
        )
    if generated_index_nodes:
        index_lines.extend(["", "## Generated query reports", ""])
        for item in sorted(generated_index_nodes, key=lambda node: str(node["title"])):
            index_lines.append(f"- `{item['page_type']}` {item['title']} | {item['local_path']}")

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

    index_text = write_canonical_page(
        config.wiki_src_dir,
        index_page_id,
        index_title,
        "Index",
        rel_index_path,
        page_asset_key(namespace_key, "index"),
        [],
        [str(node["page_id"]) for node in canonical_index_nodes],
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
