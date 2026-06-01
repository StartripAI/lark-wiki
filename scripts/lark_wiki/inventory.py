from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .config import AppConfig
from .graphify import graphify_import_summary, graphify_insights_summary, load_graphify_enrichment
from .markdown import read_frontmatter
from .portfolio import namespace_display_name, namespace_root_dir
from .utils import json_dumps, relative_to_root, sha256_text


DIRECT_LINK_SCORE = 10.0
SHARED_SOURCE_BASE_SCORE = 6.0
SHARED_SOURCE_EXTRA_SCORE = 1.0
SHARED_SOURCE_EXTRA_CAP = 3
COMMON_NEIGHBOR_SCORE = 1.5
SAME_NAMESPACE_SCORE = 0.5
TYPE_PAIR_SCORE = 0.25
EMPTY_BODY_LIMIT = 40

STRUCTURAL_PAGE_TYPES = {"Home", "Index", "Log"}
DEMO_MARKERS = ("starter", "placeholder", "synthetic", "example.invalid")
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
REASON_ORDER = {
    "direct_link": 0,
    "shared_source": 1,
    "common_neighbor": 2,
    "same_namespace": 3,
    "page_type_pair": 4,
    "graphify": 5,
}


@dataclass(frozen=True)
class PageRecord:
    page_id: str
    title: str
    page_type: str
    namespace_key: str
    local_path: str
    body: str
    source_ids: tuple[str, ...]
    links_to: tuple[str, ...]
    registered: bool
    generated_report: bool


def _is_generated_query_page(page_id: str, local_path: str) -> bool:
    normalised = local_path.replace("\\", "/")
    return "::query-" in page_id or "/reports/query-" in normalised or Path(normalised).name.startswith("query-")


def _as_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    seen: set[str] = set()
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return tuple(items)


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _merge_graphify_provenance(edge: dict[str, object], graphify: dict[str, object]) -> None:
    existing = edge.get("graphify_edges")
    provenances = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    if graphify not in provenances:
        provenances.append(graphify)
    edge["graphify_edges"] = provenances
    edge["graphify"] = max(provenances, key=lambda item: _as_float(item.get("confidence_score"), 0.0))


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


def _namespace_keys(config: AppConfig, namespace_key: str = "") -> list[str]:
    if namespace_key:
        if namespace_key not in config.namespaces:
            raise RuntimeError(f"Unknown namespace: {namespace_key}")
        return [namespace_key]
    keys = [config.account_namespace_key]
    keys.extend(key for key in sorted(config.namespaces) if key != config.account_namespace_key)
    return keys


def _safe_read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    try:
        return read_frontmatter(path)
    except (json.JSONDecodeError, ValueError):
        return {}, path.read_text(encoding="utf-8", errors="ignore")


def _registered_pages(conn: sqlite3.Connection, namespace_key: str) -> set[str]:
    return {
        str(row["page_id"])
        for row in conn.execute("SELECT page_id FROM pages WHERE namespace_key = ?", (namespace_key,)).fetchall()
    }


