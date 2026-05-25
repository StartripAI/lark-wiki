from __future__ import annotations

import json
import os
from collections import Counter
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

from .config import AppConfig
from .markdown import read_frontmatter
from .utils import json_dumps, read_text_safe, relative_to_root, sha256_text


GRAPHIFY_OUT_DIR = "graphify-out"
GRAPHIFY_MIRROR_DIR = "knowledge/build/graphify/repo"
GRAPHIFY_BUILD_DIR = "knowledge/build/graphify"
CONFIDENCE_WEIGHTS = {
    "EXTRACTED": 4.0,
    "INFERRED": 2.0,
    "AMBIGUOUS": 0.75,
}
SUMMARY_KEYS = {
    "status",
    "source_graph_path",
    "source_report_path",
    "source_html_path",
    "mirror_graph_path",
    "mirror_report_path",
    "mirror_html_path",
    "mapped_node_count",
    "mapped_edge_count",
    "unmapped_node_count",
    "ignored_edge_count",
    "ignored_generated_node_count",
    "ignored_generated_edge_count",
    "ignored_generated_hyperedge_count",
    "source_hash",
    "recommended_command",
    "artifact_state",
    "source_node_count",
    "source_edge_count",
    "source_hyperedge_count",
}
GENERATED_QUERY_REPORT_MARKER = "/reports/query-"
DEFAULT_GRAPHIFY_QUERY_BUDGET = 1500


def _rel(config: AppConfig, path: Path) -> str:
    return relative_to_root(path, config.root)


def _source_dir(config: AppConfig) -> Path:
    return config.root / GRAPHIFY_OUT_DIR


def _mirror_dir(config: AppConfig) -> Path:
    return config.root / GRAPHIFY_MIRROR_DIR


def _graphify_build_dir(config: AppConfig) -> Path:
    return config.root / GRAPHIFY_BUILD_DIR


def _source_paths(config: AppConfig) -> dict[str, Path]:
    root = _source_dir(config)
    return {
        "graph": root / "graph.json",
        "report": root / "GRAPH_REPORT.md",
        "html": root / "graph.html",
    }


def _mirror_paths(config: AppConfig) -> dict[str, Path]:
    root = _mirror_dir(config)
    return {
        "graph": root / "graph.json",
        "report": root / "GRAPH_REPORT.md",
        "html": root / "graph.html",
        "summary": root / "import_summary.json",
    }


def _insights_paths(config: AppConfig) -> dict[str, Path]:
    root = _graphify_build_dir(config)
    return {
        "json": root / "insights.json",
        "markdown": root / "insights.md",
    }


def _candidates_paths(config: AppConfig, suffix: str) -> dict[str, Path]:
    root = _graphify_build_dir(config)
    return {
        "json": root / f"candidates_{suffix}.json",
        "markdown": root / f"candidates_{suffix}.md",
    }


