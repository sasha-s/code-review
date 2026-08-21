#!/usr/bin/env python3
"""Fail on objective unslop violations in human-facing review markdown."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str


UNICODE_PUNCTUATION = {
    "\N{EM DASH}": "em dash",
    "\N{EN DASH}": "en dash",
    "\N{LEFT DOUBLE QUOTATION MARK}": "left curly quote",
    "\N{RIGHT DOUBLE QUOTATION MARK}": "right curly quote",
    "\N{LEFT SINGLE QUOTATION MARK}": "left curly apostrophe",
    "\N{RIGHT SINGLE QUOTATION MARK}": "right curly apostrophe",
}

BANNED_WORDS = (
    "additionally",
    "crucial",
    "delve",
    "enduring",
    "enhance",
    "facilitate",
    "fostering",
    "garner",
    "interplay",
    "intricate",
    "landscape",
    "leverage",
    "numerous",
    "pivotal",
    "showcase",
    "tapestry",
    "testament",
    "underscore",
    "utilize",
    "vibrant",
)

BANNED_PHRASES = {
    "chatbot": (
        r"\bi hope this helps\b",
        r"\blet me know if\b",
        r"\bof course[!,]",
        r"\bcertainly[!,]",
        r"\bfound the smoking gun\b",
        r"\bgreat question[!,]",
        r"\byou(?:'| a)re absolutely right\b",
    ),
    "filler": (
        r"\bin order to\b",
        r"\bdue to the fact that\b",
        r"\bit is important to note that\b",
        r"\bin the event that\b",
    ),
    "formula": (
        r"\bnot just\b.{0,120}\bbut\b",
        r"\bdespite (?:the )?challenges?\b.{0,120}\bcontinues? to thrive\b",
    ),
}

LEGACY_TITLE_CASE_HEADINGS = {
    "Body Claims",
    "Coverage Ledger",
    "Delta Since Last Review",
    "Findings Ledger",
    "Graph Reconnaissance",
    "Overall Verdict",
    "PR Design & Problem Fit",
    "Questions for the Author",
    "Scope Map",
    "Short Version",
    "Step Back: Cross-Scope Research",
}


def _strip_inline_code(line: str) -> str:
    return re.sub(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", "", line)


def _is_markdown_syntax(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or bool(re.fullmatch(r"-{3,}", stripped))
        or bool(re.fullmatch(r"\|?(?:\s*:?-+:?\s*\|)+", stripped))
    )


def check_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    fence_char = ""
    fence_length = 0
    current_section = ""

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        fence = re.match(r"^\s*(`{3,}|~{3,})(.*)$", raw_line)
        if fence_char:
            marker = fence.group(1) if fence else ""
            suffix = fence.group(2) if fence else ""
            if marker.startswith(fence_char) and len(marker) >= fence_length and not suffix.strip():
                fence_char = ""
                fence_length = 0
            continue
        if fence:
            fence_char = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue
        if _is_markdown_syntax(raw_line):
            continue
        if raw_line.startswith("# "):
            continue

        line = _strip_inline_code(raw_line)
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(2)
            if len(heading.group(1)) == 2:
                current_section = title.lower()
            if title in LEGACY_TITLE_CASE_HEADINGS:
                findings.append(Finding(path, line_number, "heading", "use sentence case for this heading"))

        if current_section == "body claims" and raw_line.lstrip().startswith("|"):
            continue

        for char, name in UNICODE_PUNCTUATION.items():
            if char in line:
                findings.append(Finding(path, line_number, "punctuation", f"replace {name} with plain punctuation"))

        lowered = line.lower()
        for word in BANNED_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                findings.append(Finding(path, line_number, "vocabulary", f"replace AI-pattern word '{word}'"))

        for rule, patterns in BANNED_PHRASES.items():
            for pattern in patterns:
                if re.search(pattern, lowered):
                    findings.append(Finding(path, line_number, rule, "rewrite AI-pattern phrase"))

        prose = re.sub(r"^\s*(?:>\s*)*[-*+]\s+", "", line)
        if re.search(r"\s-\s", prose):
            findings.append(Finding(path, line_number, "dash-substitute", "replace prose ' - ' separator with a sentence"))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files to check")
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    for path in args.paths:
        try:
            findings.extend(check_text(path, path.read_text(encoding="utf-8")))
        except OSError as exc:
            print(f"{path}: check failed: {exc}", file=sys.stderr)
            return 2

    for finding in findings:
        print(f"{finding.path}:{finding.line}: unslop[{finding.rule}] {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