def _scan_pages(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> list[PageRecord]:
    root = namespace_root_dir(config, namespace_key)
    registered = _registered_pages(conn, namespace_key)
    pages: list[PageRecord] = []
    if not root.exists():
        return pages
    for path in sorted(root.rglob("*.md")):
        frontmatter, body = _safe_read_frontmatter(path)
        page_id = str(frontmatter.get("page_id") or relative_to_root(path, config.wiki_src_dir).removesuffix(".md").replace("/", "::"))
        title = str(frontmatter.get("title") or path.stem.replace("_", " ").replace("-", " ").title())
        page_type = str(frontmatter.get("page_type") or "Page")
        page_namespace = str(frontmatter.get("namespace_key") or namespace_key)
        pages.append(
            PageRecord(
                page_id=page_id,
                title=title,
                page_type=page_type,
                namespace_key=page_namespace,
                local_path=relative_to_root(path, config.root),
                body=body,
                source_ids=_as_string_list(frontmatter.get("source_ids", [])),
                links_to=_as_string_list(frontmatter.get("links_to", [])),
                registered=page_id in registered,
                generated_report=_is_generated_query_page(page_id, relative_to_root(path, config.root)),
            )
        )
    return pages


def _reason_sort_key(reason: str) -> tuple[int, str]:
    prefix = reason.split(":", 1)[0]
    return REASON_ORDER.get(prefix, 99), reason


def _edge(from_page: str, to_page: str, score: float, reasons: list[str]) -> dict[str, object]:
    return {
        "from": from_page,
        "to": to_page,
        "score": round(score, 3),
        "reasons": sorted(reasons, key=_reason_sort_key),
        "source_layer": "canonical",
    }


def _neighbors(pages: list[PageRecord]) -> dict[str, set[str]]:
    ids = {page.page_id for page in pages if not page.generated_report}
    neighbors: dict[str, set[str]] = {page.page_id: set() for page in pages}
    for page in pages:
        if page.generated_report:
            continue
        for linked in page.links_to:
            if linked in ids and linked != page.page_id:
                neighbors[page.page_id].add(linked)
                neighbors[linked].add(page.page_id)
    return neighbors


def _relation_edges(pages: list[PageRecord]) -> list[dict[str, object]]:
    relation_pages = [page for page in pages if not page.generated_report]
    page_ids = {page.page_id for page in relation_pages}
    neighbor_map = _neighbors(relation_pages)
    edge_scores: dict[tuple[str, str], float] = defaultdict(float)
    edge_reasons: dict[tuple[str, str], set[str]] = defaultdict(set)

    for page in relation_pages:
        for linked in page.links_to:
            if linked not in page_ids or linked == page.page_id:
                continue
            key = (page.page_id, linked)
            edge_scores[key] += DIRECT_LINK_SCORE
            edge_reasons[key].add("direct_link")

    for i, left in enumerate(relation_pages):
        for right in relation_pages[i + 1 :]:
            shared_sources = sorted(set(left.source_ids).intersection(right.source_ids))
            common_neighbors = sorted(neighbor_map[left.page_id].intersection(neighbor_map[right.page_id]))
            weak_score = 0.0
            weak_reasons: list[str] = []
            if shared_sources:
                extra = min(max(len(shared_sources) - 1, 0), SHARED_SOURCE_EXTRA_CAP)
                weak_score += SHARED_SOURCE_BASE_SCORE + extra * SHARED_SOURCE_EXTRA_SCORE
                weak_reasons.append("shared_source")
                weak_reasons.append(f"shared_source:{len(shared_sources)}")
            if common_neighbors:
                weak_score += COMMON_NEIGHBOR_SCORE * len(common_neighbors)
                weak_reasons.append(f"common_neighbor:{len(common_neighbors)}")
            if left.namespace_key == right.namespace_key:
                weak_score += SAME_NAMESPACE_SCORE
                weak_reasons.append("same_namespace")
            if left.page_type and left.page_type == right.page_type:
                weak_score += TYPE_PAIR_SCORE
                if not shared_sources and not common_neighbors:
                    weak_reasons.append("same_page_type")
                weak_reasons.append(f"page_type_pair:{left.page_type}:{right.page_type}")
            if weak_score <= 0:
                continue
            key = tuple(sorted((left.page_id, right.page_id)))
            if key[0] == key[1]:
                continue
            edge_scores[key] += weak_score
            edge_reasons[key].update(weak_reasons)

    edges = [_edge(src, dst, edge_scores[(src, dst)], list(edge_reasons[(src, dst)])) for src, dst in edge_scores]
    return sorted(edges, key=lambda item: (-float(item["score"]), str(item["from"]), str(item["to"])))


def _merge_external_edges(
    edges: list[dict[str, object]],
    external_edges: list[dict[str, object]],
) -> list[dict[str, object]]:
    edge_map: dict[tuple[str, str], dict[str, object]] = {
        (str(edge.get("from", "")), str(edge.get("to", ""))): dict(edge)
        for edge in edges
    }
    for raw_edge in external_edges:
        if not isinstance(raw_edge, dict):
            continue
        from_page = str(raw_edge.get("from", ""))
        to_page = str(raw_edge.get("to", ""))
        if not from_page or not to_page or from_page == to_page:
            continue
        key = (from_page, to_page)
        edge = edge_map.get(key)
        created = edge is None
        if edge is None:
            edge = {"from": from_page, "to": to_page, "score": 0.0, "reasons": [], "source_layer": "graphify"}
            edge_map[key] = edge
        try:
            incoming_score = float(raw_edge.get("score", 0.0))
        except (TypeError, ValueError):
            incoming_score = 0.0
        try:
            existing_score = float(edge.get("score", 0.0))
        except (TypeError, ValueError):
            existing_score = 0.0
        edge["score"] = round(max(existing_score, incoming_score), 3)
        reasons = set(_as_string_list(edge.get("reasons", [])))
        reasons.update(_as_string_list(raw_edge.get("reasons", [])))
        edge["reasons"] = sorted(reasons, key=_reason_sort_key)
        graphify = raw_edge.get("graphify")
        incoming_graphify = isinstance(graphify, dict) or _has_graphify_reason(raw_edge.get("reasons", []))
        if isinstance(graphify, dict):
            _merge_graphify_provenance(edge, graphify)
        _merge_source_layer(
            edge,
            raw_edge.get("source_layer") or ("graphify" if created else edge.get("source_layer")),
            incoming_graphify=incoming_graphify,
        )
    return sorted(edge_map.values(), key=lambda item: (-float(item["score"]), str(item["from"]), str(item["to"])))


def _counts(edges: list[dict[str, object]]) -> tuple[Counter[str], Counter[str]]:
    inbound: Counter[str] = Counter()
    outbound: Counter[str] = Counter()
    for edge in edges:
        src = str(edge["from"])
        dst = str(edge["to"])
        outbound[src] += 1
        inbound[dst] += 1
    return inbound, outbound


def _body_text(body: str) -> str:
    return re.sub(r"\s+", " ", body).strip()


def _issue(issue_type: str, severity: str, page_id: str = "", detail: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "page_id": page_id,
        "detail": detail or {},
    }


def _detect_issues(
    config: AppConfig,
    namespace_key: str,
    pages: list[PageRecord],
    edges: list[dict[str, object]],
) -> list[dict[str, object]]:
    page_ids = {page.page_id for page in pages}
    inbound, outbound = _counts(edges)
    issues: list[dict[str, object]] = []
    graph_path = config.build_dir / f"graph_{namespace_key.replace('::', '_')}.json"
    if not graph_path.exists():
        issues.append(_issue("missing_graph_manifest", "low", detail={"expected_path": relative_to_root(graph_path, config.root)}))
    for page in pages:
        if page.generated_report:
            continue
        body_text = _body_text(page.body)
        if len(body_text) < EMPTY_BODY_LIMIT:
            issues.append(_issue("empty_page", "medium", page.page_id, {"local_path": page.local_path, "body_size": len(body_text)}))
        if not page.registered:
            issues.append(_issue("unregistered_page", "medium", page.page_id, {"local_path": page.local_path}))
        for linked in page.links_to:
            if linked not in page_ids:
                issues.append(_issue("broken_link", "high", page.page_id, {"linked_page_id": linked, "local_path": page.local_path}))
        if (
            page.page_type not in STRUCTURAL_PAGE_TYPES
            and inbound[page.page_id] == 0
            and outbound[page.page_id] == 0
        ):
            issues.append(_issue("orphan_page", "medium", page.page_id, {"local_path": page.local_path}))
        lower = f"{page.title}\n{page.body}".lower()
        if page.page_type not in STRUCTURAL_PAGE_TYPES and any(marker in lower for marker in DEMO_MARKERS):
            issues.append(_issue("demo_content", "low", page.page_id, {"local_path": page.local_path}))
    return sorted(
        issues,
        key=lambda item: (
            SEVERITY_RANK.get(str(item["severity"]), 99),
            str(item["issue_type"]),
            str(item["page_id"]),
            json.dumps(item["detail"], ensure_ascii=False, sort_keys=True),
        ),
    )


def _nodes(pages: list[PageRecord], edges: list[dict[str, object]]) -> list[dict[str, object]]:
    inbound, outbound = _counts(edges)
    nodes = [
        {
            "page_id": page.page_id,
            "title": page.title,
            "page_type": page.page_type,
            "namespace_key": page.namespace_key,
            "local_path": page.local_path,
            "body_size": len(page.body),
            "source_count": len(page.source_ids),
            "source_ids": list(page.source_ids),
            "links_to": list(page.links_to),
            "inbound_count": inbound[page.page_id],
            "outbound_count": outbound[page.page_id],
            "registered": page.registered,
            "generated_report": page.generated_report,
        }
        for page in pages
    ]
    return sorted(nodes, key=lambda node: (str(node["page_type"]), str(node["title"]), str(node["page_id"])))


def _rrf_rank(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for index, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + index)
    return scores


def _entry_points(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    candidate_nodes = [node for node in nodes if not node.get("generated_report")]
    if not candidate_nodes:
        return []
    by_title = sorted(candidate_nodes, key=lambda node: str(node["title"]).lower())
    by_inbound = sorted(candidate_nodes, key=lambda node: (-int(node["inbound_count"]), str(node["title"])))
    by_sources = sorted(candidate_nodes, key=lambda node: (-int(node["source_count"]), str(node["title"])))
    by_body = sorted(candidate_nodes, key=lambda node: (-int(node["body_size"]), str(node["title"])))
    type_priority = {"Home": 0, "Index": 1, "Report": 2, "Concept": 3, "Entity": 4, "Source": 5, "Log": 8}
    by_type = sorted(candidate_nodes, key=lambda node: (type_priority.get(str(node["page_type"]), 7), str(node["title"])))
    scores = _rrf_rank(
        [[str(node["page_id"]) for node in ranking] for ranking in [by_type, by_inbound, by_sources, by_body, by_title]]
    )
    selected = sorted(candidate_nodes, key=lambda node: (-scores[str(node["page_id"])], str(node["title"])))[:8]
    return [
        {
            "page_id": str(node["page_id"]),
            "title": str(node["title"]),
            "page_type": str(node["page_type"]),
            "score": round(scores[str(node["page_id"])], 6),
            "local_path": str(node["local_path"]),
        }
        for node in selected
    ]


def _source_count(pages: list[PageRecord]) -> int:
    sources: set[str] = set()
    for page in pages:
        if page.generated_report:
            continue
        sources.update(page.source_ids)
    return len(sources)


def build_relation_inventory(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> dict[str, object]:
    pages = _scan_pages(conn, config, namespace_key)
    edges = _relation_edges(pages)
    graphify = load_graphify_enrichment(conn, config, namespace_key=namespace_key)
    graphify_edges = graphify.get("edges", [])
    if isinstance(graphify_edges, list) and graphify_edges:
        edges = _merge_external_edges(edges, graphify_edges)
    nodes = _nodes(pages, edges)
    issues = _detect_issues(config, namespace_key, pages, edges)
    graphify_summary = graphify.get("summary") if isinstance(graphify, dict) else None
    return {
        "namespace_key": namespace_key,
        "display_name": namespace_display_name(config, namespace_key),
        "page_count": len(nodes),
        "generated_report_count": sum(1 for page in pages if page.generated_report),
        "source_count": _source_count(pages),
        "relation_count": len(edges),
        "issue_count": len(issues),
        "entry_points": _entry_points(nodes),
        "issues": issues,
        "nodes": nodes,
        "edges": edges,
        "graphify": graphify_summary if isinstance(graphify_summary, dict) else graphify_import_summary(config),
        "graphify_insights": graphify_insights_summary(config),
    }


def _markdown_for_namespace(summary: dict[str, object]) -> str:
    lines = [
        f"## {summary['display_name']} (`{summary['namespace_key']}`)",
        "",
        f"- 页面：**{summary['page_count']}**",
        f"- 生成报告：**{summary.get('generated_report_count', 0)}**",
        f"- 来源：**{summary['source_count']}**",
        f"- 关系：**{summary['relation_count']}**",
        f"- 需要处理：**{summary['issue_count']}**",
        "",
        "### 先看这些",
        "",
    ]
    entry_points = summary.get("entry_points", []) or []
    if entry_points:
        for item in entry_points:
            lines.append(f"- `{item['page_type']}` [{item['title']}]({item['local_path']})")
    else:
        lines.append("- 暂时没有页面。")
    lines.extend(["", "### 关系线索", ""])
    edges = summary.get("edges", []) or []
    if edges:
        for edge in edges[:10]:
            reasons = ", ".join(str(reason) for reason in edge.get("reasons", []))
            lines.append(f"- `{edge['from']}` → `{edge['to']}` | score={edge['score']} | {reasons}")
    else:
        lines.append("- 暂时没有可解释的页面关系。")
    lines.extend(["", "### 需要处理", ""])
    issues = summary.get("issues", []) or []
    if issues:
        for issue in issues[:20]:
            page_id = f"`{issue.get('page_id')}` " if issue.get("page_id") else ""
            lines.append(f"- `{issue['severity']}` `{issue['issue_type']}` {page_id}{json.dumps(issue.get('detail', {}), ensure_ascii=False, sort_keys=True)}")
    else:
        lines.append("- 暂时没有明显问题。")
    graphify = summary.get("graphify", {}) if isinstance(summary.get("graphify", {}), dict) else {}
    lines.extend(["", "### Graphify", ""])
    lines.append(f"- 状态：`{graphify.get('status', 'unknown')}`")
    lines.append(f"- 官方图：`{graphify.get('source_graph_path', 'graphify-out/graph.json')}`")
    lines.append(f"- 镜像图：`{graphify.get('mirror_graph_path', 'knowledge/build/graphify/repo/graph.json')}`")
    lines.append(f"- 映射节点：**{graphify.get('mapped_node_count', 0)}**")
    lines.append(f"- 导入关系：**{graphify.get('mapped_edge_count', 0)}**")
    lines.append(f"- 未映射节点：**{graphify.get('unmapped_node_count', 0)}**")
    lines.append(f"- 忽略关系：**{graphify.get('ignored_edge_count', 0)}**")
    if graphify.get("artifact_state"):
        lines.append(f"- 刷新状态：`{graphify.get('artifact_state')}`")
    insights = summary.get("graphify_insights", {}) if isinstance(summary.get("graphify_insights", {}), dict) else {}
    if insights:
        lines.append(f"- 关系洞察：`{insights.get('markdown_path', 'knowledge/build/graphify/insights.md')}`")
        questions = insights.get("suggested_questions", []) or []
        if questions:
            lines.extend(["", "#### Graphify 建议追问", ""])
            for question in questions[:3]:
                lines.append(f"- {question}")
    return "\n".join(lines).rstrip()


def _write_outputs(config: AppConfig, namespace_key: str, payload: dict[str, object]) -> tuple[str, str]:
    config.build_dir.mkdir(parents=True, exist_ok=True)
    suffix = "all" if not namespace_key else namespace_key.replace("::", "_")
    markdown_path = config.build_dir / f"inventory_{suffix}.md"
    json_path = config.build_dir / f"inventory_{suffix}.json"
    payload["markdown_path"] = relative_to_root(markdown_path, config.root)
    payload["json_path"] = relative_to_root(json_path, config.root)
    payload["source_hash"] = sha256_text(json_dumps(payload))
    lines = ["# Knowledge Inventory", ""]
    for summary in payload["namespaces"]:
        lines.append(_markdown_for_namespace(summary))
        lines.append("")
    markdown = "\n".join(lines).rstrip() + "\n"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_dumps(payload), encoding="utf-8")
    return str(payload["markdown_path"]), str(payload["json_path"])


def inventory(conn: sqlite3.Connection, config: AppConfig, namespace_key: str = "") -> dict[str, object]:
    summaries = [build_relation_inventory(conn, config, key) for key in _namespace_keys(config, namespace_key)]
    payload: dict[str, object] = {
        "namespaces": summaries,
        "namespace_count": len(summaries),
        "page_count": sum(int(summary["page_count"]) for summary in summaries),
        "relation_count": sum(int(summary["relation_count"]) for summary in summaries),
        "issue_count": sum(int(summary["issue_count"]) for summary in summaries),
    }
    if namespace_key and summaries:
        payload.update(summaries[0])
    _write_outputs(config, namespace_key, payload)
    return payload
