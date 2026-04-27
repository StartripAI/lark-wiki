from __future__ import annotations

import argparse
import sqlite3

from .compiler.graph import build_graph
from .compiler.pages import ingest
from .config import build_config
from .db import finish_run, open_db, start_run, upsert_asset
from .discover.classify import audit_coverage, bootstrap_portfolio, classify_assets, conformance_check, discover_account_assets
from .discover.feishu_bases import discover_feishu_bases
from .discover.feishu_docs import discover_feishu_docs
from .discover.feishu_project import discover_feishu_project
from .discover.local_repo import discover_local_repo_assets
from .discover.state_lineage import discover_state_lineage
from .lark_cli import run_command, run_lark
from .lint import lint
from .ops_base import bootstrap_ops_base, sync_ops_base
from .query import query
from .sync.docs import merge_patches, sync_pull, sync_push
from .utils import json_dumps, relative_to_root, sha256_text


RUN_COMMANDS = {
    "upgrade_preflight",
    "bootstrap_portfolio",
    "bootstrap_namespace",
    "discover_account_assets",
    "discover_local_repo_assets",
    "discover_feishu_docs",
    "discover_feishu_bases",
    "discover_feishu_project",
    "discover_state_lineage",
    "classify_assets",
    "audit_coverage",
    "conformance_check",
    "snapshot_legacy",
    "ingest",
    "build_graph",
    "sync_push",
    "sync_pull",
    "merge_patches",
    "lint",
    "query",
    "bootstrap_ops_base",
    "sync_ops_base",
}


def default_namespace_for(command_name: str, config) -> str:
    if command_name in {
        "upgrade_preflight",
        "bootstrap_portfolio",
        "discover_account_assets",
        "discover_local_repo_assets",
        "discover_feishu_docs",
        "discover_feishu_bases",
        "discover_feishu_project",
        "discover_state_lineage",
        "classify_assets",
        "audit_coverage",
        "conformance_check",
        "bootstrap_ops_base",
        "sync_ops_base",
    }:
        return config.account_namespace_key
    return config.default_project_namespace


def command_upgrade_preflight(conn: sqlite3.Connection, config, namespace_key: str) -> dict[str, object]:
    npm_path = run_command(config, ["which", "npm"]).strip()
    lark_paths = run_command(config, ["which", "-a", "lark-cli"]).splitlines()
    lark_version = run_command(config, ["lark-cli", "--version"]).strip()
    doctor = run_lark(config, ["doctor"])
    docs_help = run_command(config, ["lark-cli", "docs", "--help"])
    wiki_help = run_command(config, ["lark-cli", "wiki", "--help"])
    base_help = run_command(config, ["lark-cli", "base", "--help"])
    drive_help = run_command(config, ["lark-cli", "drive", "--help"])
    summary = {
        "npm_path": npm_path,
        "lark_paths": lark_paths,
        "lark_version": lark_version,
        "doctor_ok": doctor.get("ok", False),
        "doctor": doctor,
        "checks": {
            "docs_help_ok": "+fetch" in docs_help and "+update" in docs_help,
            "wiki_help_ok": "nodes" in wiki_help and "spaces" in wiki_help,
            "base_help_ok": "+table-list" in base_help and "+record-upsert" in base_help,
            "drive_help_ok": "+add-comment" in drive_help and "+import" in drive_help,
            "single_active_lark_path": len(lark_paths) == 1,
        },
    }
    snapshot_path = config.raw_dir / "state_lineage" / "upgrade_preflight.json"
    snapshot_path.write_text(json_dumps(summary), encoding="utf-8")
    upsert_asset(
        conn,
        asset_key="STATE::upgrade_preflight",
        asset_class="state_snapshot",
        title="lark-cli 升级预检快照",
        local_path=relative_to_root(snapshot_path, config.root),
        upstream_system="local",
        source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
        canonical_role="state_snapshot",
        sync_mode="local_only",
        portfolio_key=config.portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        metadata=summary,
    )
    conn.commit()
    return summary


def command_snapshot_legacy(conn: sqlite3.Connection, config, namespace_key: str) -> dict[str, object]:
    docs = discover_feishu_docs(conn, config)
    lineage = discover_state_lineage(conn, config)
    summary = {"docs": docs, "lineage": lineage, "mode": "legacy_snapshot", "namespace_key": namespace_key}
    legacy_path = config.raw_dir / "state_lineage" / "legacy_snapshot.json"
    legacy_path.write_text(json_dumps(summary), encoding="utf-8")
    conn.commit()
    return summary


