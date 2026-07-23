#!/usr/bin/env python3
"""Check ID continuity across review-lab pipeline stage artifacts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEDGER_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:C-\d{3,}|K-\d{3,}|K-new-\d{3,}(?:\([^)`\s]+\))?)"
)


@dataclass(frozen=True)
class Occurrence:
    stage: str
    line: int
    excerpt: str


@dataclass(frozen=True)
class StageDoc:
    name: str
    path: Path
    ids: set[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_ledger_id(raw: str) -> str:
    value = raw.strip("`*_")
    value = value.lstrip("[(")
    value = value.rstrip(".,;:")
    while value and value[-1] in "])}":
        opener = {")": "(", "]": "[", "}": "{"}[value[-1]]
        if opener in value:
            break
        value = value[:-1].rstrip(".,;:")
    return value


def ledger_id_sort_key(value: str) -> tuple[str, int, str]:
    match = re.match(r"^(C|K(?:-new)?)-(\d+)", value)
    if not match:
        return (value, -1, value)
    return (match.group(1), int(match.group(2)), value)


def excerpt(line: str, limit: int = 180) -> str:
    compact = " ".join(line.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def find_ids(line: str) -> list[str]:
    ids: list[str] = []
    for match in LEDGER_ID_RE.finditer(line):
        normalized = normalize_ledger_id(match.group(0))
        if normalized:
            ids.append(normalized)
    return ids


def is_contract(value: str) -> bool:
    return value.startswith("C-")


def stage_paths_from_manifest(pipeline_dir: Path) -> list[Path]:
    manifest_path = pipeline_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths: list[Path] = []
    for stage in manifest.get("stages", []):
        output = stage.get("output")
        if not output:
            continue
        path = Path(output)
        if path.exists():
            paths.append(path)
    return paths


def collect_stage_docs(pipeline_dir: Path) -> tuple[list[StageDoc], dict[str, list[Occurrence]]]:
    stage_paths = stage_paths_from_manifest(pipeline_dir)
    if not stage_paths:
        stage_paths = sorted(pipeline_dir.glob("[0-9][0-9]-*.md"))
    stages: list[StageDoc] = []
    occurrences: dict[str, list[Occurrence]] = {}
    for path in stage_paths:
        stage_ids: set[str] = set()
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            line_ids = find_ids(line)
            if not line_ids:
                continue
            for ledger_id in line_ids:
                stage_ids.add(ledger_id)
                occurrences.setdefault(ledger_id, []).append(
                    Occurrence(path.stem, line_number, excerpt(line))
                )
        stages.append(StageDoc(path.stem, path, stage_ids))
    return stages, occurrences


def first_stage_index(stages: list[StageDoc], needle: str) -> int | None:
    for index, stage in enumerate(stages):
        if needle in stage.name:
            return index
    return None


def ids_before(stages: list[StageDoc], index: int, *, candidates_only: bool = False) -> set[str]:
    ids: set[str] = set()
    for stage in stages[:index]:
        ids.update(stage.ids)
    if candidates_only:
        return {ledger_id for ledger_id in ids if not is_contract(ledger_id)}
    return ids


def ids_in_stage(stages: list[StageDoc], index: int, *, candidates_only: bool = False) -> set[str]:
    ids = set(stages[index].ids)
    if candidates_only:
        return {ledger_id for ledger_id in ids if not is_contract(ledger_id)}
    return ids


def occurrence_payload(
    ledger_id: str, occurrences: dict[str, list[Occurrence]], max_occurrences: int
) -> dict[str, Any]:
    hits = occurrences.get(ledger_id, [])
    return {
        "id": ledger_id,
        "kind": "contract" if is_contract(ledger_id) else "candidate",
        "occurrences": [
            {"stage": hit.stage, "line": hit.line, "excerpt": hit.excerpt}
            for hit in hits[:max_occurrences]
        ],
        "occurrence_count": len(hits),
    }


def issue_payload(
    ids: set[str], occurrences: dict[str, list[Occurrence]], max_occurrences: int
) -> list[dict[str, Any]]:
    return [
        occurrence_payload(ledger_id, occurrences, max_occurrences)
        for ledger_id in sorted(ids, key=ledger_id_sort_key)
    ]


def build_report(pipeline_dir: Path, max_occurrences: int) -> dict[str, Any]:
    stages, occurrences = collect_stage_docs(pipeline_dir)
    if not stages:
        raise ValueError(f"no stage markdown artifacts found under {pipeline_dir}")

    synthesis_index = first_stage_index(stages, "synthesis")
    verifier_index = first_stage_index(stages, "verifier")
    challenger_index = first_stage_index(stages, "challenger")
    if synthesis_index is None:
        synthesis_index = len(stages) - 1

    synthesis_ids = ids_in_stage(stages, synthesis_index)
    before_synthesis = ids_before(stages, synthesis_index)
    before_synthesis_candidates = {ledger_id for ledger_id in before_synthesis if not is_contract(ledger_id)}
    before_synthesis_contracts = {ledger_id for ledger_id in before_synthesis if is_contract(ledger_id)}

    issues: dict[str, list[dict[str, Any]]] = {
        "candidates_missing_from_synthesis": issue_payload(
            before_synthesis_candidates - synthesis_ids, occurrences, max_occurrences
        ),
        "contracts_missing_from_synthesis": issue_payload(
            before_synthesis_contracts - synthesis_ids, occurrences, max_occurrences
        ),
    }

    if verifier_index is not None:
        verifier_ids = ids_in_stage(stages, verifier_index, candidates_only=True)
        issues["candidates_missing_from_verifier"] = issue_payload(
            ids_before(stages, verifier_index, candidates_only=True) - verifier_ids,
            occurrences,
            max_occurrences,
        )

    if challenger_index is not None:
        challenger_ids = ids_in_stage(stages, challenger_index, candidates_only=True)
        issues["candidates_missing_from_challenger"] = issue_payload(
            ids_before(stages, challenger_index, candidates_only=True) - challenger_ids,
            occurrences,
            max_occurrences,
        )

    if verifier_index is not None and challenger_index is not None:
        verifier_candidates = ids_in_stage(stages, verifier_index, candidates_only=True)
        challenger_candidates = ids_in_stage(stages, challenger_index, candidates_only=True)
        issues["verified_candidates_missing_from_challenger"] = issue_payload(
            verifier_candidates - challenger_candidates,
            occurrences,
            max_occurrences,
        )
        issues["verified_candidates_missing_from_synthesis"] = issue_payload(
            verifier_candidates - synthesis_ids,
            occurrences,
            max_occurrences,
        )
        issues["challenged_candidates_missing_from_synthesis"] = issue_payload(
            challenger_candidates - synthesis_ids,
            occurrences,
            max_occurrences,
        )

    all_ids = set(occurrences)
    return {
        "generated_at": utc_now(),
        "pipeline_dir": str(pipeline_dir),
        "stage_count": len(stages),
        "stages": [
            {
                "name": stage.name,
                "path": str(stage.path),
                "id_count": len(stage.ids),
                "contract_count": sum(1 for ledger_id in stage.ids if is_contract(ledger_id)),
                "candidate_count": sum(1 for ledger_id in stage.ids if not is_contract(ledger_id)),
            }
            for stage in stages
        ],
        "totals": {
            "id_count": len(all_ids),
            "contract_count": sum(1 for ledger_id in all_ids if is_contract(ledger_id)),
            "candidate_count": sum(1 for ledger_id in all_ids if not is_contract(ledger_id)),
        },
        "issue_counts": {name: len(rows) for name, rows in issues.items()},
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Ledger Continuity Check",
        "",
        f"Pipeline: `{report['pipeline_dir']}`",
        f"Stages: {report['stage_count']}",
        (
            "Totals: "
            f"{report['totals']['contract_count']} contracts, "
            f"{report['totals']['candidate_count']} candidates"
        ),
        "",
        "## Stage ID Counts",
        "",
        "| Stage | Contracts | Candidates | IDs |",
        "| --- | ---: | ---: | ---: |",
    ]
    for stage in report["stages"]:
        lines.append(
            f"| `{stage['name']}` | {stage['contract_count']} | "
            f"{stage['candidate_count']} | {stage['id_count']} |"
        )

    lines.extend(["", "## Continuity Flags", ""])
    for issue_name, count in report["issue_counts"].items():
        lines.append(f"- `{issue_name}`: {count}")

    for issue_name, rows in report["issues"].items():
        if not rows:
            continue
        lines.extend(["", f"### {issue_name}", ""])
        for row in rows:
            first = row["occurrences"][0] if row["occurrences"] else None
            if first:
                lines.append(
                    f"- `{row['id']}` first seen in `{first['stage']}` line {first['line']}: "
                    f"{first['excerpt']}"
                )
            else:
                lines.append(f"- `{row['id']}`")
    return "\n".join(lines) + "\n"


def write_json_if_changed(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != rendered:
        path.write_text(rendered, encoding="utf-8")


def write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-dir", required=True)
    parser.add_argument("--out-json")
    parser.add_argument("--out-markdown")
    parser.add_argument("--max-occurrences", type=int, default=6)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_report(Path(args.pipeline_dir).expanduser(), args.max_occurrences)
    if args.out_json:
        write_json_if_changed(Path(args.out_json).expanduser(), report)
    markdown = render_markdown(report)
    if args.out_markdown:
        write_text_if_changed(Path(args.out_markdown).expanduser(), markdown)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