def _find_graphify_binary() -> tuple[str, str]:
    for command in ("graphify", "graphifyy"):
        found = shutil.which(command)
        if found:
            return command, found

    candidates: list[Path] = []
    scripts_path = sysconfig.get_path("scripts")
    if scripts_path:
        candidates.extend([Path(scripts_path) / "graphify", Path(scripts_path) / "graphifyy"])
    candidates.extend(
        [
            Path.home() / "Library" / "Python" / f"{sys.version_info.major}.{sys.version_info.minor}" / "bin" / "graphify",
            Path.home() / "Library" / "Python" / f"{sys.version_info.major}.{sys.version_info.minor}" / "bin" / "graphifyy",
            Path.home() / ".local" / "bin" / "graphify",
            Path.home() / ".local" / "bin" / "graphifyy",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate), str(candidate)
    return "", ""


def _resolved_graph_path(config: AppConfig) -> Path:
    mirror = _mirror_paths(config)
    source = _source_paths(config)
    return mirror["graph"] if mirror["graph"].exists() else source["graph"]


def _resolved_report_path(config: AppConfig) -> Path:
    mirror = _mirror_paths(config)
    source = _source_paths(config)
    return mirror["report"] if mirror["report"].exists() else source["report"]


def _load_report_text(path: Path) -> str:
    return read_text_safe(path) if path.exists() else ""


def _normalise_path(config: AppConfig, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("file://"):
        text = text.removeprefix("file://")
    path = Path(text)
    if path.is_absolute():
        try:
            return relative_to_root(path, config.root)
        except ValueError:
            return text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _graph_counts(payload: dict[str, Any]) -> dict[str, int]:
    nodes, edges = _normalise_graph_payload(payload)
    hyperedges = payload.get("hyperedges", [])
    return {
        "source_node_count": len(nodes),
        "source_edge_count": len(edges),
        "source_hyperedge_count": len(hyperedges) if isinstance(hyperedges, list) else 0,
    }


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary[key] for key in SUMMARY_KEYS if key in summary}


def _read_report_excerpt(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    return read_text_safe(path)[:limit].strip()


def _scan_disk_pages(config: AppConfig) -> dict[str, dict[str, str]]:
    pages: dict[str, dict[str, str]] = {}
    if not config.wiki_src_dir.exists():
        return pages
    for path in sorted(config.wiki_src_dir.rglob("*.md")):
        try:
            frontmatter, _body = read_frontmatter(path)
        except (json.JSONDecodeError, ValueError, OSError):
            frontmatter = {}
        page_id = str(frontmatter.get("page_id") or "").strip()
        if not page_id:
            continue
        pages[relative_to_root(path, config.root)] = {
            "page_id": page_id,
            "title": str(frontmatter.get("title") or path.stem),
            "namespace_key": str(frontmatter.get("namespace_key") or ""),
            "local_path": relative_to_root(path, config.root),
            "asset_key": str(frontmatter.get("asset_key") or ""),
        }
    return pages


def _repo_maps(conn: sqlite3.Connection, config: AppConfig) -> dict[str, dict[str, dict[str, str]]]:
    pages_by_path = _scan_disk_pages(config)
    pages_by_id = {page["page_id"]: page for page in pages_by_path.values()}
    pages_by_asset: dict[str, dict[str, str]] = {}
    for row in conn.execute(
        """
        SELECT page_id, namespace_key, page_type, asset_key, local_path, metadata_json
        FROM pages
        ORDER BY page_id
        """
    ):
        local_path = str(row["local_path"] or "")
        page = {
            "page_id": str(row["page_id"] or ""),
            "title": "",
            "namespace_key": str(row["namespace_key"] or ""),
            "local_path": local_path,
            "asset_key": str(row["asset_key"] or ""),
        }
        if local_path:
            pages_by_path[local_path] = {**pages_by_path.get(local_path, {}), **page}
        pages_by_id[page["page_id"]] = {**pages_by_id.get(page["page_id"], {}), **page}
        if page["asset_key"]:
            pages_by_asset[page["asset_key"]] = page

    assets_by_path: dict[str, dict[str, str]] = {}
    assets_by_key: dict[str, dict[str, str]] = {}
    for row in conn.execute(
        """
        SELECT asset_key, namespace_key, asset_class, title, local_path
        FROM assets
        ORDER BY asset_key
        """
    ):
        asset = {
            "asset_key": str(row["asset_key"] or ""),
            "namespace_key": str(row["namespace_key"] or ""),
            "asset_class": str(row["asset_class"] or ""),
            "title": str(row["title"] or ""),
            "local_path": str(row["local_path"] or ""),
        }
        assets_by_key[asset["asset_key"]] = asset
        if asset["local_path"]:
            assets_by_path[asset["local_path"]] = asset

    return {
        "pages_by_path": pages_by_path,
        "pages_by_id": pages_by_id,
        "pages_by_asset": pages_by_asset,
        "assets_by_path": assets_by_path,
        "assets_by_key": assets_by_key,
    }


def _match_node(
    node: dict[str, Any],
    maps: dict[str, dict[str, dict[str, str]]],
    config: AppConfig,
) -> dict[str, str]:
    node_id = str(node.get("id") or "").strip()
    source_file = _normalise_path(
        config,
        node.get("source_file")
        or node.get("source_path")
        or node.get("file_path")
        or node.get("path")
        or "",
    )
    node_path = _normalise_path(config, node_id)
    page = maps["pages_by_id"].get(node_id)
    if not page and source_file:
        page = maps["pages_by_path"].get(source_file)
    if not page and node_path:
        page = maps["pages_by_path"].get(node_path)
    asset = maps["assets_by_key"].get(node_id)
    if not asset and source_file:
        asset = maps["assets_by_path"].get(source_file)
    if not asset and node_path:
        asset = maps["assets_by_path"].get(node_path)
    if page:
        return {
            "graphify_id": node_id,
            "mapped_type": "page",
            "page_id": page.get("page_id", ""),
            "asset_key": page.get("asset_key", ""),
            "namespace_key": page.get("namespace_key", ""),
            "local_path": page.get("local_path", source_file),
        }
    if asset:
        linked_page = maps["pages_by_asset"].get(asset.get("asset_key", ""))
        return {
            "graphify_id": node_id,
            "mapped_type": "asset",
            "page_id": linked_page.get("page_id", "") if linked_page else "",
            "asset_key": asset.get("asset_key", ""),
            "namespace_key": asset.get("namespace_key", ""),
            "local_path": asset.get("local_path", source_file),
        }
    return {
        "graphify_id": node_id,
        "mapped_type": "",
        "page_id": "",
        "asset_key": "",
        "namespace_key": "",
        "local_path": source_file,
    }


def _confidence(edge: dict[str, Any]) -> str:
    confidence = str(edge.get("confidence") or "INFERRED").strip().upper()
    return confidence if confidence in CONFIDENCE_WEIGHTS else "INFERRED"


def _edge_score(edge: dict[str, Any]) -> float:
    base = CONFIDENCE_WEIGHTS[_confidence(edge)]
    raw = edge.get("confidence_score", 1.0)
    try:
        multiplier = float(raw)
    except (TypeError, ValueError):
        multiplier = 1.0
    multiplier = max(0.0, min(multiplier, 1.5))
    return round(base * multiplier, 3)


def _edge_reason(edge: dict[str, Any]) -> str:
    relation = str(edge.get("relation") or edge.get("type") or edge.get("label") or edge.get("kind") or "relation").strip()
    safe_relation = relation.replace(" ", "_") if relation else "relation"
    return f"graphify:{safe_relation}"


def _normalise_graph_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_nodes = payload.get("nodes", [])
    raw_edges = payload.get("links", payload.get("edges", []))
    nodes = [node for node in raw_nodes if isinstance(node, dict)]
    edges = [edge for edge in raw_edges if isinstance(edge, dict)]
    return nodes, edges


def _node_source_file(config: AppConfig, node: dict[str, Any]) -> str:
    return _normalise_path(
        config,
        node.get("source_file")
        or node.get("source_path")
        or node.get("file_path")
        or node.get("path")
        or "",
    )


def _edge_source_file(config: AppConfig, edge: dict[str, Any]) -> str:
    return _normalise_path(
        config,
        edge.get("source_file")
        or edge.get("source_path")
        or edge.get("file_path")
        or edge.get("path")
        or "",
    )


def _edge_endpoint_ids(edge: dict[str, Any]) -> tuple[str, str]:
    return str(edge.get("source", edge.get("from", "")) or ""), str(edge.get("target", edge.get("to", "")) or "")


def _node_is_generated_query(config: AppConfig, node: dict[str, Any]) -> bool:
    return _is_generated_query_source(_node_source_file(config, node))


def _graph_generated_query_ids(config: AppConfig, nodes: list[dict[str, Any]]) -> set[str]:
    return {str(node.get("id") or "") for node in nodes if str(node.get("id") or "") and _node_is_generated_query(config, node)}


def _graph_generated_counts(config: AppConfig, payload: dict[str, Any]) -> dict[str, int]:
    nodes, edges = _normalise_graph_payload(payload)
    generated_ids = _graph_generated_query_ids(config, nodes)
    generated_edge_count = 0
    for edge in edges:
        source_id, target_id = _edge_endpoint_ids(edge)
        if source_id in generated_ids or target_id in generated_ids or _is_generated_query_source(_edge_source_file(config, edge)):
            generated_edge_count += 1
    generated_hyperedge_count = 0
    for hyperedge in payload.get("hyperedges", []) if isinstance(payload.get("hyperedges", []), list) else []:
        if not isinstance(hyperedge, dict):
            continue
        node_ids = [str(node_id) for node_id in hyperedge.get("nodes", [])] if isinstance(hyperedge.get("nodes", []), list) else []
        if any(node_id in generated_ids for node_id in node_ids) or _is_generated_query_source(_edge_source_file(config, hyperedge)):
            generated_hyperedge_count += 1
    return {
        "ignored_generated_node_count": len(generated_ids),
        "ignored_generated_edge_count": generated_edge_count,
        "ignored_generated_hyperedge_count": generated_hyperedge_count,
    }


def _filter_graph_payload_for_consumption(
    config: AppConfig,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    nodes, edges = _normalise_graph_payload(payload)
    generated_ids = _graph_generated_query_ids(config, nodes)
    filtered_nodes = [node for node in nodes if str(node.get("id") or "") not in generated_ids]
    filtered_edges = []
    for edge in edges:
        source_id, target_id = _edge_endpoint_ids(edge)
        if source_id in generated_ids or target_id in generated_ids or _is_generated_query_source(_edge_source_file(config, edge)):
            continue
        filtered_edges.append(edge)
    filtered_hyperedges = []
    for hyperedge in payload.get("hyperedges", []) if isinstance(payload.get("hyperedges", []), list) else []:
        if not isinstance(hyperedge, dict):
            continue
        node_ids = [str(node_id) for node_id in hyperedge.get("nodes", [])] if isinstance(hyperedge.get("nodes", []), list) else []
        if any(node_id in generated_ids for node_id in node_ids) or _is_generated_query_source(_edge_source_file(config, hyperedge)):
            continue
        filtered_hyperedges.append(hyperedge)
    counts = {
        "raw_node_count": len(nodes),
        "raw_edge_count": len(edges),
        "raw_hyperedge_count": len(payload.get("hyperedges", [])) if isinstance(payload.get("hyperedges", []), list) else 0,
        **_graph_generated_counts(config, payload),
    }
    return filtered_nodes, filtered_edges, filtered_hyperedges, counts


def _source_graph_hash(config: AppConfig) -> tuple[str, dict[str, Any]]:
    source_graph = _source_paths(config)["graph"]
    payload = _load_json(source_graph)
    if not payload:
        return "", {}
    return sha256_text(json_dumps(payload)), payload


def graphify_artifact_state(config: AppConfig) -> dict[str, Any]:
    source = _source_paths(config)
    mirror = _mirror_paths(config)
    if not source["graph"].exists():
        return {
            "artifact_state": "missing_source",
            "source_hash": "",
            "imported_source_hash": "",
            "source_graph_path": _rel(config, source["graph"]),
            "mirror_graph_path": _rel(config, mirror["graph"]),
            "source_node_count": 0,
            "source_edge_count": 0,
            "source_hyperedge_count": 0,
            "ignored_generated_node_count": 0,
            "ignored_generated_edge_count": 0,
            "ignored_generated_hyperedge_count": 0,
        }
    source_hash, payload = _source_graph_hash(config)
    if not payload:
        return {
            "artifact_state": "invalid_source",
            "source_hash": "",
            "imported_source_hash": "",
            "source_graph_path": _rel(config, source["graph"]),
            "mirror_graph_path": _rel(config, mirror["graph"]),
            "source_node_count": 0,
            "source_edge_count": 0,
            "source_hyperedge_count": 0,
            "ignored_generated_node_count": 0,
            "ignored_generated_edge_count": 0,
            "ignored_generated_hyperedge_count": 0,
        }
    summary = _load_json(mirror["summary"])
    imported_hash = str(summary.get("source_hash") or "") if summary else ""
    if not mirror["graph"].exists() or not summary:
        artifact_state = "not_imported"
    elif imported_hash != source_hash:
        artifact_state = "stale_import"
    else:
        artifact_state = "current"
    return {
        "artifact_state": artifact_state,
        "source_hash": source_hash,
        "imported_source_hash": imported_hash,
        "source_graph_path": _rel(config, source["graph"]),
        "mirror_graph_path": _rel(config, mirror["graph"]),
        **_graph_counts(payload),
        **_graph_generated_counts(config, payload),
    }


def _import_payload(
    conn: sqlite3.Connection,
    config: AppConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    nodes, edges = _normalise_graph_payload(payload)
    maps = _repo_maps(conn, config)
    node_matches: dict[str, dict[str, str]] = {}
    mapped_nodes: list[dict[str, Any]] = []
    generated_node_ids = _graph_generated_query_ids(config, nodes)
    for node in nodes:
        graphify_id = str(node.get("id") or "").strip()
        if not graphify_id:
            continue
        if graphify_id in generated_node_ids:
            continue
        match = _match_node(node, maps, config)
        node_matches[graphify_id] = match
        if not match["mapped_type"]:
            continue
        mapped_nodes.append(
            {
                "graphify_id": graphify_id,
                "mapped_type": match["mapped_type"],
                "page_id": match["page_id"],
                "asset_key": match["asset_key"],
                "namespace_key": match["namespace_key"],
                "local_path": match["local_path"],
                "label": str(node.get("label") or graphify_id),
                "file_type": str(node.get("file_type") or ""),
                "source_file": _normalise_path(config, node.get("source_file", "")),
                "community": node.get("community", ""),
            }
        )

    mapped_edges: list[dict[str, Any]] = []
    ignored_edge_count = 0
    ignored_generated_edge_count = 0
    for edge in edges:
        source_id, target_id = _edge_endpoint_ids(edge)
        if source_id in generated_node_ids or target_id in generated_node_ids or _is_generated_query_source(_edge_source_file(config, edge)):
            ignored_edge_count += 1
            ignored_generated_edge_count += 1
            continue
        source_match = node_matches.get(source_id, {})
        target_match = node_matches.get(target_id, {})
        from_page = source_match.get("page_id", "")
        to_page = target_match.get("page_id", "")
        if not from_page or not to_page or from_page == to_page:
            ignored_edge_count += 1
            continue
        mapped_edges.append(
            {
                "from": from_page,
                "to": to_page,
                "score": _edge_score(edge),
                "reasons": [_edge_reason(edge)],
                "source_layer": "graphify",
                "graphify": {
                    "source": source_id,
                    "target": target_id,
                    "relation": str(edge.get("relation") or edge.get("type") or edge.get("label") or edge.get("kind") or ""),
                    "confidence": _confidence(edge),
                    "confidence_score": edge.get("confidence_score", ""),
                    "source_file": _normalise_path(
                        config,
                        edge.get("source_file")
                        or edge.get("source_path")
                        or edge.get("file_path")
                        or edge.get("path")
                        or "",
                    ),
                },
            }
        )

    mapped_edges.sort(key=lambda item: (-float(item["score"]), str(item["from"]), str(item["to"])))
    mapped_nodes.sort(key=lambda item: (str(item["namespace_key"]), str(item["page_id"]), str(item["asset_key"])))
    return {
        "mapped_nodes": mapped_nodes,
        "mapped_edges": mapped_edges,
        "mapped_node_count": len(mapped_nodes),
        "mapped_edge_count": len(mapped_edges),
        "unmapped_node_count": max(len(nodes) - len(mapped_nodes) - len(generated_node_ids), 0),
        "ignored_edge_count": ignored_edge_count,
        "ignored_generated_node_count": len(generated_node_ids),
        "ignored_generated_edge_count": ignored_generated_edge_count,
        "ignored_generated_hyperedge_count": _graph_generated_counts(config, payload)["ignored_generated_hyperedge_count"],
    }


def graphify_status(conn: sqlite3.Connection, config: AppConfig) -> dict[str, Any]:
    source = _source_paths(config)
    mirror = _mirror_paths(config)
    graphify_command, graphify_bin = _find_graphify_binary()
    report_path = mirror["report"] if mirror["report"].exists() else source["report"]
    artifact_state = graphify_artifact_state(config)
    summary = graphify_import_summary(config)
    graphify_update_command = f"{graphify_command} update ." if graphify_command else ""
    recommended_workflow = [
        "$graphify .",
        "python3 scripts/lark_wiki.py graphify_import",
        "python3 scripts/lark_wiki.py query --namespace project::agent_workspace --query handoff",
    ]
    return {
        "graphify_available": bool(graphify_bin),
        "graphify_command": graphify_command,
        "graphify_path": graphify_bin,
        "official_refresh_command": "$graphify .",
        "graphify_shell_command": graphify_update_command,
        "graphify_update_command": graphify_update_command,
        "artifact_state": artifact_state["artifact_state"],
        "source_hash": artifact_state.get("source_hash", ""),
        "imported_source_hash": artifact_state.get("imported_source_hash", ""),
        "mapped_node_count": summary.get("mapped_node_count", 0),
        "mapped_edge_count": summary.get("mapped_edge_count", 0),
        "unmapped_node_count": summary.get("unmapped_node_count", 0),
        "ignored_edge_count": summary.get("ignored_edge_count", 0),
        "ignored_generated_node_count": artifact_state.get("ignored_generated_node_count", summary.get("ignored_generated_node_count", 0)),
        "ignored_generated_edge_count": artifact_state.get("ignored_generated_edge_count", summary.get("ignored_generated_edge_count", 0)),
        "ignored_generated_hyperedge_count": artifact_state.get(
            "ignored_generated_hyperedge_count", summary.get("ignored_generated_hyperedge_count", 0)
        ),
        "source_node_count": artifact_state.get("source_node_count", 0),
        "source_edge_count": artifact_state.get("source_edge_count", 0),
        "source_hyperedge_count": artifact_state.get("source_hyperedge_count", 0),
        "source_graph_path": _rel(config, source["graph"]),
        "source_graph_exists": source["graph"].exists(),
        "source_report_path": _rel(config, source["report"]),
        "source_report_exists": source["report"].exists(),
        "source_html_path": _rel(config, source["html"]),
        "source_html_exists": source["html"].exists(),
        "mirror_graph_path": _rel(config, mirror["graph"]),
        "mirror_graph_exists": mirror["graph"].exists(),
        "mirror_report_path": _rel(config, mirror["report"]),
        "mirror_report_exists": mirror["report"].exists(),
        "mirror_html_path": _rel(config, mirror["html"]),
        "mirror_html_exists": mirror["html"].exists(),
        "report_readable": bool(_read_report_excerpt(report_path, limit=1)),
        "recommended_workflow": recommended_workflow,
    }


def graphify_import(conn: sqlite3.Connection, config: AppConfig) -> dict[str, Any]:
    source = _source_paths(config)
    mirror = _mirror_paths(config)
    mirror_root = _mirror_dir(config)
    mirror_root.mkdir(parents=True, exist_ok=True)

    if not source["graph"].exists():
        graphify_command, _graphify_bin = _find_graphify_binary()
        summary = {
            "status": "missing_source",
            "artifact_state": "missing_source",
            "source_graph_path": _rel(config, source["graph"]),
            "mirror_graph_path": _rel(config, mirror["graph"]),
            "mirror_report_path": _rel(config, mirror["report"]),
            "mirror_html_path": _rel(config, mirror["html"]),
            "mapped_node_count": 0,
            "mapped_edge_count": 0,
            "unmapped_node_count": 0,
            "ignored_edge_count": 0,
            "ignored_generated_node_count": 0,
            "ignored_generated_edge_count": 0,
            "ignored_generated_hyperedge_count": 0,
            "source_node_count": 0,
            "source_edge_count": 0,
            "source_hyperedge_count": 0,
            "recommended_command": "$graphify .",
        }
        mirror["summary"].write_text(json_dumps(summary), encoding="utf-8")
        return summary

    payload = _load_json(source["graph"])
    imported = _import_payload(conn, config, payload) if payload else {
        "mapped_nodes": [],
        "mapped_edges": [],
        "mapped_node_count": 0,
        "mapped_edge_count": 0,
        "unmapped_node_count": 0,
        "ignored_edge_count": 0,
        "ignored_generated_node_count": 0,
        "ignored_generated_edge_count": 0,
        "ignored_generated_hyperedge_count": 0,
    }
    shutil.copy2(source["graph"], mirror["graph"])
    if source["report"].exists():
        shutil.copy2(source["report"], mirror["report"])
    if source["html"].exists():
        shutil.copy2(source["html"], mirror["html"])

    summary = {
        "status": "success" if payload else "invalid_source",
        "artifact_state": "current" if payload else "invalid_source",
        "source_graph_path": _rel(config, source["graph"]),
        "source_report_path": _rel(config, source["report"]),
        "source_html_path": _rel(config, source["html"]),
        "mirror_graph_path": _rel(config, mirror["graph"]),
        "mirror_report_path": _rel(config, mirror["report"]),
        "mirror_html_path": _rel(config, mirror["html"]),
        "mapped_node_count": imported["mapped_node_count"],
        "mapped_edge_count": imported["mapped_edge_count"],
        "unmapped_node_count": imported["unmapped_node_count"],
        "ignored_edge_count": imported["ignored_edge_count"],
        "ignored_generated_node_count": imported["ignored_generated_node_count"],
        "ignored_generated_edge_count": imported["ignored_generated_edge_count"],
        "ignored_generated_hyperedge_count": imported["ignored_generated_hyperedge_count"],
        "source_hash": sha256_text(json_dumps(payload)),
        **_graph_counts(payload),
    }
    output = {
        **summary,
        "mapped_nodes": imported["mapped_nodes"],
        "mapped_edges": imported["mapped_edges"],
    }
    mirror["summary"].write_text(json_dumps(output), encoding="utf-8")
    return summary


def graphify_import_summary(config: AppConfig) -> dict[str, Any]:
    mirror = _mirror_paths(config)
    summary = _load_json(mirror["summary"])
    if summary:
        compact = _compact_summary(summary)
        state = graphify_artifact_state(config)
        compact["artifact_state"] = state["artifact_state"]
        compact["source_hash"] = state.get("source_hash", compact.get("source_hash", ""))
        compact["source_node_count"] = state.get("source_node_count", compact.get("source_node_count", 0))
        compact["source_edge_count"] = state.get("source_edge_count", compact.get("source_edge_count", 0))
        compact["source_hyperedge_count"] = state.get("source_hyperedge_count", compact.get("source_hyperedge_count", 0))
        compact["ignored_generated_node_count"] = state.get(
            "ignored_generated_node_count", compact.get("ignored_generated_node_count", 0)
        )
        compact["ignored_generated_edge_count"] = state.get(
            "ignored_generated_edge_count", compact.get("ignored_generated_edge_count", 0)
        )
        compact["ignored_generated_hyperedge_count"] = state.get(
            "ignored_generated_hyperedge_count", compact.get("ignored_generated_hyperedge_count", 0)
        )
        return compact
    source = _source_paths(config)
    return {
        "status": "not_imported" if source["graph"].exists() else "missing_source",
        "artifact_state": graphify_artifact_state(config)["artifact_state"],
        "source_graph_path": _rel(config, source["graph"]),
        "mirror_graph_path": _rel(config, mirror["graph"]),
        "mirror_report_path": _rel(config, mirror["report"]),
        "mirror_html_path": _rel(config, mirror["html"]),
        "mapped_node_count": 0,
        "mapped_edge_count": 0,
        "unmapped_node_count": 0,
        "ignored_edge_count": 0,
        "ignored_generated_node_count": 0,
        "ignored_generated_edge_count": 0,
        "ignored_generated_hyperedge_count": 0,
        "source_node_count": 0,
        "source_edge_count": 0,
        "source_hyperedge_count": 0,
    }


def load_graphify_enrichment(
    conn: sqlite3.Connection,
    config: AppConfig,
    namespace_key: str | None = None,
) -> dict[str, Any]:
    mirror = _mirror_paths(config)
    source = _source_paths(config)
    graph_path = mirror["graph"] if mirror["graph"].exists() else source["graph"]
    payload = _load_json(graph_path)
    if not payload:
        return {
            "nodes": [],
            "edges": [],
            "summary": graphify_import_summary(config),
        }
    imported = _import_payload(conn, config, payload)
    nodes = imported["mapped_nodes"]
    edges = imported["mapped_edges"]
    if namespace_key:
        nodes = [node for node in nodes if node.get("namespace_key") in {"", namespace_key}]
        page_ids = {str(node.get("page_id", "")) for node in nodes if node.get("page_id")}
        edges = [
            edge
            for edge in edges
            if str(edge.get("from", "")) in page_ids and str(edge.get("to", "")) in page_ids
        ]
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            **graphify_import_summary(config),
            "mapped_node_count": len(nodes),
            "mapped_edge_count": len(edges),
        },
    }


def _run_graphify_cli(config: AppConfig, args: list[str]) -> dict[str, Any]:
    graphify_command, graphify_bin = _find_graphify_binary()
    graph_path = _resolved_graph_path(config)
    if not graphify_bin:
        return {
            "ok": False,
            "status": "missing_graphify",
            "graph_path": _rel(config, graph_path),
            "executed_command": "",
            "stdout": "",
            "stderr": "graphify command not found; run the official Graphify install workflow first",
            "returncode": 127,
        }
    if not graph_path.exists():
        return {
            "ok": False,
            "status": "missing_graph",
            "graph_path": _rel(config, graph_path),
            "executed_command": "",
            "stdout": "",
            "stderr": "graphify graph not found; run the official Graphify workflow, then graphify_import",
            "returncode": 1,
        }
    command = [graphify_command, *args, "--graph", str(graph_path)]
    try:
        proc = subprocess.run(
            command,
            cwd=config.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "ok": False,
            "status": "failed",
            "graph_path": _rel(config, graph_path),
            "executed_command": " ".join(command),
            "stdout": "",
            "stderr": str(exc),
            "returncode": 126,
        }
    stdout, filtered_line_count = _filter_generated_query_stdout(proc.stdout.strip())
    return {
        "ok": proc.returncode == 0,
        "status": "success" if proc.returncode == 0 else "failed",
        "graph_path": _rel(config, graph_path),
        "executed_command": " ".join(command),
        "stdout": stdout,
        "stderr": proc.stderr.strip(),
        "returncode": proc.returncode,
        "filtered_generated_query_line_count": filtered_line_count,
    }


def graphify_query(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    query_text: str,
    budget: int = DEFAULT_GRAPHIFY_QUERY_BUDGET,
    dfs: bool = False,
) -> dict[str, Any]:
    args = ["query", query_text, "--budget", str(budget)]
    if dfs:
        args.append("--dfs")
    return _run_graphify_cli(config, args)


def graphify_path(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    source: str,
    target: str,
) -> dict[str, Any]:
    return _run_graphify_cli(config, ["path", source, target])


def graphify_explain(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    node: str,
) -> dict[str, Any]:
    return _run_graphify_cli(config, ["explain", node])


def _degree_counts(edges: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for edge in edges:
        source = str(edge.get("source", edge.get("from", "")) or "")
        target = str(edge.get("target", edge.get("to", "")) or "")
        if source:
            counts[source] += 1
        if target:
            counts[target] += 1
    return counts


def _report_section(report_text: str, heading: str) -> list[str]:
    marker = f"## {heading}"
    start = report_text.find(marker)
    if start == -1:
        return []
    next_start = report_text.find("\n## ", start + 1)
    section = report_text[start : next_start if next_start != -1 else len(report_text)]
    lines = []
    for line in section.splitlines()[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("_"):
            continue
        if stripped.startswith("- ") or stripped[0:1].isdigit():
            lines.append(stripped)
    return lines


def _source_in_namespace(config: AppConfig, source_file: str, namespace_key: str) -> bool:
    if not namespace_key:
        return True
    namespace_root = ""
    namespace = config.namespaces.get(namespace_key)
    if namespace:
        if namespace.kind == "project":
            namespace_root = f"knowledge/wiki_src/projects/{namespace.slug}/"
        elif namespace.kind in {"shared", "inbox"}:
            namespace_root = f"knowledge/wiki_src/{namespace.slug}/"
        else:
            namespace_root = "knowledge/wiki_src/account/"
    return source_file.startswith(namespace_root)


def _is_generated_query_source(source_file: str) -> bool:
    path = source_file.replace("\\", "/")
    return GENERATED_QUERY_REPORT_MARKER in path or Path(path).name.startswith("query-")


def _filter_generated_query_stdout(stdout: str) -> tuple[str, int]:
    if not stdout:
        return "", 0
    kept: list[str] = []
    filtered = 0
    for line in stdout.splitlines():
        if GENERATED_QUERY_REPORT_MARKER in line or "Query Report:" in line:
            filtered += 1
            continue
        kept.append(line)
    return "\n".join(kept).strip(), filtered


def _proposed_page_type(source_file: str, file_type: str) -> str:
    path = source_file.replace("\\", "/")
    if file_type == "code":
        return "Code"
    if path.startswith("assets/"):
        return "Source"
    if path in {"README.md", "AGENTS.md"} or path.endswith("/README.md"):
        return "Concept"
    if path.startswith("demo/") or path.startswith("examples/"):
        return "Source"
    if "/concepts/" in path:
        return "Concept"
    if "/entities/" in path:
        return "Entity"
    if "/reports/" in path:
        return "Report"
    if "/sources/" in path:
        return "Source"
    return "Concept"


def _candidate_source_allowed(source_file: str, source_scope: str) -> bool:
    if source_scope == "all":
        return True
    if source_scope == "wiki":
        return source_file.startswith("knowledge/wiki_src/")
    if source_scope == "docs":
        return (
            source_file in {"README.md", "AGENTS.md"}
            or source_file.startswith("examples/")
            or source_file.startswith("demo/")
            or source_file.startswith("assets/")
        )
    return True


def _is_code_like_candidate(file_type: str, source_file: str, label: str) -> bool:
    path = source_file.replace("\\", "/")
    if file_type == "code":
        return True
    if path.startswith(("scripts/", "tests/")):
        return True
    if label.endswith("()"):
        return True
    return False


def graphify_candidates(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str | None = None,
    limit: int = 25,
    min_degree: int = 2,
    source_scope: str = "all",
    include_code: bool = False,
    write_files: bool = True,
) -> dict[str, Any]:
    graph_path = _resolved_graph_path(config)
    payload = _load_json(graph_path)
    nodes, edges = _normalise_graph_payload(payload)
    imported = _import_payload(conn, config, payload) if payload else {
        "mapped_nodes": [],
        "mapped_edges": [],
    }
    mapped_ids = {str(node.get("graphify_id", "")) for node in imported.get("mapped_nodes", [])}
    degrees = _degree_counts(edges)
    report_path = _resolved_report_path(config)
    report_text = _load_report_text(report_path)
    hyperedge_node_ids: set[str] = set()
    for hyperedge in payload.get("hyperedges", []) if isinstance(payload.get("hyperedges", []), list) else []:
        for node_id in hyperedge.get("nodes", []) if isinstance(hyperedge, dict) else []:
            hyperedge_node_ids.add(str(node_id))

    candidates: list[dict[str, Any]] = []
    for node in nodes:
        graphify_id = str(node.get("id") or "")
        if not graphify_id or graphify_id in mapped_ids:
            continue
        file_type = str(node.get("file_type") or "")
        source_file = _normalise_path(config, node.get("source_file", ""))
        label = str(node.get("label") or graphify_id)
        if not include_code and _is_code_like_candidate(file_type, source_file, label):
            continue
        if _is_generated_query_source(source_file):
            continue
        if namespace_key and source_file.startswith("knowledge/wiki_src/") and not _source_in_namespace(config, source_file, namespace_key):
            continue
        if not _candidate_source_allowed(source_file, source_scope):
            continue
        degree = int(degrees[graphify_id])
        if degree < min_degree:
            continue
        why: list[str] = []
        if degree >= min_degree:
            why.append(f"{degree} graph connections")
        if graphify_id in hyperedge_node_ids:
            why.append("part of a Graphify group relationship")
        if label and label in report_text:
            why.append("mentioned in Graphify report")
        if source_file.startswith(("README", "AGENTS", "assets/", "demo/", "examples/")):
            why.append(f"comes from {source_file.split('/', 1)[0]}")
        score = float(degree)
        if graphify_id in hyperedge_node_ids:
            score += 3.0
        if label and label in report_text:
            score += 2.0
        if source_file.startswith(("README", "AGENTS", "assets/")):
            score += 1.0
        candidates.append(
            {
                "graphify_id": graphify_id,
                "label": label,
                "score": round(score, 3),
                "degree": degree,
                "community": node.get("community", ""),
                "source_file": source_file,
                "file_type": file_type,
                "why": why or ["unmapped Graphify node"],
                "proposed_title": label,
                "proposed_page_type": _proposed_page_type(source_file, file_type),
            }
        )
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["source_file"]), str(item["label"])))
    selected = candidates[:limit]
    suffix_parts = []
    if namespace_key:
        suffix_parts.append(namespace_key.replace("::", "_"))
    suffix_parts.append(source_scope)
    paths = _candidates_paths(config, "_".join(suffix_parts))
    payload_out = {
        "status": "success" if payload else "missing_graph",
        "graph_path": _rel(config, graph_path),
        "namespace_key": namespace_key or "",
        "source_scope": source_scope,
        "include_code": include_code,
        "candidate_count": len(selected),
        "total_candidate_count": len(candidates),
        "candidates": selected,
        "json_path": _rel(config, paths["json"]),
        "markdown_path": _rel(config, paths["markdown"]),
    }
    if write_files:
        paths["json"].parent.mkdir(parents=True, exist_ok=True)
        paths["json"].write_text(json_dumps(payload_out), encoding="utf-8")
        lines = ["# Graphify Candidates", "", f"- Candidates: **{len(selected)}**", ""]
        if selected:
            for item in selected:
                why = "; ".join(item["why"])
                lines.append(
                    f"- **{item['label']}** (`{item['graphify_id']}`) | degree={item['degree']} | "
                    f"`{item['proposed_page_type']}` | {item['source_file']} | {why}"
                )
        else:
            lines.append("- No candidates matched the current filters.")
        paths["markdown"].write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload_out


def graphify_insights(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str | None = None,
    scope: str = "repo",
    limit: int = 10,
    write_files: bool = True,
) -> dict[str, Any]:
    graph_path = _resolved_graph_path(config)
    payload = _load_json(graph_path)
    nodes, edges, hyperedge_items, filtered_counts = _filter_graph_payload_for_consumption(config, payload)
    if scope == "namespace" and namespace_key:
        allowed_ids = {
            str(node.get("id"))
            for node in nodes
            if _source_in_namespace(config, _normalise_path(config, node.get("source_file", "")), namespace_key)
        }
        nodes = [node for node in nodes if str(node.get("id")) in allowed_ids]
        edges = [
            edge
            for edge in edges
            if str(edge.get("source", edge.get("from", ""))) in allowed_ids
            and str(edge.get("target", edge.get("to", ""))) in allowed_ids
        ]
    degrees = _degree_counts(edges)
    nodes_by_id = {str(node.get("id")): node for node in nodes}
    communities: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        cid = str(node.get("community", "unknown"))
        communities.setdefault(cid, []).append(node)
    community_summaries = []
    for cid, items in communities.items():
        top = sorted(items, key=lambda item: (-degrees[str(item.get("id"))], str(item.get("label") or item.get("id"))))[:5]
        community_summaries.append(
            {
                "community": cid,
                "node_count": len(items),
                "top_nodes": [
                    {
                        "graphify_id": str(item.get("id") or ""),
                        "label": str(item.get("label") or item.get("id") or ""),
                        "degree": int(degrees[str(item.get("id"))]),
                        "source_file": _normalise_path(config, item.get("source_file", "")),
                    }
                    for item in top
                ],
            }
        )
    community_summaries.sort(key=lambda item: (-int(item["node_count"]), str(item["community"])))
    god_nodes = []
    for node_id, degree in degrees.most_common(limit):
        node = nodes_by_id.get(node_id)
        if not node:
            continue
        god_nodes.append(
            {
                "graphify_id": node_id,
                "label": str(node.get("label") or node_id),
                "degree": int(degree),
                "community": node.get("community", ""),
                "source_file": _normalise_path(config, node.get("source_file", "")),
                "file_type": str(node.get("file_type") or ""),
            }
        )
    report_path = _resolved_report_path(config)
    report_text = _load_report_text(report_path)
    hyperedges = [
        {
            "id": str(item.get("id") or ""),
            "label": str(item.get("label") or ""),
            "nodes": [str(node_id) for node_id in item.get("nodes", [])] if isinstance(item.get("nodes", []), list) else [],
            "relation": str(item.get("relation") or ""),
            "confidence": str(item.get("confidence") or ""),
            "confidence_score": item.get("confidence_score", ""),
            "source_file": _normalise_path(config, item.get("source_file", "")),
        }
        for item in hyperedge_items[:limit]
        if isinstance(item, dict)
    ]
    paths = _insights_paths(config)
    result = {
        "status": "success" if payload else "missing_graph",
        "graph_path": _rel(config, graph_path),
        "report_path": _rel(config, report_path),
        "scope": scope,
        "namespace_key": namespace_key or "",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "hyperedge_count": len(hyperedge_items),
        **filtered_counts,
        "communities": community_summaries[:limit],
        "god_nodes": god_nodes,
        "surprising_connections": _report_section(report_text, "Surprising Connections")[:limit],
        "knowledge_gaps": _report_section(report_text, "Knowledge Gaps")[:limit],
        "suggested_questions": _report_section(report_text, "Suggested Questions")[:limit],
        "hyperedges": hyperedges,
        "json_path": _rel(config, paths["json"]),
        "markdown_path": _rel(config, paths["markdown"]),
    }
    if write_files:
        paths["json"].parent.mkdir(parents=True, exist_ok=True)
        paths["json"].write_text(json_dumps(result), encoding="utf-8")
        lines = [
            "# Graphify Insights",
            "",
            f"- Graph: **{result['node_count']}** nodes / **{result['edge_count']}** edges / **{result['hyperedge_count']}** hyperedges",
            f"- Raw graph: **{result['raw_node_count']}** nodes; ignored generated query nodes: **{result['ignored_generated_node_count']}**",
            f"- Source: `{result['graph_path']}`",
            "",
            "## Communities",
            "",
        ]
        for item in result["communities"]:
            top = ", ".join(node["label"] for node in item["top_nodes"][:3])
            lines.append(f"- **{item['community']}** | nodes={item['node_count']} | top: {top}")
        if not result["communities"]:
            lines.append("- None.")
        lines.extend(["", "## God Nodes", ""])
        lines.extend([f"- **{item['label']}** | degree={item['degree']} | {item['source_file']}" for item in god_nodes] or ["- None."])
        lines.extend(["", "## Hyperedges", ""])
        for item in hyperedges:
            nodes_text = ", ".join(item["nodes"][:5])
            if len(item["nodes"]) > 5:
                nodes_text += f" (+{len(item['nodes']) - 5} more)"
            lines.append(
                f"- **{item['label'] or item['id']}** | {item['relation']} | {item['confidence']} | nodes: {nodes_text or 'none'}"
            )
        if not hyperedges:
            lines.append("- None.")
        lines.extend(["", "## Surprising Connections", ""])
        lines.extend(result["surprising_connections"] or ["- None."])
        lines.extend(["", "## Suggested Questions", ""])
        lines.extend(result["suggested_questions"] or ["- None."])
        lines.extend(["", "## Knowledge Gaps", ""])
        lines.extend(result["knowledge_gaps"] or ["- None."])
        paths["markdown"].write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return result


def graphify_insights_summary(config: AppConfig) -> dict[str, Any]:
    paths = _insights_paths(config)
    payload = _load_json(paths["json"])
    if not payload:
        return {
            "status": "missing",
            "json_path": _rel(config, paths["json"]),
            "markdown_path": _rel(config, paths["markdown"]),
        }
    return {
        "status": payload.get("status", "unknown"),
        "json_path": payload.get("json_path", _rel(config, paths["json"])),
        "markdown_path": payload.get("markdown_path", _rel(config, paths["markdown"])),
        "god_nodes": payload.get("god_nodes", [])[:3],
        "suggested_questions": payload.get("suggested_questions", [])[:3],
        "knowledge_gaps": payload.get("knowledge_gaps", [])[:3],
    }


def _first_matching_line(text: str, needles: tuple[str, ...]) -> str:
    for line in text.splitlines():
        stripped = line.strip().strip("-*| ")
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(needle in lowered for needle in needles):
            return stripped[:240]
    return ""


def _paper_evidence_sidecar(config: AppConfig, limit: int = 8) -> dict[str, Any]:
    source_root = config.root / "examples" / "tutorials" / "research-paper-workbench"
    if not source_root.exists():
        return {
            "status": "missing",
            "source_root": _rel(config, source_root),
            "draft_count": 0,
            "drafts": [],
            "writes_formal_pages": False,
        }

    drafts: list[dict[str, Any]] = []
    for path in sorted(source_root.rglob("*.md")):
        if path.name == "README.md":
            continue
        try:
            frontmatter, body = read_frontmatter(path)
        except (json.JSONDecodeError, ValueError, OSError):
            frontmatter, body = {}, read_text_safe(path)
        text = body or read_text_safe(path)
        lowered = text.lower()
        signals: list[str] = []
        claim = _first_matching_line(text, ("claim", "conclusion", "finding"))
        evidence = _first_matching_line(text, ("evidence", "source", "result", "metric"))
        open_question = _first_matching_line(text, ("open question", "question", "unknown", "todo", "unclear"))
        if claim or "claim" in lowered:
            signals.append("claim")
        if evidence or "evidence" in lowered:
            signals.append("evidence")
        if open_question or "open question" in lowered:
            signals.append("open_question")
        if not signals:
            continue
        title = str(frontmatter.get("title") or path.stem.replace("-", " ").replace("_", " ").title())
        drafts.append(
            {
                "candidate_page": str(frontmatter.get("page_id") or title),
                "title": title,
                "source_file": _rel(config, path),
                "signals": signals,
                "claim": claim,
                "evidence": evidence,
                "open_question": open_question,
                "confidence": "draft",
            }
        )

    drafts.sort(key=lambda item: (-len(item["signals"]), str(item["source_file"])))
    return {
        "status": "available",
        "source_root": _rel(config, source_root),
        "draft_count": len(drafts),
        "drafts": drafts[:limit],
        "writes_formal_pages": False,
    }


def _transport_readiness(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> dict[str, Any]:
    lark_cli_path = shutil.which("lark-cli") or ""
    rows = conn.execute(
        """
        SELECT command_name, status, started_at
        FROM runs
        WHERE namespace_key IN (?, ?)
          AND command_name IN ('upgrade_preflight', 'sync_push', 'sync_pull')
        ORDER BY started_at DESC
        LIMIT 8
        """,
        (namespace_key, config.account_namespace_key),
    ).fetchall()
    latest_runs = [
        {
            "command_name": str(row["command_name"] or ""),
            "status": str(row["status"] or ""),
            "started_at": str(row["started_at"] or ""),
        }
        for row in rows
    ]
    return {
        "lark_cli_available": bool(lark_cli_path),
        "lark_cli_path": lark_cli_path,
        "transport_boundary": "lark-cli handles Feishu read/write only; it does not infer knowledge relations",
        "sync_push_policy": "formal_pages_only",
        "sync_pull_policy": "review_or_merge_before_formal_pages",
        "latest_runs": latest_runs,
        "recommended_commands": [
            "python3 scripts/lark_wiki.py upgrade_preflight",
            f"python3 scripts/lark_wiki.py sync_push --namespace {namespace_key} --limit 1",
        ],
    }


def agent_context(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str | None = None,
    query_text: str = "",
    output_format: str = "json",
) -> dict[str, Any]:
    namespace_key = namespace_key or config.default_project_namespace
    from .inventory import build_relation_inventory

    inventory_summary = build_relation_inventory(conn, config, namespace_key)
    insights = graphify_insights(conn, config, namespace_key=namespace_key, scope="repo", limit=8, write_files=False)
    candidates = graphify_candidates(conn, config, namespace_key=namespace_key, limit=8, min_degree=1, write_files=False)
    query_result = graphify_query(conn, config, query_text=query_text, budget=1000) if query_text else {}
    status = graphify_status(conn, config)
    paper_sidecar = _paper_evidence_sidecar(config)
    transport = _transport_readiness(conn, config, namespace_key)
    graphify_status_summary = {
        key: status.get(key)
        for key in [
                "artifact_state",
                "graphify_available",
                "official_refresh_command",
                "graphify_shell_command",
                "graphify_update_command",
                "source_graph_path",
            "mirror_graph_path",
            "mapped_node_count",
            "mapped_edge_count",
            "unmapped_node_count",
            "ignored_edge_count",
            "ignored_generated_node_count",
            "ignored_generated_edge_count",
            "ignored_generated_hyperedge_count",
        ]
    }
    canonical_inventory = {
        "page_count": inventory_summary.get("page_count", 0),
        "generated_report_count": inventory_summary.get("generated_report_count", 0),
        "source_count": inventory_summary.get("source_count", 0),
        "relation_count": inventory_summary.get("relation_count", 0),
        "issue_count": inventory_summary.get("issue_count", 0),
        "entry_points": inventory_summary.get("entry_points", [])[:5],
        "top_issues": inventory_summary.get("issues", [])[:5],
    }
    derived_graph = {
        "status": graphify_status_summary,
        "insights": {
            "markdown_path": insights.get("markdown_path"),
            "graph_path": insights.get("graph_path"),
            "node_count": insights.get("node_count", 0),
            "edge_count": insights.get("edge_count", 0),
            "hyperedge_count": insights.get("hyperedge_count", 0),
            "raw_node_count": insights.get("raw_node_count", insights.get("node_count", 0)),
            "ignored_generated_node_count": insights.get("ignored_generated_node_count", 0),
            "god_nodes": insights.get("god_nodes", [])[:5],
            "suggested_questions": insights.get("suggested_questions", [])[:5],
            "knowledge_gaps": insights.get("knowledge_gaps", [])[:5],
        },
        "query": query_result,
    }
    candidate_intake = {
        "graphify_candidates": candidates.get("candidates", [])[:5],
        "graphify_candidate_count": candidates.get("candidate_count", 0),
        "graphify_total_candidate_count": candidates.get("total_candidate_count", candidates.get("candidate_count", 0)),
        "graphify_candidates_path": candidates.get("markdown_path", ""),
        "paper_evidence_workbench": paper_sidecar,
    }
    recommended = [
        f"python3 scripts/lark_wiki.py agent_context --namespace {namespace_key}",
        f"python3 scripts/lark_wiki.py inventory --namespace {namespace_key}",
        "python3 scripts/lark_wiki.py graphify_insights",
        f"python3 scripts/lark_wiki.py graphify_candidates --namespace {namespace_key}",
        f"python3 scripts/lark_wiki.py graphify_query --query <text>",
        "python3 scripts/lark_wiki.py upgrade_preflight",
    ]
    result = {
        "namespace_key": namespace_key,
        "canonical_inventory": canonical_inventory,
        "derived_graph": derived_graph,
        "candidate_intake": candidate_intake,
        "transport_readiness": transport,
        "graphify_status": graphify_status_summary,
        "inventory": canonical_inventory,
        "insights": derived_graph["insights"],
        "candidates": candidate_intake["graphify_candidates"],
        "query": query_result,
        "recommended_commands": recommended,
    }
    if output_format == "md":
        lines = [
            f"# Agent Context: {namespace_key}",
            "",
            "## Canonical Inventory",
            "",
            f"- Pages: **{canonical_inventory['page_count']}**",
            f"- Generated reports: **{canonical_inventory['generated_report_count']}**",
            f"- Sources: **{canonical_inventory['source_count']}**",
            f"- Relations: **{canonical_inventory['relation_count']}**",
            f"- Issues: **{canonical_inventory['issue_count']}**",
            "",
            "## Read First",
            "",
        ]
        for item in canonical_inventory["entry_points"]:
            lines.append(f"- `{item['page_type']}` {item['title']} — {item['local_path']}")
        lines.extend(
            [
                "",
                "## Derived Graph",
                "",
                f"- Artifact state: `{graphify_status_summary.get('artifact_state')}`",
                f"- Mapped edges: **{graphify_status_summary.get('mapped_edge_count', 0)}**",
                f"- Unmapped nodes: **{graphify_status_summary.get('unmapped_node_count', 0)}**",
                f"- Ignored generated query nodes: **{graphify_status_summary.get('ignored_generated_node_count', 0)}**",
                f"- Insights: `{derived_graph['insights'].get('markdown_path')}`",
                "",
                "### Suggested Questions",
                "",
            ]
        )
        lines.extend(derived_graph["insights"]["suggested_questions"] or ["- None."])
        lines.extend(["", "## Candidate Intake", "", "### Graph Candidates", ""])
        for item in candidate_intake["graphify_candidates"]:
            lines.append(f"- **{item['label']}** | {item['source_file']} | {', '.join(item['why'])}")
        if not candidate_intake["graphify_candidates"]:
            lines.append("- None.")
        lines.extend(["", "### Paper Evidence Workbench", ""])
        paper = candidate_intake["paper_evidence_workbench"]
        lines.append(f"- Status: `{paper['status']}`")
        lines.append(f"- Drafts: **{paper['draft_count']}**")
        for item in paper["drafts"][:5]:
            lines.append(f"- **{item['title']}** | {item['source_file']} | {', '.join(item['signals'])}")
        lines.extend(
            [
                "",
                "## Transport Readiness",
                "",
                f"- lark-cli: `{'available' if transport['lark_cli_available'] else 'missing'}`",
                f"- Push policy: `{transport['sync_push_policy']}`",
            ]
        )
        result["markdown"] = "\n".join(lines).rstrip()
    return result


def _edge_layer_counts(graph_payload: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for edge in graph_payload.get("edges", []) if isinstance(graph_payload.get("edges", []), list) else []:
        if not isinstance(edge, dict):
            continue
        counts[str(edge.get("source_layer") or "missing")] += 1
    return dict(sorted(counts.items()))


def _sample_edges(graph_payload: dict[str, Any], source_layer: str, limit: int = 3) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for edge in graph_payload.get("edges", []) if isinstance(graph_payload.get("edges", []), list) else []:
        if not isinstance(edge, dict) or str(edge.get("source_layer") or "") != source_layer:
            continue
        selected.append(
            {
                "from": edge.get("from", ""),
                "to": edge.get("to", ""),
                "score": edge.get("score", 0),
                "reasons": edge.get("reasons", []),
                "graphify": edge.get("graphify", {}),
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _query_report_sections(config: AppConfig, report_page: str) -> dict[str, Any]:
    path = config.root / report_page
    text = read_text_safe(path)
    markers = {
        "has_direct_assets": "## 命中资产" in text,
        "has_direct_pages": "## 命中页面" in text,
        "has_graphify_related": "## Graphify 相关页面" in text,
        "has_synthesis_context": "## Synthesis Context" in text,
        "has_graphify_expanded_context": "### Graphify Expanded Page Context" in text,
    }
    excerpt_lines = []
    for line in text.splitlines():
        if line.startswith("## ") or line.startswith("### ") or "layer=graphify" in line or "layer=canonical" in line:
            excerpt_lines.append(line)
        if len(excerpt_lines) >= 16:
            break
    return {"path": report_page, **markers, "excerpt": excerpt_lines}


def fusion_demo(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str | None = None,
    query_text: str = "system",
) -> dict[str, Any]:
    namespace_key = namespace_key or config.default_project_namespace
    from .compiler.graph import build_graph
    from .inventory import inventory
    from .query import query

    import_result = graphify_import(conn, config)
    graph_result = build_graph(conn, config, namespace_key=namespace_key)
    insights = graphify_insights(conn, config, namespace_key=namespace_key, scope="repo", limit=8, write_files=True)
    candidates = graphify_candidates(conn, config, namespace_key=namespace_key, limit=12, min_degree=1, write_files=True)
    inventory_result = inventory(conn, config, namespace_key=namespace_key)
    query_result = query(conn, config, query_text, namespace_key=namespace_key)
    context = agent_context(conn, config, namespace_key=namespace_key, query_text=query_text, output_format="md")
    status = graphify_status(conn, config)

    graph_payload = _load_json(config.root / str(graph_result["graph_path"]))
    demo_dir = config.build_dir / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    suffix = namespace_key.replace("::", "_")
    markdown_path = demo_dir / f"fusion_demo_{suffix}.md"
    json_path = demo_dir / f"fusion_demo_{suffix}.json"
    query_report = _query_report_sections(config, str(query_result["report_page"]))
    edge_counts = _edge_layer_counts(graph_payload)
    top_issues = inventory_result.get("issues", [])[:8] if isinstance(inventory_result.get("issues", []), list) else []

    result: dict[str, Any] = {
        "status": "success",
        "namespace_key": namespace_key,
        "query": query_text,
        "artifacts": {
            "markdown_path": relative_to_root(markdown_path, config.root),
            "json_path": relative_to_root(json_path, config.root),
            "inventory_markdown_path": inventory_result.get("markdown_path", ""),
            "inventory_json_path": inventory_result.get("json_path", ""),
            "graph_path": graph_result.get("graph_path", ""),
            "graphify_insights_path": insights.get("markdown_path", ""),
            "graphify_candidates_path": candidates.get("markdown_path", ""),
            "query_report_path": query_result.get("report_page", ""),
            "agent_context_markdown": context.get("markdown", ""),
        },
        "canonical_inventory": {
            "page_count": inventory_result.get("page_count", 0),
            "generated_report_count": inventory_result.get("generated_report_count", 0),
            "source_count": inventory_result.get("source_count", 0),
            "relation_count": inventory_result.get("relation_count", 0),
            "issue_count": inventory_result.get("issue_count", 0),
            "entry_points": inventory_result.get("entry_points", [])[:6],
            "top_issues": top_issues,
        },
        "derived_graph": {
            "artifact_state": status.get("artifact_state"),
            "source_counts": {
                "nodes": status.get("source_node_count", 0),
                "edges": status.get("source_edge_count", 0),
                "hyperedges": status.get("source_hyperedge_count", 0),
            },
            "mapped_counts": {
                "nodes": status.get("mapped_node_count", 0),
                "edges": status.get("mapped_edge_count", 0),
                "unmapped_nodes": status.get("unmapped_node_count", 0),
            },
            "ignored_generated": {
                "nodes": status.get("ignored_generated_node_count", 0),
                "edges": status.get("ignored_generated_edge_count", 0),
                "hyperedges": status.get("ignored_generated_hyperedge_count", 0),
            },
            "official_refresh_command": status.get("official_refresh_command"),
            "graphify_update_command": status.get("graphify_update_command"),
            "insights_summary": {
                "node_count": insights.get("node_count", 0),
                "edge_count": insights.get("edge_count", 0),
                "hyperedge_count": insights.get("hyperedge_count", 0),
                "suggested_questions": insights.get("suggested_questions", [])[:3],
                "knowledge_gaps": insights.get("knowledge_gaps", [])[:3],
            },
        },
        "krm_merge": {
            "edge_layer_counts": edge_counts,
            "mixed_examples": _sample_edges(graph_payload, "mixed"),
            "graphify_examples": _sample_edges(graph_payload, "graphify"),
        },
        "candidate_intake": {
            "graphify_candidates": candidates.get("candidates", [])[:6],
            "paper_evidence_workbench": context.get("candidate_intake", {}).get("paper_evidence_workbench", {}),
        },
        "query_demo": {
            **query_result,
            "report": query_report,
            "graphify_query": context.get("derived_graph", {}).get("query", {}),
        },
        "transport_readiness": context.get("transport_readiness", {}),
        "command_sequence": [
            "python3 scripts/lark_wiki.py graphify_import",
            f"python3 scripts/lark_wiki.py build_graph --namespace {namespace_key}",
            "python3 scripts/lark_wiki.py graphify_insights",
            f"python3 scripts/lark_wiki.py graphify_candidates --namespace {namespace_key}",
            f"python3 scripts/lark_wiki.py inventory --namespace {namespace_key}",
            f"python3 scripts/lark_wiki.py query --namespace {namespace_key} --query {query_text}",
            f"python3 scripts/lark_wiki.py agent_context --namespace {namespace_key} --query {query_text}",
        ],
    }

    lines = [
        "# llm-wiki x Graphify x lark-cli x Paper Evidence Workbench Demo",
        "",
        f"- Namespace: `{namespace_key}`",
        f"- Query: `{query_text}`",
        f"- Status: `{result['status']}`",
        "",
        "## Command Sequence",
        "",
    ]
    lines.extend(f"- `{command}`" for command in result["command_sequence"])
    lines.extend(
        [
            "",
            "## Canonical Inventory",
            "",
            f"- Formal pages: **{result['canonical_inventory']['page_count']}**",
            f"- Generated query reports: **{result['canonical_inventory']['generated_report_count']}**",
            f"- Sources: **{result['canonical_inventory']['source_count']}**",
            f"- KRM relations: **{result['canonical_inventory']['relation_count']}**",
            f"- Open issues: **{result['canonical_inventory']['issue_count']}**",
            "",
            "### Read First",
            "",
        ]
    )
    for item in result["canonical_inventory"]["entry_points"]:
        lines.append(f"- `{item['page_type']}` {item['title']} | {item['local_path']}")
    lines.extend(["", "### Issues To Handle", ""])
    for item in top_issues:
        lines.append(f"- `{item.get('severity')}` `{item.get('issue_type')}` `{item.get('page_id', '')}` {item.get('detail', {})}")
    if not top_issues:
        lines.append("- None.")

    derived = result["derived_graph"]
    lines.extend(
        [
            "",
            "## Derived Graph",
            "",
            f"- Artifact state: `{derived['artifact_state']}`",
            f"- Raw official graph: **{derived['source_counts']['nodes']}** nodes / **{derived['source_counts']['edges']}** edges / **{derived['source_counts']['hyperedges']}** hyperedges",
            f"- Imported into KRM: **{derived['mapped_counts']['nodes']}** nodes / **{derived['mapped_counts']['edges']}** edges",
            f"- Ignored generated query nodes: **{derived['ignored_generated']['nodes']}**",
            f"- Official refresh: `{derived['official_refresh_command']}`",
            f"- Local update CLI: `{derived['graphify_update_command']}`",
            "",
            "### Suggested Questions",
            "",
        ]
    )
    lines.extend(derived["insights_summary"]["suggested_questions"] or ["- None."])
    lines.extend(["", "## KRM Merge", ""])
    lines.append(f"- Edge layers: `{json.dumps(edge_counts, ensure_ascii=False, sort_keys=True)}`")
    if result["krm_merge"]["mixed_examples"]:
        lines.extend(["", "### Mixed Examples", ""])
        for item in result["krm_merge"]["mixed_examples"]:
            lines.append(f"- `{item['from']}` -> `{item['to']}` | score={item['score']} | {', '.join(item.get('reasons', []))}")
    if result["krm_merge"]["graphify_examples"]:
        lines.extend(["", "### Graphify-Only Examples", ""])
        for item in result["krm_merge"]["graphify_examples"]:
            lines.append(f"- `{item['from']}` -> `{item['to']}` | score={item['score']} | {', '.join(item.get('reasons', []))}")

    lines.extend(["", "## Candidate Intake", "", "### Graph Candidates", ""])
    for item in result["candidate_intake"]["graphify_candidates"]:
        lines.append(f"- **{item['label']}** | degree={item['degree']} | {item['source_file']} | {'; '.join(item['why'])}")
    paper = result["candidate_intake"]["paper_evidence_workbench"]
    lines.extend(["", "### Paper Evidence Workbench", ""])
    lines.append(f"- Status: `{paper.get('status')}`")
    lines.append(f"- Drafts: **{paper.get('draft_count', 0)}**")
    for item in paper.get("drafts", [])[:5]:
        lines.append(f"- **{item['title']}** | {item['source_file']} | {', '.join(item['signals'])}")

    report = result["query_demo"]["report"]
    lines.extend(
        [
            "",
            "## Query Demo",
            "",
            f"- Report: `{report['path']}`",
            f"- Direct assets: **{result['query_demo']['match_count']}**",
            f"- Direct pages: **{result['query_demo']['page_match_count']}**",
            f"- Graphify related pages: **{result['query_demo']['graphify_related_count']}**",
            f"- Has synthesis context: `{report['has_synthesis_context']}`",
            "",
            "### Query Report Shape",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in report["excerpt"])

    transport = result["transport_readiness"]
    lines.extend(
        [
            "",
            "## Transport Readiness",
            "",
            f"- lark-cli available: `{transport.get('lark_cli_available')}`",
            f"- lark-cli path: `{transport.get('lark_cli_path', '')}`",
            f"- sync_push policy: `{transport.get('sync_push_policy')}`",
            f"- sync_pull policy: `{transport.get('sync_pull_policy')}`",
            "",
            "## Artifact Paths",
            "",
        ]
    )
    for key, value in result["artifacts"].items():
        if key == "agent_context_markdown":
            continue
        lines.append(f"- `{key}`: `{value}`")

    markdown = "\n".join(lines).rstrip() + "\n"
    result["artifacts"]["markdown_path"] = relative_to_root(markdown_path, config.root)
    result["artifacts"]["json_path"] = relative_to_root(json_path, config.root)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_dumps(result), encoding="utf-8")
    return result
