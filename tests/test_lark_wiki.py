from __future__ import annotations

import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


class LarkWikiStarterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
