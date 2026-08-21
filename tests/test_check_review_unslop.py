from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_review_unslop import check_text  # noqa: E402


class CheckReviewUnslopTests(unittest.TestCase):
    def check(self, text: str):
        return check_text(Path("review.md"), text)

    def test_accepts_review_markdown_with_semantic_severity_markers(self):
        text = """## Short version

The retry keeps the incumbent response intact.

## Recommendations

1. **R1** 🟡 Caution. Move the assignment after parsing succeeds.
"""
        self.assertEqual([], self.check(text))

    def test_rejects_objective_ai_patterns(self):
        text = """## Short Version

Additionally, this is crucial — let me know if more detail would help.

1. **R1** 🟡 Caution - Move the assignment.
"""
        rules = {finding.rule for finding in self.check(text)}
        self.assertEqual(
            {"chatbot", "dash-substitute", "heading", "punctuation", "vocabulary"},
            rules,
        )

    def test_ignores_code_fences_inline_code_and_table_delimiters(self):
        text = """## Short version

`landscape — value`

```text
Additionally — quoted fixture
```

| Claim | Status |
| --- | --- |
"""
        self.assertEqual([], self.check(text))

    def test_checks_human_facing_table_cells(self):
        text = """| Claim | Status |
| --- | --- |
| Additionally — source quote | checked |
"""
        rules = {finding.rule for finding in self.check(text)}
        self.assertEqual({"punctuation", "vocabulary"}, rules)

    def test_distinguishes_list_markers_from_prose_dash_separators(self):
        text = """## Recommendations

- Keep this list item.
  - Keep this nested list item too.
- Replace this - it joins two clauses.
"""
        findings = self.check(text)
        self.assertEqual(1, len(findings))
        self.assertEqual("dash-substitute", findings[0].rule)
        self.assertEqual(5, findings[0].line)


if __name__ == "__main__":
    unittest.main()
