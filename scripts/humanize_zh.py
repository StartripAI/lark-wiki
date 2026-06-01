#!/usr/bin/env python3
"""Lightweight Chinese readability pass inspired by ai-zixun/humanizer-zh.

This is not an AI detector bypass. It is a local pre-sync editor for Chinese
Markdown pages: catch common model-ish wording, apply conservative wording
fixes, and keep code/frontmatter untouched.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


UPSTREAM = "https://github.com/ai-zixun/humanizer-zh"


@dataclass(frozen=True)
class Issue:
    pattern: str
    count: int
    note: str


REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^## 结论$", re.MULTILINE), "## 先说结论"),
    (re.compile(r"^## 当前能力$", re.MULTILINE), "## 它现在能做什么"),
    (re.compile(r"^## 明确边界$", re.MULTILINE), "## 哪些事它不做"),
    (re.compile(r"^## 当前实现状态$", re.MULTILINE), "## 现在做到哪一步"),
    (re.compile(r"^## 这个工具的价值$", re.MULTILINE), "## 它到底帮人省什么"),
    (re.compile(r"当前产品原语固定为"), "现在主线固定成"),
    (re.compile(r"已实现为本地证据缺口工作台"), "已经做成本地证据缺口工作台"),
    (re.compile(r"作为 runtime"), "作为默认运行时"),
    (re.compile(r"输出 `go / hold / no-go`"), "最后给出 `go / hold / no-go`"),
    (re.compile(r"只代表证据包是否可进入下一人工审核步骤"), "只说明证据包能不能交给人继续审核"),
    (re.compile(r"不代表交易批准、账号安全、估值准确、欺诈清除"), "不等于批准交易，也不保证账号安全、估值准确或已经排除欺诈"),
    (re.compile(r"生成可审查的证据包、缺口矩阵、人工采集任务、本地报告和进入下一人工审核步骤的建议"), "整理出证据包、缺口表、人工补证任务和下一步审核建议"),
    (re.compile(r"根据 requirement mapping、minimum support、validator pass 计算"), "按证据映射、最低支持等级和校验结果判断"),
    (re.compile(r"禁用词扫描"), "越界承诺扫描"),
)


ISSUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"赋能|重塑|颠覆|革命|开启新篇章|里程碑|深远影响"), "空泛大词，除非有机制和证据，否则删掉或落到具体动作。"),
    (re.compile(r"值得注意的是|与此同时|基于此|在这一背景下|从某种意义上说"), "翻译腔连接词，优先改成更短的中文连接。"),
    (re.compile(r"不是.+而是"), "机械对照句，偶尔能用，连续出现会很像模型模板。"),
    (re.compile(r"不仅.+还"), "机械排比句，检查是否可以改成自然叙述。"),
    (re.compile(r"这意味着.+时代|未来已经到来|这只是开始"), "口号式收束，改回具体约束或下一步动作。"),
    (re.compile(r"## 当前能力|## 明确边界|## 当前实现状态"), "机器式标题，优先改成人能扫懂的标题。"),
)


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :]


def split_fenced_blocks(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    cursor = 0
    in_fence = False
    fence_start = 0
    for match in re.finditer(r"^```.*$", text, flags=re.MULTILINE):
        if not in_fence:
            if match.start() > cursor:
                parts.append((False, text[cursor : match.start()]))
            fence_start = match.start()
            in_fence = True
        else:
            parts.append((True, text[fence_start : match.end()]))
            cursor = match.end()
            in_fence = False
    if in_fence:
        parts.append((True, text[fence_start:]))
    elif cursor < len(text):
        parts.append((False, text[cursor:]))
    return parts


def apply_light_humanize(text: str) -> str:
    frontmatter, body = split_frontmatter(text)
    chunks: list[str] = []
    for is_fence, chunk in split_fenced_blocks(body):
        if is_fence:
            chunks.append(chunk)
            continue
        updated = chunk
        for pattern, replacement in REPLACEMENTS:
            updated = pattern.sub(replacement, updated)
        updated = re.sub(r"\n{4,}", "\n\n\n", updated)
        chunks.append(updated)
    return frontmatter + "".join(chunks)


def find_issues(text: str) -> list[Issue]:
    _, body = split_frontmatter(text)
    prose = "".join(chunk for is_fence, chunk in split_fenced_blocks(body) if not is_fence)
    issues: list[Issue] = []
    for pattern, note in ISSUE_PATTERNS:
        matches = pattern.findall(prose)
        if matches:
            issues.append(Issue(pattern.pattern, len(matches), note))
    return issues


def humanize_file(path: Path, *, apply: bool) -> dict[str, object]:
    original = path.read_text(encoding="utf-8")
    updated = apply_light_humanize(original)
    changed = updated != original
    if apply and changed:
        path.write_text(updated, encoding="utf-8")
    issues = find_issues(updated)
    return {
        "path": str(path),
        "changed": changed,
        "applied": bool(apply and changed),
        "issue_count": sum(issue.count for issue in issues),
        "issues": [issue.__dict__ for issue in issues],
        "upstream_reference": UPSTREAM,
    }


def iter_markdown_paths(raw_paths: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.md")))
        else:
            paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Chinese humanizer pass over Markdown before publishing.")
    parser.add_argument("paths", nargs="+", help="Markdown files or directories")
    parser.add_argument("--apply", action="store_true", help="write conservative wording fixes")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--fail-on-issues", action="store_true", help="exit non-zero when humanizer issues remain")
    args = parser.parse_args()

    results = [humanize_file(path, apply=args.apply) for path in iter_markdown_paths(args.paths)]
    payload = {
        "ok": not (args.fail_on_issues and any(int(item["issue_count"]) for item in results)),
        "mode": "apply" if args.apply else "check",
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(f"{result['path']}: changed={result['changed']} issue_count={result['issue_count']}")
            for issue in result["issues"]:
                print(f"  - {issue['pattern']} x{issue['count']}: {issue['note']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
