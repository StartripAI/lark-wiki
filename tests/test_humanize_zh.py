from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class HumanizeZhTests(unittest.TestCase):
    def test_light_humanize_keeps_frontmatter_and_code_fences(self) -> None:
        from scripts.humanize_zh import apply_light_humanize

        text = """---
{"title":"demo"}
---

## 当前能力

当前产品原语固定为 Evidence -> Gap。

```text
## 当前能力
当前产品原语固定为 code sample
```
"""
        updated = apply_light_humanize(text)
        self.assertTrue(updated.startswith('---\n{"title":"demo"}\n---'))
        self.assertIn("## 它现在能做什么", updated)
        self.assertIn("现在主线固定成 Evidence -> Gap", updated)
        self.assertIn("```text\n## 当前能力\n当前产品原语固定为 code sample\n```", updated)

    def test_humanize_file_reports_remaining_issues(self) -> None:
        from scripts.humanize_zh import humanize_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.md"
            path.write_text("## 明确边界\n\n值得注意的是，这不是普通更新，而是一次革命。\n", encoding="utf-8")
            result = humanize_file(path, apply=True)
            self.assertTrue(result["changed"])
            self.assertIn("## 哪些事它不做", path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(result["issue_count"], 1)


if __name__ == "__main__":
    unittest.main()
