#!/usr/bin/env python3
"""Agent-facing wrapper for the local lark-wiki runtime.

This script intentionally keeps remote writes out of the default workflows.
Use sync_push / ops base commands only after explicit user confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
LARK_WIKI = ROOT / "scripts" / "lark_wiki.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent wrapper for lark-wiki local knowledge workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    full = subparsers.add_parser("full", help="Run a local full knowledge refresh for a task")
    full.add_argument("--task", required=True)

    subparsers.add_parser("refresh", help="Refresh local inventory and graph only")
    subparsers.add_parser("doctor", help="Check local runtime and lark-cli readiness")
    humanize = subparsers.add_parser("humanize", help="Run Chinese humanizer pass before remote publishing")
    humanize.add_argument("paths", nargs="+")
    humanize.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.command == "doctor":
        return run_doctor()
    if args.command == "refresh":
        return run_refresh()
    if args.command == "full":
        return run_full(args.task)
    if args.command == "humanize":
        return run_humanize(args.paths, apply=args.apply)
    raise AssertionError(args.command)


def run_doctor() -> int:
    checks: list[dict[str, object]] = []

    checks.append(_check_file("runtime_root", ROOT))
    checks.append(_check_file("lark_wiki_entry", LARK_WIKI))
    checks.append(_check_file("state_dir", ROOT / "state"))
    checks.append(_check_file("knowledge_dir", ROOT / "knowledge"))
    checks.append(_check_python())
    checks.append(_check_lark_cli())

    # upgrade_preflight performs remote read / capability checks through lark-cli.
    if shutil.which("lark-cli"):
        result = _run(["upgrade_preflight"], allow_failure=True)
        checks.append({"name": "upgrade_preflight", "ok": result.returncode == 0, "detail": _brief(result)})
    else:
        checks.append({"name": "upgrade_preflight", "ok": False, "detail": "lark-cli not on PATH"})

    ok = all(bool(item["ok"]) for item in checks)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def run_refresh() -> int:
    steps = [
        ["discover_local_repo_assets"],
        ["classify_assets"],
        ["ingest"],
        ["inventory"],
        ["build_graph"],
    ]
    return _run_steps(steps)


def run_full(task: str) -> int:
    print(json.dumps({"ok": True, "task": task, "mode": "local_full_no_remote_write"}, ensure_ascii=False))
    return run_refresh()


def run_humanize(paths: list[str], *, apply: bool) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / "humanize_zh.py"), *paths, "--json"]
    if apply:
        cmd.append("--apply")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _run_steps(steps: list[list[str]]) -> int:
    results: list[dict[str, object]] = []
    for step in steps:
        result = _run(step, allow_failure=False)
        results.append({"step": step, "returncode": result.returncode, "stdout": result.stdout.strip()[-2000:]})
    print(json.dumps({"ok": True, "steps": results}, ensure_ascii=False, indent=2))
    return 0


def _run(args: Sequence[str], *, allow_failure: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    result = subprocess.run(
        [sys.executable, str(LARK_WIKI), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not allow_failure:
        sys.stderr.write(result.stderr)
        sys.stdout.write(result.stdout)
        raise SystemExit(result.returncode)
    return result


def _check_file(name: str, path: Path) -> dict[str, object]:
    return {"name": name, "ok": path.exists(), "detail": str(path)}


def _check_python() -> dict[str, object]:
    return {"name": "python", "ok": True, "detail": sys.version.split()[0]}


def _check_lark_cli() -> dict[str, object]:
    path = shutil.which("lark-cli")
    if not path:
        return {"name": "lark-cli", "ok": False, "detail": "not found on PATH"}
    result = subprocess.run(["lark-cli", "--version"], capture_output=True, text=True)
    return {"name": "lark-cli", "ok": result.returncode == 0, "detail": result.stdout.strip() or result.stderr.strip()}


def _brief(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stdout.strip() or result.stderr.strip()).replace("\n", " ")
    return text[:500]


if __name__ == "__main__":
    raise SystemExit(main())
