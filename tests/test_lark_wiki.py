from __future__ import annotations

import os
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LarkWikiStarterTests(unittest.TestCase):
    PROJECT_NAMESPACE = "project::agent_workspace"

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "demo" / "agent_workspace_assets").mkdir(parents=True)
        (self.root / "misc").mkdir(parents=True)
        (self.root / "state").mkdir(parents=True)

        (self.root / "README.md").write_text("# test repo\n", encoding="utf-8")
        (self.root / "demo" / "agent_workspace_assets" / "agent_ops_manifest.json").write_text(
            '{"remote_url":"https://example.invalid/docs/agent-ops"}',
            encoding="utf-8",
        )
        (self.root / "demo" / "agent_workspace_assets" / "research_brief.md").write_text(
            "# Research Brief\n\nSynthetic starter content.\n",
            encoding="utf-8",
        )
        (self.root / "misc" / "capture.md").write_text("scratch\n", encoding="utf-8")
        (self.root / "state" / "agent_workspace_sync.sqlite").write_bytes(b"sqlite placeholder")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _page_id(self, short_id: str) -> str:
        return f"{self.PROJECT_NAMESPACE}::{short_id}"

    def _page_asset_key(self, short_id: str) -> str:
        return f"PAGE::{self.PROJECT_NAMESPACE}::{short_id}"

    def _write_fake_graphify_artifacts(
        self,
        config,
        *,
        nodes: list[dict[str, object]],
        links: list[dict[str, object]],
        report: str = "# Graphify Report\n\nSynthetic graph report.\n",
    ) -> None:
        graphify_dir = config.root / "graphify-out"
        graphify_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "directed": False,
            "multigraph": False,
            "graph": {},
            "nodes": nodes,
            "links": links,
        }
        (graphify_dir / "graph.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (graphify_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        (graphify_dir / "graph.html").write_text("<!doctype html><title>Graphify</title>", encoding="utf-8")

    def _write_inventory_page(
        self,
        conn: sqlite3.Connection,
        config,
        *,
        short_id: str,
        title: str,
        page_type: str,
        rel_path: str,
        body: str,
        source_ids: list[str] | None = None,
        links_to: list[str] | None = None,
        registered: bool = True,
    ) -> str:
        from scripts.lark_wiki.db import upsert_asset, upsert_page
        from scripts.lark_wiki.utils import relative_to_root, sha256_text

        source_ids = source_ids or []
        links_to = links_to or []
        page_id = self._page_id(short_id)
        asset_key = self._page_asset_key(short_id)
        payload = {
            "asset_key": asset_key,
            "links_to": links_to,
            "namespace_key": self.PROJECT_NAMESPACE,
            "page_id": page_id,
            "page_type": page_type,
            "portfolio_key": config.portfolio_key,
            "source_id": source_ids[0] if source_ids else "",
            "source_ids": source_ids,
            "sync_mode": "bidirectional_markdown_safe",
            "title": title,
        }
        text = "---\n" + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n---\n\n" + body
        full_path = config.wiki_src_dir / "projects" / "agent_workspace" / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(text, encoding="utf-8")
        local_path = relative_to_root(full_path, config.root)
        if registered:
            upsert_asset(
                conn,
                asset_key=asset_key,
                asset_class="local_file",
                title=title,
                local_path=local_path,
                upstream_system="unit_test",
                source_hash=sha256_text(text),
                canonical_role="canonical_page",
                sync_mode="bidirectional_markdown_safe",
                portfolio_key=config.portfolio_key,
                namespace_key=self.PROJECT_NAMESPACE,
                classification_status="classified",
                metadata={"page_id": page_id, "page_type": page_type},
            )
            upsert_page(
                conn,
                page_id=page_id,
                page_type=page_type,
                asset_key=asset_key,
                local_path=local_path,
                last_local_hash=sha256_text(text),
                sync_mode="bidirectional_markdown_safe",
                portfolio_key=config.portfolio_key,
                namespace_key=self.PROJECT_NAMESPACE,
                metadata={"title": title},
            )
        return page_id

    def _build_inventory_fixture(self, conn: sqlite3.Connection, config) -> dict[str, str]:
        home_id = self._page_id("home")
        overview_id = self._page_id("overview")
        shared_report_id = self._page_id("shared-report")
        missing_id = self._page_id("missing-page")
        ids = {
            "home": self._write_inventory_page(
                conn,
                config,
                short_id="home",
                title="Agent Workspace Home",
                page_type="Home",
                rel_path="00_Home.md",
                body="# Agent Workspace Home\n\nLinks to the overview page.\n",
                source_ids=["SRC::home"],
                links_to=[overview_id],
            ),
            "overview": self._write_inventory_page(
                conn,
                config,
                short_id="overview",
                title="Workspace Overview",
                page_type="Concept",
                rel_path="concepts/overview.md",
                body="# Workspace Overview\n\nA normal concept page.\n",
                source_ids=["SRC::shared"],
            ),
            "shared_report": self._write_inventory_page(
                conn,
                config,
                short_id="shared-report",
                title="Shared Source Report",
                page_type="Report",
                rel_path="reports/shared_source_report.md",
                body="# Shared Source Report\n\nShares a source with the overview.\n",
                source_ids=["SRC::shared"],
            ),
            "empty": self._write_inventory_page(
                conn,
                config,
                short_id="empty",
                title="Empty Page",
                page_type="Entity",
                rel_path="entities/empty.md",
                body="",
            ),
            "broken": self._write_inventory_page(
                conn,
                config,
                short_id="broken",
                title="Broken Link Page",
                page_type="Report",
                rel_path="reports/broken_link_page.md",
                body="# Broken Link Page\n\nThis page links to a page that is not present.\n",
                links_to=[missing_id],
            ),
            "unregistered": self._write_inventory_page(
                conn,
                config,
                short_id="unregistered",
                title="Unregistered Disk Page",
                page_type="Source",
                rel_path="sources/unregistered_disk_page.md",
                body="# Unregistered Disk Page\n\nThis file exists only on disk.\n",
                source_ids=["SRC::unregistered"],
                registered=False,
            ),
        }
        self.assertEqual(home_id, ids["home"])
        self.assertEqual(shared_report_id, ids["shared_report"])
        conn.commit()
        return ids

    def _nodes_by_page_id(self, result: dict[str, object]) -> dict[str, dict[str, object]]:
        nodes = result.get("nodes")
        self.assertIsInstance(nodes, list)
        return {str(node["page_id"]): node for node in nodes if isinstance(node, dict) and "page_id" in node}

    def _issue_types(self, result: dict[str, object]) -> set[str]:
        issues = result.get("issues")
        self.assertIsInstance(issues, list)
        return {str(issue.get("type") or issue.get("issue_type")) for issue in issues if isinstance(issue, dict)}

    def _edge_with_reason(self, result: dict[str, object], reason: str) -> dict[str, object]:
        edges = result.get("edges")
        self.assertIsInstance(edges, list)
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            reasons = edge.get("reasons") or edge.get("reason") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            if reason in reasons:
                return edge
        self.fail(f"missing edge reason {reason!r}")

    def _score(self, edge: dict[str, object]) -> float:
        self.assertIn("score", edge)
        return float(edge["score"])

    def test_schema_init_is_idempotent_and_tables_exist(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db

        config = build_config(self.root)
        conn = open_db(config)
        conn.execute(
            """
            INSERT INTO assets (
                asset_key, asset_class, title, local_path, remote_url, remote_id,
                upstream_system, source_hash, canonical_role, sync_mode, last_seen_at,
                last_synced_at, metadata_json
            ) VALUES (?, ?, ?, '', '', '', '', '', '', '', '2026-04-05T00:00:00+08:00', NULL, '{}')
            """,
            ("LOCAL::README.md", "local_file", "README"),
        )
        conn.commit()
        conn.close()

        conn = open_db(config)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "assets",
            "asset_edges",
            "pages",
            "runs",
            "issues",
            "merge_queue",
            "sync_cursor",
            "legacy_redirects",
            "namespaces",
            "cross_scope_edges",
            "sync_journal",
        }
        self.assertTrue(expected.issubset(tables))
        count = conn.execute("SELECT COUNT(*) FROM assets WHERE asset_key = 'LOCAL::README.md'").fetchone()[0]
        self.assertEqual(count, 1)
        conn.close()

    def test_repeated_runs_use_unique_ids(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db, start_run

        config = build_config(self.root)
        conn = open_db(config)

        first = start_run(conn, "classify_assets", portfolio_key=config.portfolio_key, namespace_key=config.account_namespace_key)
        second = start_run(conn, "classify_assets", portfolio_key=config.portfolio_key, namespace_key=config.account_namespace_key)

        self.assertNotEqual(first, second)
        count = conn.execute("SELECT COUNT(*) FROM runs WHERE command_name = 'classify_assets'").fetchone()[0]
        self.assertEqual(count, 2)
        conn.close()

    def test_build_config_registers_public_default_namespaces(self) -> None:
        from scripts.lark_wiki.config import build_config

        config = build_config(self.root)

        self.assertEqual(config.portfolio_key, "portfolio::default")
        self.assertEqual(config.account_namespace_key, "account")
        self.assertEqual(config.shared_namespace_key, "shared")
        self.assertEqual(config.inbox_namespace_key, "inbox")
        self.assertEqual(config.default_project_namespace, "project::agent_workspace")
        self.assertIn("project::agent_workspace", config.namespaces)
        project = config.namespaces["project::agent_workspace"]
        self.assertEqual(project.slug, "agent_workspace")
        self.assertIn("demo/agent_workspace_assets", project.local_roots)
        self.assertEqual(config.target_root_title, "Agent Workspace Starter")

    def test_config_exposes_agent_synthesis_limits_without_provider_surface(self) -> None:
        from scripts.lark_wiki.config import build_config

        config = build_config(self.root)

        self.assertEqual(config.agent_max_assets_per_prompt, 6)
        self.assertEqual(config.agent_max_chars_per_asset, 3500)
        for removed in (
            "llm_provider",
            "llm_model",
            "llm_command",
            "llm_timeout_seconds",
            "llm_max_assets_per_prompt",
            "llm_max_chars_per_asset",
            "llm_semantic_lint_enabled",
        ):
            self.assertFalse(hasattr(config, removed), removed)

    def test_legacy_llm_config_is_ignored_but_agent_synthesis_config_applies(self) -> None:
        from scripts.lark_wiki.config import build_config

        (self.root / "state" / "llm_wiki_v1.local.toml").write_text(
            "\n".join(
                [
                    "[llm]",
                    'provider = "command"',
                    "max_assets_per_prompt = 99",
                    "max_chars_per_asset = 99999",
                    "",
                    "[agent_synthesis]",
                    "max_assets_per_prompt = 3",
                    "max_chars_per_asset = 1200",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        config = build_config(self.root)

        self.assertEqual(config.agent_max_assets_per_prompt, 3)
        self.assertEqual(config.agent_max_chars_per_asset, 1200)

    def test_legacy_llm_config_alone_does_not_change_agent_synthesis_limits(self) -> None:
        from scripts.lark_wiki.config import build_config

        (self.root / "state" / "llm_wiki_v1.local.toml").write_text(
            "\n".join(
                [
                    "[llm]",
                    'provider = "command"',
                    "max_assets_per_prompt = 99",
                    "max_chars_per_asset = 99999",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        config = build_config(self.root)

        self.assertEqual(config.agent_max_assets_per_prompt, 6)
        self.assertEqual(config.agent_max_chars_per_asset, 3500)

    def test_docs_fetch_full_uses_v2_markdown_document_content(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki import lark_cli

        config = build_config(self.root)
        calls: list[list[str]] = []
        original = lark_cli.run_lark

        def fake_run_lark(config, args, allow_empty: bool = False):
            calls.append(args)
            return {
                "data": {
                    "document": {
                        "content": "<title>Remote Title</title>\n\n# Remote Title\n\nBody",
                        "document_id": "doc123",
                        "revision_id": 7,
                    }
                }
            }

        try:
            lark_cli.run_lark = fake_run_lark
            result = lark_cli.docs_fetch_full(config, "doc-token")
        finally:
            lark_cli.run_lark = original

        self.assertEqual(result["doc_id"], "doc123")
        self.assertEqual(result["title"], "Remote Title")
        self.assertEqual(result["markdown"], "# Remote Title\n\nBody")
        self.assertEqual(calls[0][:7], ["docs", "+fetch", "--api-version", "v2", "--as", "user", "--doc"])
        self.assertIn("--doc-format", calls[0])
        self.assertIn("markdown", calls[0])

    def test_create_or_update_doc_uses_v2_overwrite_content(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.sync import docs as sync_docs

        config = build_config(self.root)
        calls: list[list[str]] = []
        original = sync_docs.run_lark

        def fake_run_lark(config, args, allow_empty: bool = False):
            calls.append(args)
            return {
                "data": {
                    "document": {
                        "url": "https://example.feishu.cn/docx/doc123",
                        "document_id": "doc123",
                    }
                }
            }

        try:
            sync_docs.run_lark = fake_run_lark
            url, doc_token, node_token = sync_docs.create_or_update_doc(
                config,
                "Remote Title",
                "# Remote Title\n\nBody",
                mirror_doc_token="doc123",
            )
        finally:
            sync_docs.run_lark = original

        self.assertEqual(url, "https://example.feishu.cn/docx/doc123")
        self.assertEqual(doc_token, "doc123")
        self.assertEqual(node_token, "")
        self.assertEqual(calls[0][:8], ["docs", "+update", "--api-version", "v2", "--as", "user", "--doc", "doc123"])
        self.assertIn("--command", calls[0])
        self.assertIn("overwrite", calls[0])
        self.assertIn("--doc-format", calls[0])
        self.assertIn("markdown", calls[0])
        self.assertIn("--content", calls[0])
        self.assertIn("# Remote Title\n\nBody", calls[0])
        self.assertNotIn("--mode", calls[0])
        self.assertNotIn("--markdown", calls[0])

    def test_config_loads_with_system_python_tomli_fallback(self) -> None:
        interpreter = Path("/usr/bin/python3")
        if not interpreter.exists():
            self.skipTest("/usr/bin/python3 is not available")
        probe = subprocess.run(
            [
                str(interpreter),
                "-c",
                "import importlib.util; print(bool(importlib.util.find_spec('tomllib'))); print(bool(importlib.util.find_spec('tomli')))",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        lines = probe.stdout.splitlines()
        if len(lines) < 2 or lines[0] == "True":
            self.skipTest("system Python already has tomllib")
        if lines[1] != "True":
            self.skipTest("system Python has neither tomllib nor tomli")

        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)
        proc = subprocess.run(
            [
                str(interpreter),
                "-c",
                (
                    "from pathlib import Path; "
                    "from scripts.lark_wiki.config import build_config; "
                    f"cfg = build_config(Path({str(self.root)!r})); "
                    "print(cfg.default_project_namespace)"
                ),
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), self.PROJECT_NAMESPACE)

    def test_local_repo_discovery_classifies_generic_asset_types(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.discover.local_repo import discover_local_repo_assets

        config = build_config(self.root)
        conn = open_db(config)
        result = discover_local_repo_assets(conn, config)

        self.assertGreaterEqual(result["counts"]["local_file"], 2)
        self.assertEqual(
            conn.execute(
                "SELECT asset_class FROM assets WHERE asset_key = 'LOCAL::demo/agent_workspace_assets/agent_ops_manifest.json'"
            ).fetchone()[0],
            "manifest",
        )
        self.assertEqual(
            conn.execute(
                "SELECT asset_class FROM assets WHERE asset_key = 'LOCAL::state/agent_workspace_sync.sqlite'"
            ).fetchone()[0],
            "local_db",
        )
        self.assertIsNone(
            conn.execute("SELECT 1 FROM assets WHERE asset_key = 'LOCAL::state/llm_wiki_v1.sqlite'").fetchone()
        )

    def test_classify_assets_assigns_project_and_inbox_namespaces(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db, upsert_asset
        from scripts.lark_wiki.discover.classify import bootstrap_portfolio, classify_assets

        config = build_config(self.root)
        conn = open_db(config)
        bootstrap_portfolio(conn, config)
        upsert_asset(
            conn,
            asset_key="LOCAL::demo/agent_workspace_assets/research_brief.md",
            asset_class="local_file",
            title="research_brief",
            local_path="demo/agent_workspace_assets/research_brief.md",
            upstream_system="local_repo",
            source_hash="brief-hash",
            canonical_role="source_only",
            sync_mode="local_only",
        )
        upsert_asset(
            conn,
            asset_key="LOCAL::misc/capture.md",
            asset_class="local_file",
            title="capture",
            local_path="misc/capture.md",
            upstream_system="local_repo",
            source_hash="capture-hash",
            canonical_role="source_only",
            sync_mode="local_only",
        )

        result = classify_assets(conn, config)

        self.assertGreaterEqual(result["classified_count"], 2)
        project_ns = conn.execute(
            "SELECT namespace_key FROM assets WHERE asset_key = 'LOCAL::demo/agent_workspace_assets/research_brief.md'"
        ).fetchone()[0]
        inbox_ns = conn.execute(
            "SELECT namespace_key FROM assets WHERE asset_key = 'LOCAL::misc/capture.md'"
        ).fetchone()[0]
        self.assertEqual(project_ns, "project::agent_workspace")
        self.assertEqual(inbox_ns, "inbox")

    def test_public_cli_help_exposes_core_commands(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "lark_wiki.py"
        proc = subprocess.run(
            ["python3", str(script_path), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("bootstrap_portfolio", proc.stdout)
        self.assertIn("discover_feishu_docs", proc.stdout)
        self.assertIn("sync_push", proc.stdout)
        self.assertIn("inventory", proc.stdout)
        self.assertIn("graphify_status", proc.stdout)
        self.assertIn("graphify_query", proc.stdout)
        self.assertIn("graphify_path", proc.stdout)
        self.assertIn("graphify_explain", proc.stdout)
        self.assertIn("graphify_insights", proc.stdout)
        self.assertIn("graphify_candidates", proc.stdout)
        self.assertIn("agent_context", proc.stdout)
        self.assertIn("fusion_demo", proc.stdout)

    def test_inventory_discovers_disk_pages_and_writes_reports(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.inventory import inventory

        config = build_config(self.root)
        conn = open_db(config)
        ids = self._build_inventory_fixture(conn, config)

        result = inventory(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        self.assertEqual(result["namespace_key"], self.PROJECT_NAMESPACE)
        nodes_by_id = self._nodes_by_page_id(result)
        self.assertTrue(set(ids.values()).issubset(nodes_by_id))
        for page_id in ids.values():
            node = nodes_by_id[page_id]
            for field in ["page_id", "title", "page_type", "local_path", "source_ids", "links_to", "registered"]:
                self.assertIn(field, node)
        self.assertFalse(nodes_by_id[ids["unregistered"]]["registered"])

        issue_types = self._issue_types(result)
        self.assertIn("unregistered_page", issue_types)
        self.assertIn("empty_page", issue_types)
        self.assertIn("broken_link", issue_types)

        json_reports = sorted(config.build_dir.rglob("*inventory*.json"))
        markdown_reports = sorted(config.build_dir.rglob("*inventory*.md"))
        self.assertTrue(json_reports, "inventory should write a JSON report under knowledge/build")
        self.assertTrue(markdown_reports, "inventory should write a Markdown report under knowledge/build")
        report_payload = json.loads(json_reports[-1].read_text(encoding="utf-8"))
        self.assertIn("nodes", report_payload)
        markdown_text = markdown_reports[-1].read_text(encoding="utf-8")
        self.assertIn("unregistered_page", markdown_text)
        self.assertIn("broken_link", markdown_text)
        conn.close()

    def test_inventory_allows_real_pages_to_discuss_demos_without_placeholder_flag(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.inventory import inventory

        config = build_config(self.root)
        conn = open_db(config)
        page_id = self._write_inventory_page(
            conn,
            config,
            short_id="real-report",
            title="AI Trade Control Plane",
            page_type="Report",
            rel_path="reports/real_report.md",
            body="# AI Trade Control Plane\n\n不要做 AI demo 野系统，要沉淀正式页面、正式对象和可复盘动作。\n",
        )
        conn.commit()

        result = inventory(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        page_issues = [
            issue
            for issue in result["issues"]
            if isinstance(issue, dict) and issue.get("page_id") == page_id
        ]
        self.assertNotIn("demo_content", {str(issue.get("issue_type")) for issue in page_issues})
        conn.close()

    def test_inventory_relation_scores_prioritize_links_and_shared_sources(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.inventory import inventory

        config = build_config(self.root)
        conn = open_db(config)
        linked_to = self._page_id("linked-to")
        self._write_inventory_page(
            conn,
            config,
            short_id="linked-from",
            title="Linked From",
            page_type="Concept",
            rel_path="concepts/linked_from.md",
            body="# Linked From\n",
            links_to=[linked_to],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="linked-to",
            title="Linked To",
            page_type="Report",
            rel_path="reports/linked_to.md",
            body="# Linked To\n",
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="shared-a",
            title="Shared A",
            page_type="Entity",
            rel_path="entities/shared_a.md",
            body="# Shared A\n",
            source_ids=["SRC::same"],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="shared-b",
            title="Shared B",
            page_type="Entity",
            rel_path="entities/shared_b.md",
            body="# Shared B\n",
            source_ids=["SRC::same"],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="type-only-a",
            title="Type Only A",
            page_type="Source",
            rel_path="sources/type_only_a.md",
            body="# Type Only A\n",
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="type-only-b",
            title="Type Only B",
            page_type="Source",
            rel_path="sources/type_only_b.md",
            body="# Type Only B\n",
        )
        conn.commit()

        result = inventory(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        direct_link = self._edge_with_reason(result, "direct_link")
        shared_source = self._edge_with_reason(result, "shared_source")
        type_only = self._edge_with_reason(result, "same_page_type")
        self.assertGreater(self._score(direct_link), self._score(type_only))
        self.assertGreater(self._score(shared_source), self._score(type_only))
        self.assertIn("same_namespace", direct_link["reasons"])
        self.assertIn("same_namespace", shared_source["reasons"])
        self.assertEqual(direct_link["source_layer"], "canonical")
        self.assertEqual(shared_source["source_layer"], "canonical")
        conn.close()

    def test_inventory_cli_run_in_temp_repo(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db

        repo_root = Path(__file__).resolve().parents[1]
        shutil.copytree(
            repo_root / "scripts",
            self.root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        config = build_config(self.root)
        conn = open_db(config)
        self._build_inventory_fixture(conn, config)
        conn.close()

        proc = subprocess.run(
            ["python3", "scripts/lark_wiki.py", "inventory", "--namespace", self.PROJECT_NAMESPACE],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "inventory")
        self.assertEqual(payload["namespace_key"], self.PROJECT_NAMESPACE)
        self.assertTrue(list(config.build_dir.rglob("*inventory*.json")))

    def test_build_graph_uses_inventory_disk_scan(self) -> None:
        from scripts.lark_wiki.compiler.graph import build_graph
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db

        config = build_config(self.root)
        conn = open_db(config)
        ids = self._build_inventory_fixture(conn, config)

        result = build_graph(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        self.assertEqual(result["namespace_key"], self.PROJECT_NAMESPACE)
        graph_path = config.root / str(result["graph_path"])
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        node_ids = {node["page_id"] for node in graph_payload["nodes"]}
        self.assertIn(ids["unregistered"], node_ids)
        self.assertTrue(all("score" in edge and "reasons" in edge for edge in graph_payload["edges"]))
        direct_edge = next(
            edge
            for edge in graph_payload["edges"]
            if edge["from"] == ids["home"] and edge["to"] == ids["overview"]
        )
        self.assertIn("frontmatter.links_to", direct_edge["reasons"])
        shared_source_edge = next(
            edge
            for edge in graph_payload["edges"]
            if {edge["from"], edge["to"]} == {ids["overview"], ids["shared_report"]}
        )
        self.assertIn("shared_source", shared_source_edge["reasons"])
        self.assertNotIn("frontmatter.links_to", shared_source_edge["reasons"])
        issue_types = {issue["issue_type"] for issue in graph_payload["issues"]}
        self.assertNotIn("unregistered_page", issue_types)
        self.assertIn("broken_link", issue_types)
        registered = conn.execute(
            "SELECT 1 FROM pages WHERE page_id = ?",
            (ids["unregistered"],),
        ).fetchone()
        self.assertIsNotNone(registered)
        conn.close()

    def test_graphify_status_reports_artifact_state_without_graphify_install(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        import scripts.lark_wiki.graphify as graphify

        config = build_config(self.root)
        conn = open_db(config)
        original_find = graphify._find_graphify_binary
        try:
            graphify._find_graphify_binary = lambda: ("", "")
            result = graphify.graphify_status(conn, config)
        finally:
            graphify._find_graphify_binary = original_find

        self.assertIn("graphify_available", result)
        self.assertFalse(result["graphify_available"])
        self.assertEqual(result["artifact_state"], "missing_source")
        self.assertEqual(result["source_graph_path"], "graphify-out/graph.json")
        self.assertFalse(result["source_graph_exists"])
        self.assertEqual(result["recommended_workflow"][0], "$graphify .")
        self.assertEqual(result["official_refresh_command"], "$graphify .")
        self.assertEqual(result["graphify_shell_command"], "")
        conn.close()

    def test_graphify_status_reports_discovered_binary_as_cli_update_command(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        import scripts.lark_wiki.graphify as graphify

        config = build_config(self.root)
        conn = open_db(config)
        original_find = graphify._find_graphify_binary
        try:
            graphify._find_graphify_binary = lambda: ("/tmp/fake-graphify", "/tmp/fake-graphify")
            result = graphify.graphify_status(conn, config)
        finally:
            graphify._find_graphify_binary = original_find

        self.assertEqual(result["recommended_workflow"][0], "$graphify .")
        self.assertEqual(result["graphify_shell_command"], "/tmp/fake-graphify update .")
        self.assertEqual(result["graphify_update_command"], "/tmp/fake-graphify update .")
        conn.close()

    def test_graphify_status_reports_not_imported_and_invalid_source(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_status

        config = build_config(self.root)
        conn = open_db(config)
        self._write_fake_graphify_artifacts(
            config,
            nodes=[{"id": "g_one", "label": "One", "file_type": "document", "source_file": "README.md"}],
            links=[],
        )

        not_imported = graphify_status(conn, config)
        self.assertEqual(not_imported["artifact_state"], "not_imported")

        (config.root / "graphify-out" / "graph.json").write_text("{not-json", encoding="utf-8")
        invalid = graphify_status(conn, config)
        self.assertEqual(invalid["artifact_state"], "invalid_source")
        conn.close()

    def test_graphify_import_mirrors_artifacts_and_maps_known_edges(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import, load_graphify_enrichment

        config = build_config(self.root)
        conn = open_db(config)
        direct_id = self._write_inventory_page(
            conn,
            config,
            short_id="direct",
            title="Direct Keyword Page",
            page_type="Report",
            rel_path="reports/direct_keyword_page.md",
            body="# Direct Keyword Page\n\nhandoff details\n",
        )
        related_id = self._write_inventory_page(
            conn,
            config,
            short_id="related",
            title="Related Graph Page",
            page_type="Concept",
            rel_path="concepts/related_graph_page.md",
            body="# Related Graph Page\n\nRelated context.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_direct",
                    "label": "Direct Keyword Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/direct_keyword_page.md",
                    "community": 1,
                },
                {
                    "id": "g_related",
                    "label": "Related Graph Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/related_graph_page.md",
                    "community": 1,
                },
                {
                    "id": "g_unknown",
                    "label": "Unknown",
                    "file_type": "document",
                    "source_file": "unknown.md",
                },
            ],
            links=[
                {
                    "source": "g_direct",
                    "target": "g_related",
                    "relation": "semantically_similar_to",
                    "confidence": "EXTRACTED",
                    "confidence_score": 0.9,
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/direct_keyword_page.md",
                },
                {
                    "source": "g_direct",
                    "target": "g_unknown",
                    "relation": "mentions",
                    "confidence": "INFERRED",
                },
            ],
        )

        result = graphify_import(conn, config)
        enrichment = load_graphify_enrichment(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["mapped_node_count"], 2)
        self.assertEqual(result["mapped_edge_count"], 1)
        self.assertEqual(result["ignored_edge_count"], 1)
        self.assertTrue((config.root / "knowledge/build/graphify/repo/graph.json").exists())
        self.assertTrue((config.root / "knowledge/build/graphify/repo/GRAPH_REPORT.md").exists())
        self.assertTrue((config.root / "knowledge/build/graphify/repo/graph.html").exists())
        edge = enrichment["edges"][0]
        self.assertEqual(edge["from"], direct_id)
        self.assertEqual(edge["to"], related_id)
        self.assertIn("graphify:semantically_similar_to", edge["reasons"])
        self.assertEqual(edge["source_layer"], "graphify")
        conn.close()

    def test_graphify_status_marks_stale_import_after_source_changes(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import, graphify_status

        config = build_config(self.root)
        conn = open_db(config)
        self._write_fake_graphify_artifacts(
            config,
            nodes=[{"id": "g_one", "label": "One", "file_type": "document", "source_file": "README.md"}],
            links=[],
        )
        graphify_import(conn, config)
        self.assertEqual(graphify_status(conn, config)["artifact_state"], "current")

        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {"id": "g_one", "label": "One", "file_type": "document", "source_file": "README.md"},
                {"id": "g_two", "label": "Two", "file_type": "document", "source_file": "AGENTS.md"},
            ],
            links=[],
        )
        status = graphify_status(conn, config)

        self.assertEqual(status["artifact_state"], "stale_import")
        self.assertEqual(status["source_node_count"], 2)
        conn.close()

    def test_graphify_cli_wrappers_capture_official_command_output(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        import scripts.lark_wiki.graphify as graphify

        config = build_config(self.root)
        conn = open_db(config)
        self._write_fake_graphify_artifacts(
            config,
            nodes=[{"id": "g_one", "label": "One", "file_type": "document", "source_file": "README.md"}],
            links=[],
        )
        graphify.graphify_import(conn, config)

        captured: dict[str, object] = {}
        original_find = graphify._find_graphify_binary
        original_run = graphify.subprocess.run

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, stdout="NODE One", stderr="")

        try:
            graphify._find_graphify_binary = lambda: ("/tmp/fake-graphify", "/tmp/fake-graphify")
            graphify.subprocess.run = fake_run
            result = graphify.graphify_query(conn, config, query_text="one", budget=321, dfs=True)
            self.assertTrue(result["ok"])
            self.assertIn("knowledge/build/graphify/repo/graph.json", result["graph_path"])
            self.assertEqual(result["stdout"], "NODE One")
            command = captured["command"]
            kwargs = captured["kwargs"]
            self.assertIn("query", command)
            self.assertIn("one", command)
            self.assertIn("321", command)
            self.assertIn("--dfs", command)
            self.assertIn("--graph", command)
            self.assertEqual(kwargs["cwd"], config.root)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], subprocess.PIPE)

            result_path = graphify.graphify_path(conn, config, source="One", target="Two")
            self.assertTrue(result_path["ok"])
            self.assertIn("path", captured["command"])
            self.assertIn("One", captured["command"])
            self.assertIn("Two", captured["command"])

            result_explain = graphify.graphify_explain(conn, config, node="One")
            self.assertTrue(result_explain["ok"])
            self.assertIn("explain", captured["command"])
        finally:
            graphify._find_graphify_binary = original_find
            graphify.subprocess.run = original_run
        conn.close()

    def test_graphify_cli_wrapper_reports_missing_graph_and_subprocess_failure(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        import scripts.lark_wiki.graphify as graphify

        config = build_config(self.root)
        conn = open_db(config)
        original_find = graphify._find_graphify_binary
        original_run = graphify.subprocess.run
        try:
            graphify._find_graphify_binary = lambda: ("/tmp/fake-graphify", "/tmp/fake-graphify")
            missing = graphify.graphify_query(conn, config, query_text="missing")
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["status"], "missing_graph")
            self.assertEqual(missing["returncode"], 1)

            self._write_fake_graphify_artifacts(
                config,
                nodes=[{"id": "g_one", "label": "One", "file_type": "document", "source_file": "README.md"}],
                links=[],
            )
            graphify.graphify_import(conn, config)

            def fake_run(_command, **_kwargs):
                raise PermissionError("not executable")

            graphify.subprocess.run = fake_run
            failed = graphify.graphify_query(conn, config, query_text="one")
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["returncode"], 126)
            self.assertIn("not executable", failed["stderr"])
        finally:
            graphify._find_graphify_binary = original_find
            graphify.subprocess.run = original_run
        conn.close()

    def test_graphify_cli_wrapper_reports_missing_binary_without_traceback(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        import scripts.lark_wiki.graphify as graphify

        config = build_config(self.root)
        conn = open_db(config)
        original_find = graphify._find_graphify_binary
        try:
            graphify._find_graphify_binary = lambda: ("", "")
            result = graphify.graphify_explain(conn, config, node="anything")
        finally:
            graphify._find_graphify_binary = original_find

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "missing_graphify")
        self.assertEqual(result["returncode"], 127)
        conn.close()

    def test_build_graph_merges_graphify_edges_without_overwriting_frontmatter(self) -> None:
        from scripts.lark_wiki.compiler.graph import build_graph
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import

        config = build_config(self.root)
        conn = open_db(config)
        target_id = self._page_id("target")
        source_id = self._write_inventory_page(
            conn,
            config,
            short_id="source",
            title="Source Page",
            page_type="Report",
            rel_path="reports/source_page.md",
            body="# Source Page\n\nhandoff source\n",
            links_to=[target_id],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="target",
            title="Target Page",
            page_type="Concept",
            rel_path="concepts/target_page.md",
            body="# Target Page\n\nTarget context.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_source",
                    "label": "Source Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/source_page.md",
                },
                {
                    "id": "g_target",
                    "label": "Target Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/target_page.md",
                },
            ],
            links=[
                {
                    "source": "g_source",
                    "target": "g_target",
                    "relation": "calls",
                    "confidence": "AMBIGUOUS",
                    "confidence_score": 1.0,
                }
            ],
        )
        graphify_import(conn, config)

        result = build_graph(conn, config, namespace_key=self.PROJECT_NAMESPACE)
        graph_payload = json.loads((config.root / str(result["graph_path"])).read_text(encoding="utf-8"))
        edge = next(
            item
            for item in graph_payload["edges"]
            if item["from"] == source_id and item["to"] == target_id
        )

        self.assertIn("frontmatter.links_to", edge["reasons"])
        self.assertIn("graphify:calls", edge["reasons"])
        self.assertEqual(edge["source_layer"], "mixed")
        self.assertEqual(edge["graphify"]["relation"], "calls")
        self.assertEqual(edge["graphify"]["confidence"], "AMBIGUOUS")
        self.assertEqual(edge["graphify_edges"][0]["relation"], "calls")
        self.assertGreaterEqual(edge["score"], 10.0)
        conn.close()

    def test_build_graph_marks_secondary_graphify_edges_mixed_with_local_context(self) -> None:
        from scripts.lark_wiki.compiler.graph import build_graph
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import

        config = build_config(self.root)
        conn = open_db(config)
        first_id = self._write_inventory_page(
            conn,
            config,
            short_id="graph-only-a",
            title="Graph Only A",
            page_type="Concept",
            rel_path="concepts/graph_only_a.md",
            body="# Graph Only A\n\nFirst page.\n",
        )
        second_id = self._write_inventory_page(
            conn,
            config,
            short_id="graph-only-b",
            title="Graph Only B",
            page_type="Report",
            rel_path="reports/graph_only_b.md",
            body="# Graph Only B\n\nSecond page.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_a",
                    "label": "Graph Only A",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/graph_only_a.md",
                },
                {
                    "id": "g_b",
                    "label": "Graph Only B",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/graph_only_b.md",
                },
            ],
            links=[
                {
                    "source": "g_a",
                    "target": "g_b",
                    "relation": "semantically_similar_to",
                    "confidence": "INFERRED",
                }
            ],
        )
        graphify_import(conn, config)

        result = build_graph(conn, config, namespace_key=self.PROJECT_NAMESPACE)
        graph_payload = json.loads((config.root / str(result["graph_path"])).read_text(encoding="utf-8"))
        edge = next(
            item
            for item in graph_payload["edges"]
            if item["from"] == first_id and item["to"] == second_id
        )

        self.assertIn("same_namespace", edge["reasons"])
        self.assertIn("graphify:semantically_similar_to", edge["reasons"])
        self.assertEqual(edge["source_layer"], "mixed")
        self.assertNotIn("frontmatter.links_to", edge["reasons"])
        conn.close()

    def test_graphify_insights_and_candidates_surface_unmapped_value(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_candidates, graphify_import, graphify_insights
        from scripts.lark_wiki.inventory import inventory

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="mapped",
            title="Mapped Page",
            page_type="Concept",
            rel_path="concepts/mapped.md",
            body="# Mapped Page\n\nMapped body.\n",
        )
        conn.commit()
        report = "\n".join(
            [
                "# Graph Report",
                "",
                "## Surprising Connections",
                "- `README Graphify Workflow` --references--> `Mapped Page` [INFERRED]",
                "",
                "## Knowledge Gaps",
                "- **Thin community `Docs`** (2 nodes)",
                "",
                "## Suggested Questions",
                "- **Why does README Graphify Workflow connect to Mapped Page?**",
            ]
        )
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_mapped",
                    "label": "Mapped Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/mapped.md",
                    "community": 1,
                },
                {"id": "g_readme", "label": "README Graphify Workflow", "file_type": "document", "source_file": "README.md", "community": 1},
                {"id": "g_asset", "label": "Architecture Asset", "file_type": "image", "source_file": "assets/architecture.svg", "community": 1},
                {"id": "g_code", "label": "build_graph()", "file_type": "code", "source_file": "scripts/lark_wiki/compiler/graph.py", "community": 2},
                {
                    "id": "g_query",
                    "label": "Query Report",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/query-demo.md",
                    "community": 3,
                },
            ],
            links=[
                {"source": "g_mapped", "target": "g_readme", "relation": "references", "confidence": "INFERRED"},
                {"source": "g_readme", "target": "g_asset", "relation": "references", "confidence": "EXTRACTED"},
                {"source": "g_readme", "target": "g_code", "relation": "references", "confidence": "INFERRED"},
                {"source": "g_readme", "target": "g_query", "relation": "references", "confidence": "INFERRED"},
            ],
            report=report,
        )
        graph_path = config.root / "graphify-out" / "graph.json"
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        payload["hyperedges"] = [
            {
                "id": "h_graphify",
                "label": "Graphify Workflow Group",
                "nodes": ["g_readme", "g_asset", "g_mapped"],
                "relation": "participate_in",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "README.md",
            }
        ]
        graph_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        graphify_import(conn, config)

        insights = graphify_insights(conn, config, limit=5)
        candidates = graphify_candidates(conn, config, namespace_key=self.PROJECT_NAMESPACE, limit=10, min_degree=1)
        code_candidates = graphify_candidates(
            conn,
            config,
            namespace_key=self.PROJECT_NAMESPACE,
            limit=10,
            min_degree=1,
            include_code=True,
            write_files=False,
        )
        candidate_ids = {item["graphify_id"] for item in candidates["candidates"]}
        code_candidate_ids = {item["graphify_id"] for item in code_candidates["candidates"]}
        inventory_result = inventory(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        self.assertTrue((config.root / insights["json_path"]).exists())
        self.assertTrue((config.root / insights["markdown_path"]).exists())
        insights_markdown = (config.root / insights["markdown_path"]).read_text(encoding="utf-8")
        self.assertEqual(insights["surprising_connections"][0], "- `README Graphify Workflow` --references--> `Mapped Page` [INFERRED]")
        self.assertEqual(insights["knowledge_gaps"][0], "- **Thin community `Docs`** (2 nodes)")
        self.assertEqual(insights["suggested_questions"][0], "- **Why does README Graphify Workflow connect to Mapped Page?**")
        self.assertEqual(insights["hyperedges"][0]["nodes"], ["g_readme", "g_asset", "g_mapped"])
        self.assertIn("## Communities", insights_markdown)
        self.assertIn("## Hyperedges", insights_markdown)
        self.assertIn("g_readme", insights_markdown)
        self.assertIn("g_readme", candidate_ids)
        self.assertIn("g_asset", candidate_ids)
        self.assertNotIn("g_code", candidate_ids)
        self.assertNotIn("g_query", candidate_ids)
        self.assertIn("g_code", code_candidate_ids)
        readme_candidate = next(item for item in candidates["candidates"] if item["graphify_id"] == "g_readme")
        self.assertEqual(readme_candidate["proposed_page_type"], "Concept")
        self.assertIn("mentioned in Graphify report", readme_candidate["why"])
        self.assertIn("graphify_insights", inventory_result)
        self.assertIn("markdown_path", inventory_result["graphify_insights"])
        conn.close()

    def test_query_uses_graphify_related_pages_below_direct_hits(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import
        from scripts.lark_wiki.query import query

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="handoff-direct",
            title="Handoff Direct Page",
            page_type="Report",
            rel_path="reports/handoff_direct_page.md",
            body="# Handoff Direct Page\n\nhandoff keyword appears here.\n",
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="graph-related",
            title="Graph Related Page",
            page_type="Concept",
            rel_path="concepts/graph_related_page.md",
            body="# Graph Related Page\n\nNo matching keyword in this body.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_handoff",
                    "label": "Handoff Direct Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/handoff_direct_page.md",
                },
                {
                    "id": "g_related",
                    "label": "Graph Related Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/graph_related_page.md",
                },
            ],
            links=[
                {
                    "source": "g_handoff",
                    "target": "g_related",
                    "relation": "semantically_similar_to",
                    "confidence": "EXTRACTED",
                }
            ],
        )
        graphify_import(conn, config)

        result = query(conn, config, "handoff", namespace_key=self.PROJECT_NAMESPACE)
        report_text = (config.root / str(result["report_page"])).read_text(encoding="utf-8")

        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["graphify_related_count"], 1)
        self.assertIn("## 命中资产", report_text)
        self.assertIn("Handoff Direct Page", report_text)
        self.assertIn("## Graphify 相关页面", report_text)
        self.assertIn("Graph Related Page", report_text)
        self.assertIn("layer=graphify", report_text)
        self.assertIn("## Synthesis Context", report_text)
        self.assertLess(report_text.index("### Direct Page Context"), report_text.index("### Graphify Expanded Page Context"))
        self.assertLess(report_text.index("Handoff Direct Page"), report_text.index("Graph Related Page"))
        conn.close()

    def test_query_uses_graphify_for_disk_only_pages(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import graphify_import
        from scripts.lark_wiki.query import query
        from scripts.lark_wiki.llm_compile import AGENT_SYNTHESIS_MARKER

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="disk-direct",
            title="Disk Direct Page",
            page_type="Report",
            rel_path="reports/disk_direct_page.md",
            body="# Disk Direct Page\n\nhandoff appears only in this disk page.\n",
            registered=False,
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="disk-related",
            title="Disk Related Page",
            page_type="Concept",
            rel_path="concepts/disk_related_page.md",
            body="# Disk Related Page\n\nRelated page without the direct search word.\n",
            registered=False,
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_direct",
                    "label": "Disk Direct Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/disk_direct_page.md",
                },
                {
                    "id": "g_related",
                    "label": "Disk Related Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/disk_related_page.md",
                },
            ],
            links=[
                {
                    "source": "g_direct",
                    "target": "g_related",
                    "type": "depends_on",
                    "confidence": "EXTRACTED",
                }
            ],
        )
        graphify_import(conn, config)

        result = query(conn, config, "handoff", namespace_key=self.PROJECT_NAMESPACE)
        report_text = (config.root / str(result["report_page"])).read_text(encoding="utf-8")

        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["page_match_count"], 1)
        self.assertEqual(result["graphify_related_count"], 1)
        self.assertIn("## 命中页面", report_text)
        self.assertIn("Disk Direct Page", report_text)
        self.assertIn("## Graphify 相关页面", report_text)
        self.assertIn("Disk Related Page", report_text)
        self.assertIn("graphify:depends_on", report_text)
        self.assertIn("layer=graphify", report_text)
        self.assertIn("## Synthesis Context", report_text)
        self.assertIn("project::agent_workspace::disk-related", report_text)
        # Synthesis is an agent task block (no model call): it references the surfaced
        # pages for the host IDE agent to read, rather than inlining their bodies.
        self.assertIn(AGENT_SYNTHESIS_MARKER, report_text)
        conn.close()

    def test_agent_context_combines_inventory_graphify_and_candidates(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import agent_context, graphify_import

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="mapped",
            title="Mapped Page",
            page_type="Concept",
            rel_path="concepts/mapped.md",
            body="# Mapped Page\n\nMapped body.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_mapped",
                    "label": "Mapped Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/mapped.md",
                    "community": 1,
                },
                {"id": "g_readme", "label": "README Graphify Workflow", "file_type": "document", "source_file": "README.md", "community": 1},
            ],
            links=[{"source": "g_mapped", "target": "g_readme", "relation": "references", "confidence": "INFERRED"}],
            report="# Graph Report\n\n## Suggested Questions\n- **Why does Graphify matter?**\n",
        )
        graphify_import(conn, config)
        sidecar = self.root / "examples" / "tutorials" / "research-paper-workbench" / "reports" / "evidence-notes.md"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            "# Evidence Notes\n\n- Claim: retrieval helps handoff.\n- Evidence: measured recall in source notes.\n- Open question: which pages should be promoted?\n",
            encoding="utf-8",
        )
        page_count_before = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]

        result = agent_context(conn, config, namespace_key=self.PROJECT_NAMESPACE, output_format="md")
        page_count_after = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]

        self.assertEqual(result["namespace_key"], self.PROJECT_NAMESPACE)
        self.assertIn("canonical_inventory", result)
        self.assertIn("derived_graph", result)
        self.assertIn("candidate_intake", result)
        self.assertIn("transport_readiness", result)
        self.assertIn("graphify_status", result)
        self.assertIn("inventory", result)
        self.assertIn("candidates", result)
        self.assertEqual(result["inventory"], result["canonical_inventory"])
        self.assertEqual(result["transport_readiness"]["sync_push_policy"], "formal_pages_only")
        entry_titles = [item["title"] for item in result["canonical_inventory"]["entry_points"]]
        self.assertFalse(any(title.startswith("Query Report:") for title in entry_titles))
        paper = result["candidate_intake"]["paper_evidence_workbench"]
        self.assertEqual(paper["status"], "available")
        self.assertFalse(paper["writes_formal_pages"])
        self.assertEqual(page_count_before, page_count_after)
        self.assertIn("markdown", result)
        self.assertIn("## Canonical Inventory", result["markdown"])
        self.assertIn("## Derived Graph", result["markdown"])
        self.assertIn("## Candidate Intake", result["markdown"])
        self.assertIn("## Transport Readiness", result["markdown"])
        self.assertIn("agent_context", " ".join(result["recommended_commands"]))
        conn.close()

    def test_agent_context_handles_missing_graphify_artifacts(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import agent_context

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="local-page",
            title="Local Page",
            page_type="Concept",
            rel_path="concepts/local-page.md",
            body="# Local Page\n\nLocal body.\n",
        )
        conn.commit()

        result = agent_context(conn, config, namespace_key=self.PROJECT_NAMESPACE, output_format="md")

        self.assertEqual(result["graphify_status"]["artifact_state"], "missing_source")
        self.assertEqual(result["derived_graph"]["insights"]["node_count"], 0)
        self.assertEqual(result["candidate_intake"]["graphify_candidate_count"], 0)
        self.assertIn("## Canonical Inventory", result["markdown"])
        self.assertIn("Artifact state: `missing_source`", result["markdown"])
        conn.close()

    def test_query_excludes_current_report_from_graphify_related_pages(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.compiler.graph import build_graph
        from scripts.lark_wiki.graphify import graphify_import, graphify_import_summary, load_graphify_enrichment
        from scripts.lark_wiki.markdown import read_frontmatter
        from scripts.lark_wiki.query import query

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="handoff-direct",
            title="Handoff Direct Page",
            page_type="Report",
            rel_path="reports/handoff_direct_page.md",
            body="# Handoff Direct Page\n\nhandoff keyword appears here.\n",
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="query-old",
            title="Query Report: old",
            page_type="Report",
            rel_path="reports/query-old.md",
            body="# Query Report: old\n\nhandoff should not become a direct query source.\n",
        )
        conn.commit()
        first = query(conn, config, "handoff", namespace_key=self.PROJECT_NAMESPACE)
        report_path = str(first["report_page"])
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_handoff",
                    "label": "Handoff Direct Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/reports/handoff_direct_page.md",
                },
                {
                    "id": "g_report",
                    "label": "Query Report: handoff",
                    "file_type": "document",
                    "source_file": report_path,
                },
            ],
            links=[
                {
                    "source": "g_handoff",
                    "target": "g_report",
                    "relation": "references",
                    "confidence": "EXTRACTED",
                }
            ],
        )
        graphify_import(conn, config)
        import_summary = graphify_import_summary(config)
        enrichment = load_graphify_enrichment(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        result = query(conn, config, "handoff", namespace_key=self.PROJECT_NAMESPACE)
        full_report_path = config.root / str(result["report_page"])
        report_text = full_report_path.read_text(encoding="utf-8")
        frontmatter, _body = read_frontmatter(full_report_path)

        self.assertEqual(result["graphify_related_count"], 0)
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["page_match_count"], 1)
        self.assertGreaterEqual(import_summary["ignored_generated_node_count"], 1)
        self.assertFalse(any(edge.get("to") == "project::agent_workspace::query-handoff" for edge in enrichment["edges"]))
        self.assertNotIn("## Graphify 相关页面", report_text)
        self.assertNotIn("Query Report: old", report_text)
        self.assertNotIn("PAGE::project::agent_workspace::query-handoff", frontmatter.get("source_ids", []))
        self.assertNotIn("PAGE::project::agent_workspace::query-old", frontmatter.get("source_ids", []))
        graph_result = build_graph(conn, config, namespace_key=self.PROJECT_NAMESPACE)
        index_frontmatter, index_body = read_frontmatter(config.root / "knowledge/wiki_src/projects/agent_workspace/01_Index.md")
        self.assertNotIn("project::agent_workspace::query-handoff", index_frontmatter.get("links_to", []))
        self.assertIn("Generated query reports", index_body)
        graph_payload = json.loads((config.root / str(graph_result["graph_path"])).read_text(encoding="utf-8"))
        self.assertFalse(
            any(
                edge.get("from") == "project::agent_workspace::query-handoff"
                or edge.get("to") == "project::agent_workspace::query-handoff"
                for edge in graph_payload["edges"]
            )
        )
        conn.close()

    def test_fusion_demo_writes_complete_artifact(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.graphify import fusion_demo

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="system-direct",
            title="System Direct Page",
            page_type="Concept",
            rel_path="concepts/system_direct.md",
            body="# System Direct Page\n\nsystem keyword appears here.\n",
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="system-related",
            title="System Related Page",
            page_type="Source",
            rel_path="sources/system_related.md",
            body="# System Related Page\n\nRelated content.\n",
        )
        conn.commit()
        self._write_fake_graphify_artifacts(
            config,
            nodes=[
                {
                    "id": "g_direct",
                    "label": "System Direct Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/concepts/system_direct.md",
                },
                {
                    "id": "g_related",
                    "label": "System Related Page",
                    "file_type": "document",
                    "source_file": "knowledge/wiki_src/projects/agent_workspace/sources/system_related.md",
                },
            ],
            links=[{"source": "g_direct", "target": "g_related", "relation": "references", "confidence": "EXTRACTED"}],
        )

        result = fusion_demo(conn, config, namespace_key=self.PROJECT_NAMESPACE, query_text="system")

        markdown_path = config.root / result["artifacts"]["markdown_path"]
        json_path = config.root / result["artifacts"]["json_path"]
        self.assertTrue(markdown_path.exists())
        self.assertTrue(json_path.exists())
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("Canonical Inventory", markdown)
        self.assertIn("Derived Graph", markdown)
        self.assertIn("KRM Merge", markdown)
        self.assertIn("Candidate Intake", markdown)
        self.assertIn("Query Demo", markdown)
        self.assertIn("Transport Readiness", markdown)
        self.assertTrue(result["query_demo"]["report"]["has_synthesis_context"])
        self.assertTrue({"mixed", "graphify"}.intersection(result["krm_merge"]["edge_layer_counts"]))
        conn.close()

    def test_graphify_agent_files_exclude_private_and_generated_paths(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        graphifyignore = (repo_root / ".graphifyignore").read_text(encoding="utf-8")
        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
        agents = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
        contract = (repo_root / "docs" / "knowledge-layer-contract.md").read_text(encoding="utf-8")

        self.assertIn("state/", graphifyignore)
        self.assertIn("knowledge/build/", graphifyignore)
        self.assertIn("graphify-out/", graphifyignore)
        self.assertIn("knowledge/wiki_src/**/reports/query-*.md", graphifyignore)
        self.assertIn("graphify-out/", gitignore)
        self.assertIn("GRAPH_REPORT.md", agents)
        self.assertIn("agent_context", agents)
        self.assertIn("canonical_inventory", agents)
        self.assertIn("python3 scripts/lark_wiki.py graphify_import", agents)
        self.assertIn("Graphify relations are secondary signals", contract)
        self.assertIn("Paper Evidence Workbench drafts stay sidecar", contract)

    def test_detect_claim_contradictions_flags_conflicting_values(self) -> None:
        from scripts.lark_wiki.llm_compile import detect_claim_contradictions

        pages = [
            {"page_id": "p1", "body": "Claim: capital_total => 150万\nClaim: shared => same"},
            {"page_id": "p2", "body": "Claim: capital_total => 100万\nClaim: shared => same"},
        ]
        findings = detect_claim_contradictions(pages)
        claims = {finding["claim"] for finding in findings}
        self.assertIn("capital_total", claims)
        self.assertNotIn("shared", claims)
        conflict = next(finding for finding in findings if finding["claim"] == "capital_total")
        self.assertEqual(conflict["page_ids"], "p1, p2")

    def test_lint_flags_cross_page_contradiction_without_llm(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.lint import lint

        config = build_config(self.root)
        conn = open_db(config)
        overview_id = self._page_id("overview")
        self._write_inventory_page(
            conn,
            config,
            short_id="home",
            title="Home",
            page_type="Home",
            rel_path="00_Home.md",
            body="# Home\n\nClaim: steam_daily_sales => 150\n",
            links_to=[overview_id],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="overview",
            title="Overview",
            page_type="Concept",
            rel_path="concepts/overview.md",
            body="# Overview\n\nClaim: steam_daily_sales => 100\n",
        )

        # No model is ever called; the contradiction check is deterministic and always-on.
        lint(conn, config, namespace_key=self.PROJECT_NAMESPACE)
        contradiction_count = conn.execute(
            "SELECT COUNT(*) FROM issues "
            "WHERE namespace_key = ? AND issue_type = 'semantic_contradiction' AND status = 'open'",
            (self.PROJECT_NAMESPACE,),
        ).fetchone()[0]
        self.assertGreaterEqual(contradiction_count, 1)
        conn.close()

    def test_compile_page_markdown_emits_agent_task_block(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.llm_compile import AGENT_SYNTHESIS_MARKER, compile_page_markdown

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="src-page",
            title="Src",
            page_type="Concept",
            rel_path="concepts/src.md",
            body="# Src\n\nSome grounded content.\n",
        )
        out = compile_page_markdown(
            conn,
            config,
            namespace_key=self.PROJECT_NAMESPACE,
            title="T",
            page_type="Concept",
            base_body="body",
            source_ids=[self._page_asset_key("src-page")],
        )
        self.assertIn(AGENT_SYNTHESIS_MARKER, out)
        empty = compile_page_markdown(
            conn,
            config,
            namespace_key=self.PROJECT_NAMESPACE,
            title="T",
            page_type="Concept",
            base_body="body",
            source_ids=[],
        )
        self.assertEqual(empty, "")
        conn.close()

    def test_read_frontmatter_tolerates_unterminated_fence(self) -> None:
        from scripts.lark_wiki.markdown import read_frontmatter

        path = self.root / "unterminated.md"
        text = '---\n{"title": "No Close Fence"}\n\nbody continues with no closing fence\n'
        path.write_text(text, encoding="utf-8")

        frontmatter, body = read_frontmatter(path)

        self.assertEqual(frontmatter, {})
        self.assertEqual(body, text)

    def test_read_frontmatter_tolerates_invalid_json(self) -> None:
        from scripts.lark_wiki.markdown import read_frontmatter

        path = self.root / "bad_json.md"
        text = "---\n{bad json}\n---\n\n# Real Body\n"
        path.write_text(text, encoding="utf-8")

        frontmatter, body = read_frontmatter(path)

        self.assertEqual(frontmatter, {})
        self.assertEqual(body, text)

    def test_normalize_markdown_for_sync_tolerates_feishu_v2_roundtrip(self) -> None:
        from scripts.lark_wiki.markdown import normalize_markdown_for_sync

        local = "\n".join(
            [
                "# Title",
                "",
                "| A | B |",
                "|---|---|",
                "| one | two |",
                "",
                "- `Concept` AIOS OS Canonical Knowledge | inbound=9",
                "- **P0**（现在~6月底）：AI 交易平台 V0 上线闸门。",
                "```Plain Text",
                "body",
                "```",
                "",
            ]
        )
        remote = "\n".join(
            [
                "# Title",
                "",
                "| A | B |",
                "|-|-|",
                "| one | two |",
                "",
                "- `Concept`AIOS OS Canonical Knowledge | inbound=9",
                "- **P0**（现在\\~6月底）：AI 交易平台 V0 上线闸门。",
                "```Plain",
                "body",
                "```",
                "",
            ]
        )

        self.assertEqual(normalize_markdown_for_sync(local), normalize_markdown_for_sync(remote))

    def test_build_graph_survives_malformed_frontmatter_page(self) -> None:
        from scripts.lark_wiki.compiler.graph import build_graph
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db

        config = build_config(self.root)
        conn = open_db(config)
        ids = self._build_inventory_fixture(conn, config)
        malformed_path = (
            config.wiki_src_dir / "projects" / "agent_workspace" / "concepts" / "malformed.md"
        )
        malformed_path.parent.mkdir(parents=True, exist_ok=True)
        malformed_path.write_text("---\n{bad json}\n\nmalformed page body\n", encoding="utf-8")

        result = build_graph(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        graph_payload = json.loads((config.root / str(result["graph_path"])).read_text(encoding="utf-8"))
        node_ids = {node["page_id"] for node in graph_payload["nodes"]}
        self.assertTrue(set(ids.values()).issubset(node_ids))
        conn.close()

    def test_cli_sync_push_with_conflicts_reports_failure(self) -> None:
        from scripts.lark_wiki import cli
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db

        repo_root = Path(__file__).resolve().parents[1]
        shutil.copytree(
            repo_root / "scripts",
            self.root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        config = build_config(self.root)
        conn = open_db(config)
        conn.close()

        original_push = cli.sync_push
        original_build_config = cli.build_config
        original_argv = sys.argv

        def fake_push(_conn, _config, *, namespace_key, limit=0):
            return {
                "synced": [],
                "conflicts": ["project::agent_workspace::home"],
                "namespace_key": namespace_key,
            }

        captured: dict[str, object] = {}
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        try:
            cli.sync_push = fake_push
            cli.build_config = lambda root=None: build_config(self.root)
            sys.argv = ["lark_wiki.py", "sync_push", "--namespace", self.PROJECT_NAMESPACE]
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as ctx:
                    cli.main()
            captured["code"] = ctx.exception.code
        finally:
            cli.sync_push = original_push
            cli.build_config = original_build_config
            sys.argv = original_argv

        self.assertNotEqual(captured["code"], 0)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "sync_push")
        self.assertEqual(payload["conflicts"], 1)

        verify_conn = open_db(config)
        status = verify_conn.execute(
            "SELECT status FROM runs WHERE command_name = 'sync_push' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()[0]
        verify_conn.close()
        self.assertEqual(status, "failed")

    def test_query_uses_internal_relations_without_graphify_artifacts(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.query import query

        config = build_config(self.root)
        conn = open_db(config)
        self._write_inventory_page(
            conn,
            config,
            short_id="direct-hit",
            title="Direct Hit Page",
            page_type="Report",
            rel_path="reports/direct_hit_page.md",
            body="# Direct Hit Page\n\nhandoff keyword appears here.\n",
            source_ids=["SRC::shared"],
        )
        self._write_inventory_page(
            conn,
            config,
            short_id="internal-related",
            title="Internal Related Page",
            page_type="Concept",
            rel_path="concepts/internal_related_page.md",
            body="# Internal Related Page\n\nNo matching keyword in this body.\n",
            source_ids=["SRC::shared"],
        )
        conn.commit()
        self.assertFalse((config.root / "graphify-out").exists())

        result = query(conn, config, "handoff", namespace_key=self.PROJECT_NAMESPACE)
        report_text = (config.root / str(result["report_page"])).read_text(encoding="utf-8")

        self.assertEqual(result["match_count"], 1)
        self.assertGreaterEqual(result["graphify_related_count"], 1)
        self.assertIn("## Graphify 相关页面", report_text)
        self.assertIn("Internal Related Page", report_text)
        self.assertIn("shared_source", report_text)
        conn.close()

    def test_lint_does_not_flag_generated_query_reports_as_orphans(self) -> None:
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db
        from scripts.lark_wiki.lint import lint
        from scripts.lark_wiki.query import query

        config = build_config(self.root)
        conn = open_db(config)

        result = query(conn, config, "missing topic", namespace_key=self.PROJECT_NAMESPACE)
        lint(conn, config, namespace_key=self.PROJECT_NAMESPACE)
        report_page_id = self._page_id("query-missing-topic")
        self.assertTrue((config.root / str(result["report_page"])).exists())
        orphan_count = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE namespace_key = ? AND issue_type = 'orphan_page' AND page_id = ?",
            (self.PROJECT_NAMESPACE, report_page_id),
        ).fetchone()[0]

        self.assertEqual(orphan_count, 0)
        conn.close()


    def test_compile_sources_compiles_summaries_and_flags_contradiction(self) -> None:
        from scripts.lark_wiki.compiler.pages import compile_sources
        from scripts.lark_wiki.config import build_config
        from scripts.lark_wiki.db import open_db, upsert_asset
        from scripts.lark_wiki.llm_compile import AGENT_SYNTHESIS_MARKER
        from scripts.lark_wiki.utils import sha256_text

        config = build_config(self.root)
        conn = open_db(config)
        raw = self.root / "knowledge" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        for name, val in (("src1", "150"), ("src2", "100")):
            path = raw / f"{name}.md"
            path.write_text(f"# {name}\n\nClaim: steam_daily_sales => {val}\n", encoding="utf-8")
            upsert_asset(
                conn,
                asset_key=f"LOCAL::knowledge/raw/{name}.md",
                asset_class="local_file",
                title=name,
                local_path=f"knowledge/raw/{name}.md",
                upstream_system="unit_test",
                source_hash=sha256_text(path.read_text(encoding="utf-8")),
                canonical_role="raw_source",
                sync_mode="bidirectional_markdown_safe",
                portfolio_key=config.portfolio_key,
                namespace_key=self.PROJECT_NAMESPACE,
                classification_status="classified",
                metadata={},
            )
        conn.commit()

        result = compile_sources(conn, config, namespace_key=self.PROJECT_NAMESPACE)

        # Each raw source compiled into a summary page...
        self.assertEqual(result["compiled_source_count"], 2)
        summary_pages = conn.execute(
            "SELECT COUNT(*) FROM pages WHERE namespace_key = ? AND page_type = 'Summary'",
            (self.PROJECT_NAMESPACE,),
        ).fetchone()[0]
        self.assertEqual(summary_pages, 2)
        # ...and the conflicting claim across the two sources is flagged.
        self.assertGreaterEqual(result["contradiction_count"], 1)
        bodies = "\n".join(p.read_text(encoding="utf-8") for p in config.wiki_src_dir.rglob("source-summary-*.md"))
        self.assertIn(AGENT_SYNTHESIS_MARKER, bodies)  # tool emits an agent task block, never a model call
        self.assertIn("Claim: steam_daily_sales", bodies)  # claims lifted from source into wiki
        conn.close()


if __name__ == "__main__":
    unittest.main()
