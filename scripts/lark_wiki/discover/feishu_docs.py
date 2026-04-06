from __future__ import annotations

from typing import Any
import sqlite3

from ..config import AppConfig
from ..db import record_issue, upsert_asset, upsert_asset_edge
from ..lark_cli import detect_doc_token, docs_fetch_full, search_docs, wiki_get_node, wiki_list_children, wiki_list_spaces
from ..utils import json_dumps, now_iso, relative_to_root, scan_local_text_urls, sha256_text


def crawl_wiki_subtree(config: AppConfig, seed_node_token: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    queue: list[str] = [seed_node_token]
    nodes: list[dict[str, Any]] = []
    while queue:
        token = queue.pop(0)
        if token in seen:
            continue
        seen.add(token)
        node = wiki_get_node(config, token)
        if not node:
            continue
        nodes.append(node)
        space_id = node.get("space_id", "")
        if not space_id:
            continue
        for child in wiki_list_children(config, space_id, token):
            child_token = child.get("node_token", "")
            if child_token and child_token not in seen:
                queue.append(child_token)
    return nodes


def discover_feishu_docs(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    discovered_urls = scan_local_text_urls(config)
    seed_nodes: dict[str, set[str]] = {}
    doc_refs: dict[str, set[str]] = {}
    online_docs: list[dict[str, str]] = []
    doc_search_queries: dict[str, set[str]] = {}

    if config.portfolio_root_node:
        seed_nodes.setdefault(config.portfolio_root_node, set()).add(config.account_namespace_key)

    for namespace_key, namespace in config.namespaces.items():
        for seed in namespace.wiki_seed_nodes:
            seed_nodes.setdefault(seed, set()).add(namespace_key)
        for keyword in namespace.title_keywords:
            doc_search_queries.setdefault(keyword, set()).add(namespace_key)

    for url in discovered_urls:
        doc_type, token = detect_doc_token(url)
        if doc_type == "wiki" and token:
            seed_nodes.setdefault(token, set()).add(config.inbox_namespace_key)
        elif doc_type and token:
            doc_refs.setdefault(url, set()).add(config.inbox_namespace_key)

    for query in sorted(filter(None, doc_search_queries)):
        try:
            for item in search_docs(config, query):
                url = str(item.get("url", "") or item.get("obj_url", "") or "")
                if not url:
                    continue
                doc_type, token = detect_doc_token(url)
                if doc_type == "wiki" and token:
                    seed_nodes.setdefault(token, set()).update(doc_search_queries.get(query, {config.inbox_namespace_key}))
                elif doc_type and token:
                    doc_refs.setdefault(url, set()).update(doc_search_queries.get(query, {config.inbox_namespace_key}))
        except Exception as exc:  # pragma: no cover
            record_issue(conn, issue_type="remote_search_failed", severity="medium", namespace_key=config.account_namespace_key, detail={"query": query, "error": str(exc)})

    try:
        spaces = wiki_list_spaces(config)
    except Exception:
        spaces = []

    deduped_nodes: dict[str, dict[str, Any]] = {}
    node_candidates: dict[str, set[str]] = {}
    for seed, candidates in sorted(((seed, candidates) for seed, candidates in seed_nodes.items() if seed), key=lambda item: item[0]):
        for node in crawl_wiki_subtree(config, seed):
            node_token = node.get("node_token", "")
            if not node_token:
                continue
            deduped_nodes[node_token] = node
            node_candidates.setdefault(node_token, set()).update(candidates)

    for node_token, node in deduped_nodes.items():
        obj_token = node.get("obj_token", "")
        obj_type = node.get("obj_type", "")
        if obj_token and obj_type in {"docx", "slides"}:
            doc_refs.setdefault(f"https://example.invalid/{obj_type}/{obj_token}", set()).update(
                node_candidates.get(node_token, {config.inbox_namespace_key})
            )

    for node in sorted(deduped_nodes.values(), key=lambda item: item.get("title", "")):
        node_token = node.get("node_token", "")
        candidate_namespaces = sorted(node_candidates.get(node_token, {config.inbox_namespace_key}))
        namespace_key = candidate_namespaces[0] if len(candidate_namespaces) == 1 else config.inbox_namespace_key
        classification_status = "classified" if len(candidate_namespaces) == 1 else "inbox"
        obj_type = node.get("obj_type", "")
        obj_token = node.get("obj_token", "")
        title = node.get("title", "")
        node_url = f"https://example.invalid/wiki/{node_token}" if node_token else ""
        node_key = f"WIKI_NODE::{node_token}"
        node_hash = sha256_text(json_dumps(node))
        upsert_asset(
            conn,
            asset_key=node_key,
            asset_class="wiki_node",
            title=title,
            remote_url=node_url,
            remote_id=node_token,
            upstream_system="feishu_wiki",
            source_hash=node_hash,
            canonical_role="remote_source",
            sync_mode="remote_snapshot",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status=classification_status,
            metadata={**node, "candidate_namespaces": candidate_namespaces},
        )
        if obj_token:
            doc_asset_class = "wiki_doc" if obj_type == "docx" else "online_doc"
            doc_url = f"https://example.invalid/{obj_type}/{obj_token}"
            upsert_asset(
                conn,
                asset_key=f"DOC::{obj_token}",
                asset_class=doc_asset_class,
                title=title,
                remote_url=doc_url,
                remote_id=obj_token,
                upstream_system=f"feishu_{obj_type}",
                source_hash=node_hash,
                canonical_role="remote_source",
                sync_mode="bidirectional_markdown_safe" if obj_type == "docx" else "remote_snapshot",
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                classification_status=classification_status,
                metadata={**node, "candidate_namespaces": candidate_namespaces},
            )
            upsert_asset_edge(conn, node_key, f"DOC::{obj_token}", "wraps_document", {"obj_type": obj_type})

    for doc_ref in sorted(doc_refs):
        try:
            fetched = docs_fetch_full(config, doc_ref)
        except Exception as exc:  # pragma: no cover - remote failures are environment-dependent
            record_issue(conn, issue_type="remote_fetch_failed", severity="medium", namespace_key=config.account_namespace_key, detail={"doc_ref": doc_ref, "error": str(exc)})
            continue
        doc_id = fetched.get("doc_id", "") or detect_doc_token(doc_ref)[1]
        if not doc_id:
            continue
        snapshot_path = config.raw_dir / "feishu_docs" / f"{doc_id}.json"
        snapshot_path.write_text(
            json_dumps(
                {
                    "doc_ref": doc_ref,
                    "doc_id": doc_id,
                    "title": fetched.get("title", ""),
                    "markdown": fetched.get("markdown", ""),
                    "fetched_at": now_iso(),
                }
            ),
            encoding="utf-8",
        )
        upsert_asset(
            conn,
            asset_key=f"DOC::{doc_id}",
            asset_class="wiki_doc" if "/docx/" in doc_ref or doc_ref.startswith("DOC::") else "online_doc",
            title=fetched.get("title", "") or doc_id,
            local_path=relative_to_root(snapshot_path, config.root),
            remote_url=doc_ref,
            remote_id=doc_id,
            upstream_system="feishu_docs",
            source_hash=sha256_text(fetched.get("markdown", "")),
            canonical_role="remote_source",
            sync_mode="bidirectional_markdown_safe" if "/docx/" in doc_ref else "remote_snapshot",
            portfolio_key=config.portfolio_key,
            namespace_key=sorted(doc_refs.get(doc_ref, {config.inbox_namespace_key}))[0] if len(doc_refs.get(doc_ref, {config.inbox_namespace_key})) == 1 else config.inbox_namespace_key,
            classification_status="classified" if len(doc_refs.get(doc_ref, {config.inbox_namespace_key})) == 1 else "inbox",
            metadata={
                "title": fetched.get("title", ""),
                "doc_ref": doc_ref,
                "candidate_namespaces": sorted(doc_refs.get(doc_ref, {config.inbox_namespace_key})),
            },
        )
        online_docs.append({"doc_id": doc_id, "title": fetched.get("title", ""), "doc_ref": doc_ref})

    summary = {
        "wiki_nodes": len(deduped_nodes),
        "docs_snapshotted": len(online_docs),
        "doc_refs": sorted(doc_refs),
        "seed_nodes": sorted(seed_nodes),
        "wiki_spaces": len(spaces),
    }
    snapshot_path = config.raw_dir / "feishu_docs" / "discovery_summary.json"
    snapshot_path.write_text(json_dumps(summary), encoding="utf-8")
    upsert_asset(
        conn,
        asset_key="STATE::feishu_docs_discovery",
        asset_class="state_snapshot",
        title="飞书文档发现快照",
        local_path=relative_to_root(snapshot_path, config.root),
        upstream_system="feishu_docs",
        source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
        canonical_role="state_snapshot",
        sync_mode="local_only",
        portfolio_key=config.portfolio_key,
        namespace_key=config.account_namespace_key,
        metadata=summary,
    )
    conn.commit()
    return summary