def command_bootstrap_namespace(conn: sqlite3.Connection, config, namespace_key: str) -> dict[str, object]:
    portfolio = bootstrap_portfolio(conn, config)
    if namespace_key not in config.namespaces:
        raise RuntimeError(f"Unknown namespace: {namespace_key}")
    ingest_result = ingest(conn, config, namespace_key=namespace_key)
    graph_result = build_graph(conn, config, namespace_key=namespace_key)
    return {
        "portfolio": portfolio,
        "namespace_key": namespace_key,
        "ingest": ingest_result,
        "build_graph": graph_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lark Wiki starter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command_name in sorted(RUN_COMMANDS):
        subparser = subparsers.add_parser(command_name)
        if command_name in {"sync_push", "sync_pull"}:
            subparser.add_argument("--limit", type=int, default=0, help="Limit number of pages processed")
        if command_name == "query":
            subparser.add_argument("--query", required=True, help="Keyword query for local asset search")
        if command_name in {"bootstrap_namespace", "ingest", "build_graph", "sync_push", "sync_pull", "merge_patches", "lint", "query"}:
            subparser.add_argument("--namespace", default="", help="Target namespace key")
        if command_name in {"audit_coverage", "conformance_check"}:
            subparser.add_argument("--scope", choices=["account", "namespace"], default="account")
            subparser.add_argument("--namespace", default="", help="Namespace key when --scope namespace")
    args = parser.parse_args()
    config = build_config()
    namespace_key = getattr(args, "namespace", "") or default_namespace_for(args.command, config)
    conn = open_db(config)
    run_id = start_run(conn, args.command, portfolio_key=config.portfolio_key, namespace_key=namespace_key)
    try:
        command_handlers = {
            "upgrade_preflight": lambda c, cfg, a: command_upgrade_preflight(c, cfg, namespace_key),
            "bootstrap_portfolio": lambda c, cfg, a: bootstrap_portfolio(c, cfg),
            "bootstrap_namespace": lambda c, cfg, a: command_bootstrap_namespace(c, cfg, namespace_key),
            "discover_account_assets": lambda c, cfg, a: discover_account_assets(c, cfg),
            "discover_local_repo_assets": lambda c, cfg, a: discover_local_repo_assets(c, cfg),
            "discover_feishu_docs": lambda c, cfg, a: discover_feishu_docs(c, cfg),
            "discover_feishu_bases": lambda c, cfg, a: discover_feishu_bases(c, cfg),
            "discover_feishu_project": lambda c, cfg, a: discover_feishu_project(c, cfg),
            "discover_state_lineage": lambda c, cfg, a: discover_state_lineage(c, cfg),
            "classify_assets": lambda c, cfg, a: classify_assets(c, cfg),
            "audit_coverage": lambda c, cfg, a: audit_coverage(c, cfg, scope=a.scope, namespace_key=getattr(a, "namespace", "")),
            "conformance_check": lambda c, cfg, a: conformance_check(c, cfg, scope=a.scope, namespace_key=getattr(a, "namespace", "")),
            "snapshot_legacy": lambda c, cfg, a: command_snapshot_legacy(c, cfg, namespace_key),
            "ingest": lambda c, cfg, a: ingest(c, cfg, namespace_key=namespace_key),
            "build_graph": lambda c, cfg, a: build_graph(c, cfg, namespace_key=namespace_key),
            "sync_push": lambda c, cfg, a: sync_push(c, cfg, namespace_key=namespace_key, limit=a.limit),
            "sync_pull": lambda c, cfg, a: sync_pull(c, cfg, namespace_key=namespace_key, limit=a.limit),
            "merge_patches": lambda c, cfg, a: merge_patches(c, cfg, namespace_key=namespace_key),
            "lint": lambda c, cfg, a: lint(c, cfg, namespace_key=namespace_key),
            "query": lambda c, cfg, a: query(c, cfg, a.query, namespace_key=namespace_key),
            "bootstrap_ops_base": lambda c, cfg, a: bootstrap_ops_base(c, cfg),
            "sync_ops_base": lambda c, cfg, a: sync_ops_base(c, cfg),
        }
        result = command_handlers[args.command](conn, config, args)
        finish_run(conn, run_id, status="success", summary=result)
        print(json_dumps({"ok": True, "command": args.command, "namespace_key": namespace_key, "result": result}))
    except Exception as exc:
        finish_run(conn, run_id, status="failed", error_text=str(exc), summary={"command": args.command, "namespace_key": namespace_key})
        raise
    finally:
        conn.close()
