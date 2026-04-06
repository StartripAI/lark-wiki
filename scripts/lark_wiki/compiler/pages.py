from __future__ import annotations

import csv
import sqlite3
import textwrap
from pathlib import Path

from ..config import AppConfig
from ..db import upsert_asset, upsert_page
from ..llm_compile import compile_page_markdown
from ..markdown import write_canonical_page
from ..portfolio import namespace_root_relpath, namespaced_page_id, page_asset_key
from ..utils import relative_to_root, sha256_text


def master_rows(config: AppConfig) -> list[dict[str, str]]:
    if not config.master_csv_path or not config.master_csv_path.exists():
        return []
    with config.master_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _existing_source_ids(conn: sqlite3.Connection, candidates: list[str]) -> list[str]:
    return [asset_key for asset_key in candidates if asset_key and conn.execute("SELECT 1 FROM assets WHERE asset_key = ?", (asset_key,)).fetchone()]


def _count_assets(conn: sqlite3.Connection, namespace_key: str, clause: str = "", params: tuple[object, ...] = ()) -> int:
    where = "WHERE namespace_key = ?"
    if clause:
        where = f"{where} AND {clause}"
    row = conn.execute(f"SELECT COUNT(*) FROM assets {where}", (namespace_key, *params)).fetchone()
    return int(row[0] or 0)


def _write_namespace_page(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    short_id: str,
    title: str,
    page_type: str,
    rel_path: Path,
    source_ids: list[str],
    links_to: list[str],
    body: str,
) -> str:
    page_id = namespaced_page_id(namespace_key, short_id)
    asset_key = page_asset_key(namespace_key, short_id)
    text = write_canonical_page(
        config.wiki_src_dir,
        page_id,
        title,
        page_type,
        rel_path,
        asset_key,
        source_ids,
        links_to,
        body,
        namespace_key=namespace_key,
        portfolio_key=config.portfolio_key,
    )
    full_path = config.wiki_src_dir / rel_path
    upsert_asset(
        conn,
        asset_key=asset_key,
        asset_class="local_file",
        title=title,
        local_path=relative_to_root(full_path, config.root),
        upstream_system="llm_wiki_compiler",
        source_hash=sha256_text(text),
        canonical_role="canonical_page",
        sync_mode="bidirectional_markdown_safe",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        metadata={"page_type": page_type, "page_id": page_id},
    )
    upsert_page(
        conn,
        page_id=page_id,
        page_type=page_type,
        asset_key=asset_key,
        local_path=relative_to_root(full_path, config.root),
        last_local_hash=sha256_text(text),
        sync_mode="bidirectional_markdown_safe",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        metadata={"title": title},
    )
    return relative_to_root(full_path, config.root)


def _namespace_relpath(config: AppConfig, namespace_key: str, relative_path: str) -> Path:
    return Path(namespace_root_relpath(config, namespace_key)) / relative_path


def _maybe_append_llm_synthesis(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    short_id: str,
    title: str,
    page_type: str,
    body: str,
    source_ids: list[str],
) -> str:
    llm_priority_pages = {
        "agent-ops-catalog",
        "agent-system-map",
        "execution-readiness-report",
        "handoff-risks-report",
    }
    if short_id not in llm_priority_pages or page_type not in {"Entity", "Concept", "Report"} or not source_ids:
        return body
    compiled = compile_page_markdown(
        conn,
        config,
        namespace_key=namespace_key,
        title=title,
        page_type=page_type,
        base_body=body,
        source_ids=source_ids,
    ).strip()
    if not compiled:
        return body
    return f"{body.rstrip()}\n\n## LLM Synthesis\n\n{compiled}\n"


def _ingest_account(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    namespace_key = config.account_namespace_key
    namespace_rows = conn.execute(
        """
        SELECT namespace_key, display_name, kind, slug, root_local_path
        FROM namespaces
        WHERE namespace_key != ?
        ORDER BY kind, namespace_key
        """,
        (config.account_namespace_key,),
    ).fetchall()
    home_lines = [
        f"# {config.portfolio_root_title}",
        "",
        "本仓库把本地 Markdown、Lark/Feishu 文档、Base 和项目状态编成一个 local-first knowledge compiler。",
        "",
        "## Namespace Snapshot",
        "",
    ]
    for row in namespace_rows:
        asset_count = _count_assets(conn, row["namespace_key"])
        page_count = int(conn.execute("SELECT COUNT(*) FROM pages WHERE namespace_key = ?", (row["namespace_key"],)).fetchone()[0])
        home_lines.append(f"- `{row['namespace_key']}` {row['display_name']} | assets={asset_count} | pages={page_count}")

    index_lines = ["# Portfolio Index", "", "## Namespaces", ""]
    for row in namespace_rows:
        root = row["root_local_path"] or namespace_root_relpath(config, row["namespace_key"])
        index_lines.append(f"- `{row['kind']}` [{row['display_name']}]({root}/00_Home.md)")

    log_lines = [
        "# Portfolio Run Log",
        "",
        f"- assets: **{conn.execute('SELECT COUNT(*) FROM assets').fetchone()[0]}**",
        f"- pages: **{conn.execute('SELECT COUNT(*) FROM pages').fetchone()[0]}**",
        f"- namespaces: **{len(namespace_rows) + 1}**",
    ]

    generated = [
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="home",
            title=config.portfolio_root_title,
            page_type="Home",
            rel_path=_namespace_relpath(config, namespace_key, "00_Home.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "index"), namespaced_page_id(namespace_key, "log")],
            body="\n".join(home_lines),
        ),
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="index",
            title="Portfolio Index",
            page_type="Index",
            rel_path=_namespace_relpath(config, namespace_key, "01_Index.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "home"), namespaced_page_id(namespace_key, "log")],
            body="\n".join(index_lines),
        ),
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="log",
            title="Portfolio Run Log",
            page_type="Log",
            rel_path=_namespace_relpath(config, namespace_key, "02_Log.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "home"), namespaced_page_id(namespace_key, "index")],
            body="\n".join(log_lines),
        ),
    ]
    conn.commit()
    return {"generated_pages": generated, "page_count": len(generated), "namespace_key": namespace_key}


def _ingest_generic_namespace(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> dict[str, object]:
    namespace = config.namespaces[namespace_key]
    asset_count = _count_assets(conn, namespace_key)
    generated = [
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="home",
            title=namespace.target_root_title,
            page_type="Home",
            rel_path=_namespace_relpath(config, namespace_key, "00_Home.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "index"), namespaced_page_id(namespace_key, "log")],
            body=f"# {namespace.target_root_title}\n\n- assets: **{asset_count}**\n",
        ),
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="index",
            title=f"{namespace.display_name} Index",
            page_type="Index",
            rel_path=_namespace_relpath(config, namespace_key, "01_Index.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "home"), namespaced_page_id(namespace_key, "log")],
            body=f"# {namespace.display_name} Index\n",
        ),
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="log",
            title=f"{namespace.display_name} Log",
            page_type="Log",
            rel_path=_namespace_relpath(config, namespace_key, "02_Log.md"),
            source_ids=[],
            links_to=[namespaced_page_id(namespace_key, "home"), namespaced_page_id(namespace_key, "index")],
            body=f"# {namespace.display_name} Log\n",
        ),
        _write_namespace_page(
            conn,
            config,
            namespace_key=namespace_key,
            short_id="asset-inventory",
            title=f"{namespace.display_name} Asset Inventory",
            page_type="Source",
            rel_path=_namespace_relpath(config, namespace_key, "sources/asset_inventory.md"),
            source_ids=[row[0] for row in conn.execute("SELECT asset_key FROM assets WHERE namespace_key = ? ORDER BY asset_key LIMIT 20", (namespace_key,)).fetchall()],
            links_to=[namespaced_page_id(namespace_key, "index")],
            body=f"# {namespace.display_name} Asset Inventory\n",
        ),
    ]
    conn.commit()
    return {"generated_pages": generated, "page_count": len(generated), "namespace_key": namespace_key}


def _ingest_agent_workspace(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> dict[str, object]:
    namespace = config.namespaces[namespace_key]
    counts = {
        "assets": _count_assets(conn, namespace_key),
        "local_files": _count_assets(conn, namespace_key, "asset_class IN ('local_file', 'manifest', 'local_db')"),
        "docs": _count_assets(conn, namespace_key, "asset_class IN ('wiki_node', 'wiki_doc', 'online_doc')"),
        "bases": _count_assets(conn, namespace_key, "asset_class IN ('base_app', 'base_table')"),
        "project_items": _count_assets(conn, namespace_key, "asset_class = 'project_work_item'"),
    }
    source_ids = [row[0] for row in conn.execute("SELECT asset_key FROM assets WHERE namespace_key = ? ORDER BY asset_key LIMIT 12", (namespace_key,)).fetchall()]
    docs_source_ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT asset_key
            FROM assets
            WHERE namespace_key = ?
              AND asset_class IN ('wiki_node', 'wiki_doc', 'online_doc')
            ORDER BY asset_key
            LIMIT 12
            """,
            (namespace_key,),
        ).fetchall()
    ]
    base_source_ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT asset_key
            FROM assets
            WHERE namespace_key = ?
              AND asset_class IN ('base_app', 'base_table')
            ORDER BY asset_key
            LIMIT 12
            """,
            (namespace_key,),
        ).fetchall()
    ]
    project_items_by_type = conn.execute(
        """
        SELECT COALESCE(json_extract(metadata_json, '$.work_item_type'), 'unknown'), COUNT(*)
        FROM assets
        WHERE namespace_key = ?
          AND asset_class = 'project_work_item'
        GROUP BY 1
        ORDER BY COUNT(*) DESC
        LIMIT 8
        """,
        (namespace_key,),
    ).fetchall()

    home_body = textwrap.dedent(
        f"""
        # {namespace.target_root_title}

        一个完全脱敏的 AI agent workspace demo，用来演示 `lark-cli x LLM wiki` 的编排方式。

        ## Coverage Snapshot

        - 总资产：**{counts['assets']}**
        - 本地素材：**{counts['local_files']}**
        - 远端文档 / Wiki：**{counts['docs']}**
        - Base / Bitable：**{counts['bases']}**
        - Project items：**{counts['project_items']}**
        """
    ).strip()

    index_body = textwrap.dedent(
        """
        # Agent Workspace Index

        ## Core pages

        - `asset-inventory`
        - `remote-docs-registry`
        - `ops-base-registry`
        - `state-lineage-registry`
        - `agent-ops-catalog`
        - `agent-system-map`
        - `execution-readiness-report`
        - `handoff-risks-report`
        """
    ).strip()

    log_body = textwrap.dedent(
        f"""
        # Agent Workspace Log

        - latest asset count: **{counts['assets']}**
        - latest page count: **{conn.execute("SELECT COUNT(*) FROM pages WHERE namespace_key = ?", (namespace_key,)).fetchone()[0]}**
        """
    ).strip()

    inventory_body = textwrap.dedent(
        f"""
        # Agent Workspace Asset Inventory

        ## Totals

        - local files / manifests / DBs: **{counts['local_files']}**
        - docs / wiki nodes: **{counts['docs']}**
        - bases: **{counts['bases']}**
        - project items: **{counts['project_items']}**
        """
    ).strip()

    docs_registry_lines = ["# Remote Docs Registry", "", "## Discovered Docs", ""]
    doc_rows = conn.execute(
        """
        SELECT title, remote_url, asset_class
        FROM assets
        WHERE namespace_key = ?
          AND asset_class IN ('wiki_node', 'wiki_doc', 'online_doc')
        ORDER BY title, asset_key
        LIMIT 30
        """,
        (namespace_key,),
    ).fetchall()
    if doc_rows:
        for row in doc_rows:
            docs_registry_lines.append(f"- `{row['asset_class']}` {row['title']} | {row['remote_url'] or 'https://example.invalid/docs/demo'}")
    else:
        docs_registry_lines.append("- No remote docs discovered yet. Run `discover_feishu_docs` after wiring `lark-cli`.")
    docs_registry_body = "\n".join(docs_registry_lines)

    base_registry_lines = ["# Ops Base Registry", "", "## Discovered Bases", ""]
    base_rows = conn.execute(
        """
        SELECT title, remote_url, asset_class
        FROM assets
        WHERE namespace_key = ?
          AND asset_class IN ('base_app', 'base_table')
        ORDER BY asset_class, title
        LIMIT 30
        """,
        (namespace_key,),
    ).fetchall()
    if base_rows:
        for row in base_rows:
            base_registry_lines.append(f"- `{row['asset_class']}` {row['title']} | {row['remote_url'] or 'https://example.invalid/base/demo'}")
    else:
        base_registry_lines.append("- No bases discovered yet. Run `discover_feishu_bases` after wiring `lark-cli`.")
    base_registry_body = "\n".join(base_registry_lines)

    state_lineage_body = textwrap.dedent(
        """
        # State Lineage Registry

        ## What this namespace tracks

        - local Markdown as canonical pages
        - remote docs / wiki snapshots
        - base snapshots
        - project work item snapshots
        - merge queue and sync journal
        """
    ).strip()

    entity_body = textwrap.dedent(
        """
        # Agent Ops Catalog

        ## Synthetic core entities

        - `AGENT-001`: research coordinator
        - `TASK-101`: weekly synthesis
        - `BASE::ops_registry`: structured operational state
        - `DOC::runbook`: mirrored execution guide
        """
    ).strip()

    concept_lines = [
        "# Agent System Map",
        "",
        "## Runtime surfaces",
        "",
        "- local `knowledge/wiki_src/**` stores canonical pages",
        "- local `state/**` stores compiler state and sync cursors",
        "- Lark Docs / Wiki provides the reading and collaboration layer",
        "- Lark Base provides operational control tables",
        "",
        "## Project item types",
        "",
    ]
    if project_items_by_type:
        for work_item_type, count in project_items_by_type:
            concept_lines.append(f"- `{work_item_type}`: {count}")
    else:
        concept_lines.append("- No project items discovered yet. Run `discover_feishu_project` after wiring your project source.")
    concept_body = "\n".join(concept_lines)

    readiness_body = textwrap.dedent(
        f"""
        # Execution Readiness Report

        ## Readiness gates

        - canonical pages present: **yes**
        - local assets registered: **{counts['local_files']}**
        - docs registry available: **{'yes' if docs_source_ids else 'not yet'}**
        - base registry available: **{'yes' if base_source_ids else 'not yet'}**
        - LLM synthesis can run when `provider != disabled`
        """
    ).strip()

    risks_body = textwrap.dedent(
        """
        # Handoff Risks Report

        ## Common failure modes

        - remote docs drift from local canonical markdown
        - base schemas change without refreshing snapshots
        - project snapshots go stale and weaken synthesis quality
        - LLM prompts over-expand if asset budgets are not capped
        """
    ).strip()

    def pid(short_id: str) -> str:
        return namespaced_page_id(namespace_key, short_id)

    page_specs = [
        ("home", namespace.target_root_title, "Home", "00_Home.md", source_ids, ["index", "log", "asset-inventory", "remote-docs-registry", "ops-base-registry", "state-lineage-registry", "agent-ops-catalog", "agent-system-map", "execution-readiness-report", "handoff-risks-report"], home_body),
        ("index", "Agent Workspace Index", "Index", "01_Index.md", [], ["home", "log"], index_body),
        ("log", "Agent Workspace Log", "Log", "02_Log.md", [], ["home", "index"], log_body),
        ("asset-inventory", "Agent Workspace Asset Inventory", "Source", "sources/asset_inventory.md", source_ids, ["index", "execution-readiness-report"], inventory_body),
        ("remote-docs-registry", "Remote Docs Registry", "Source", "sources/remote_docs_registry.md", docs_source_ids, ["index", "asset-inventory"], docs_registry_body),
        ("ops-base-registry", "Ops Base Registry", "Source", "sources/ops_base_registry.md", base_source_ids, ["index", "asset-inventory"], base_registry_body),
        ("state-lineage-registry", "State Lineage Registry", "Source", "sources/state_lineage_registry.md", _existing_source_ids(conn, ["STATE::lineage_summary"]), ["index", "agent-system-map"], state_lineage_body),
        ("agent-ops-catalog", "Agent Ops Catalog", "Entity", "entities/agent_ops_catalog.md", source_ids, ["index", "execution-readiness-report"], entity_body),
        ("agent-system-map", "Agent System Map", "Concept", "concepts/agent_system_map.md", _existing_source_ids(conn, ["STATE::lineage_summary", *base_source_ids[:2], *docs_source_ids[:2]]), ["index", "state-lineage-registry", "execution-readiness-report"], concept_body),
        ("execution-readiness-report", "Execution Readiness Report", "Report", "reports/execution_readiness_report.md", source_ids, ["index", "asset-inventory", "handoff-risks-report"], readiness_body),
        ("handoff-risks-report", "Handoff Risks Report", "Report", "reports/handoff_risks_report.md", source_ids, ["index", "execution-readiness-report"], risks_body),
    ]

    generated: list[str] = []
    for short_id, title, page_type, rel_str, source_ids_for_page, links, body in page_specs:
        compiled_body = _maybe_append_llm_synthesis(
            conn,
            config,
            namespace_key=namespace_key,
            short_id=short_id,
            title=title,
            page_type=page_type,
            body=body,
            source_ids=source_ids_for_page,
        )
        generated.append(
            _write_namespace_page(
                conn,
                config,
                namespace_key=namespace_key,
                short_id=short_id,
                title=title,
                page_type=page_type,
                rel_path=_namespace_relpath(config, namespace_key, rel_str),
                source_ids=source_ids_for_page,
                links_to=[pid(link) for link in links],
                body=compiled_body,
            )
        )
    conn.commit()
    return {"generated_pages": generated, "page_count": len(generated), "namespace_key": namespace_key}


def ingest(conn: sqlite3.Connection, config: AppConfig, namespace_key: str | None = None) -> dict[str, object]:
    namespace_key = namespace_key or config.default_project_namespace
    if namespace_key == config.account_namespace_key:
        return _ingest_account(conn, config)
    if namespace_key == config.default_project_namespace:
        return _ingest_agent_workspace(conn, config, namespace_key)
    return _ingest_generic_namespace(conn, config, namespace_key)
