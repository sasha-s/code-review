#!/usr/bin/env python3
"""Isolated review-lab harness for blind PR review experiments.

This runner deliberately separates reviewer inputs from benchmark evaluator
data. Benchmark goldens are cached only under an evaluator path and are never
written into the review input artifact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "code-review" / "review-lab"
DEFAULT_PR_AF_PROBLEMS = (
    Path.home()
    / ".cache"
    / "code-review"
    / "pr-af"
    / "benchmark"
    / "martian-code-review-bench"
    / "problems.json"
)
DEFAULT_REMAINING_MISS_ANNOTATIONS = (
    Path(__file__).resolve().parent / "annotations" / "remaining-misses.json"
)
DEFAULT_CHILD_CODEX_HOME = DEFAULT_CACHE_ROOT / "codex-home-auth-only"

RUNTIME_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
}

REVIEWABLE_EXTENSIONS = RUNTIME_EXTENSIONS | {
    ".css",
    ".ftl",
    ".html",
    ".json",
    ".json5",
    ".prisma",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".toml",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

DOC_EXTENSIONS = {
    ".adoc",
    ".md",
    ".mdx",
    ".rst",
    ".txt",
}

AGENT_INSTRUCTION_FILES = {
    "agents.md",
    "claude.md",
    "codex.md",
}

TEST_PATH_PATTERNS = (
    "/test/",
    "/tests/",
    "__tests__",
    ".test.",
    ".spec.",
    "_test.",
    "test_",
)

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "before",
    "being",
    "between",
    "called",
    "cannot",
    "code",
    "does",
    "done",
    "each",
    "from",
    "have",
    "into",
    "line",
    "more",
    "must",
    "only",
    "path",
    "should",
    "that",
    "their",
    "there",
    "this",
    "through",
    "when",
    "where",
    "while",
    "will",
    "with",
    "without",
}


@dataclass(frozen=True)
class AddedLine:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class DiffLine:
    path: str
    line: int
    text: str
    side: str


@dataclass(frozen=True)
class DiffHunk:
    path: str
    new_start: int
    new_count: int
    old_count: int
    deletion_only: bool


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_json(data: Any) -> str:
    return hash_text(stable_json(data))


def slugify(value: str) -> str:
    value = value.strip().replace("#", "-")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "case"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_if_changed(path: Path, data: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def write_text_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def materialize_local_instruction_stubs(root: Path) -> list[str]:
    """Avoid child Codex wasting time on host-local instruction includes."""
    stubs = {
        root / "LEAN-CTX.md": "\n".join(
            [
                "# review-lab lean-ctx stub",
                "",
                "This generated review-lab workspace intentionally does not include host-global instruction files.",
                "Use the explicit review-lab prompt and repo-local inputs for this run.",
                "",
            ]
        ),
        root
        / "skills"
        / "karpathy-guidelines"
        / "SKILL.md": "\n".join(
            [
                "---",
                "name: karpathy-guidelines",
                "description: review-lab local stub for missing host-global skill include",
                "---",
                "",
                "# Karpathy Guidelines Stub",
                "",
                "Use the explicit review-lab prompt. Keep findings evidence-based, scoped, and actionable.",
                "",
            ]
        ),
    }
    written: list[str] = []
    for path, text in stubs.items():
        if write_text_if_changed(path, text):
            written.append(str(path))
    return written


def ensure_child_codex_home(args: argparse.Namespace) -> None:
    """Create an auth-only CODEX_HOME for isolated child Codex runs."""
    source_home = Path(args.source_home).expanduser()
    out = Path(args.out).expanduser()
    auth_source = source_home / "auth.json"
    if not auth_source.exists():
        raise SystemExit(f"Missing required auth file: {auth_source}")

    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)

    linked: list[str] = []
    skipped: list[str] = []
    for name, required in [("auth.json", True), ("installation_id", False)]:
        source = source_home / name
        dest = out / name
        if not source.exists():
            if required:
                raise SystemExit(f"Missing required auth file: {source}")
            skipped.append(name)
            continue
        if dest.is_symlink() and dest.resolve() == source.resolve():
            linked.append(name)
            continue
        if dest.exists() or dest.is_symlink():
            if not args.force:
                raise SystemExit(
                    f"Refusing to replace existing {dest}. Pass --force to relink it."
                )
            dest.unlink()
        dest.symlink_to(source)
        linked.append(name)

    readme = [
        "# review-lab auth-only CODEX_HOME",
        "",
        "Generated for isolated child Codex runs.",
        "",
        "This directory symlinks authentication files from the real Codex home,",
        "but intentionally omits config, AGENTS, rules, sessions, and skills.",
        "",
        "Use it with:",
        "",
        "```bash",
        f"CODEX_HOME={out} codex --ask-for-approval never exec \\",
        "  --ignore-user-config --ignore-rules --ephemeral ...",
        "```",
        "",
    ]
    write_text_if_changed(out / "README.md", "\n".join(readme))
    result = {"codex_home": str(out), "linked": linked, "skipped": skipped}
    write_json_if_changed(out / "manifest.json", result)
    print(out)


def scan_codex_event_log(args: argparse.Namespace) -> None:
    """Scan child Codex JSON/event output for known benchmark isolation leaks."""
    event_log = Path(args.event_log).expanduser()
    text = safe_read_text(event_log, max_bytes=args.max_bytes)
    patterns = {
        "host-deepreview-skill": "/Users/sasha/code-review/skills/deepreview",
        "host-agent-skill": "/Users/sasha/.agents/skills/",
        "evaluator-path": "/evaluator/",
        "pr-af-goldens": "pr-af-goldens",
        "benchmark-golden-token": "benchmark-golden",
    }
    hits: list[dict[str, Any]] = []
    denial_markers = ("avoid ", "do not read", "did not inspect", "did not read", "not inspect", "not read")
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for kind, pattern in patterns.items():
            lower_kinds = {"pr-af-goldens", "benchmark-golden-token"}
            scan_line = line
            if kind.startswith("host-"):
                scan_line = scan_line.replace(f"!{pattern}", "")
            if kind in {"evaluator-path", "benchmark-golden-token"}:
                scan_line = scan_line.replace("!**/evaluator/**", "")
                scan_line = scan_line.replace("!**/benchmark-golden/**", "")
            scan_lowered = scan_line.lower()
            if kind in lower_kinds and any(marker in lowered for marker in denial_markers):
                continue
            haystack = scan_lowered if kind in lower_kinds else scan_line
            needle = pattern.lower() if kind in lower_kinds else pattern
            if needle in haystack:
                hits.append(
                    {
                        "line": line_number,
                        "kind": kind,
                        "excerpt": line[: args.max_excerpt_chars],
                    }
                )
                break

    report = {
        "event_log": str(event_log),
        "hit_count": len(hits),
        "hits": hits,
    }
    if args.out:
        write_json_if_changed(Path(args.out).expanduser(), report)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))


def is_generated_benchmark_worktree(path: Path) -> bool:
    parts = path.expanduser().resolve().parts
    return "pr-af-benchmark" in parts and "worktrees" in parts


def run_json(command: list[str]) -> Any:
    proc = subprocess.run(command, check=True, text=True, capture_output=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Command did not return JSON: {' '.join(command)}\n{exc}") from exc


def run_text(command: list[str]) -> str:
    proc = subprocess.run(command, check=True, text=True, capture_output=True)
    return proc.stdout


def git_head_or_none(repo_dir: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$", pr_url)
    if not match:
        raise ValueError(f"Unsupported PR URL: {pr_url}")
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def parse_commit_url(commit_url: str) -> tuple[str, str, str]:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{7,40})$", commit_url)
    if not match:
        raise ValueError(f"Unsupported commit URL: {commit_url}")
    owner, repo, sha = match.groups()
    return owner, repo, sha


def snapshot_ref_label(snapshot: dict[str, Any]) -> str:
    if snapshot.get("number") is not None:
        return f"PR-{snapshot.get('number')}"
    if snapshot.get("commit_sha"):
        return f"commit-{str(snapshot['commit_sha'])[:12]}"
    return str(snapshot.get("ref_label") or "unknown")


def problem_goldens(problem: dict[str, Any]) -> list[dict[str, Any]]:
    goldens = problem.get("goldens")
    if isinstance(goldens, list):
        return goldens
    legacy = problem.get("golden_comments")
    if isinstance(legacy, list):
        return legacy
    return []


def load_pr_af_subset(problems_path: Path, limit: int | None, ids: list[str]) -> list[dict[str, Any]]:
    problems = read_json(problems_path)
    if not isinstance(problems, list):
        raise SystemExit(f"Expected a list of problems in {problems_path}")
    if ids:
        wanted = set(ids)
        selected = [problem for problem in problems if problem.get("id") in wanted]
        missing = sorted(wanted - {problem.get("id") for problem in selected})
        if missing:
            raise SystemExit(f"Problem ids not found: {', '.join(missing)}")
        return selected
    return problems[:limit] if limit is not None else problems


def prepare_pr_af_subset(args: argparse.Namespace) -> None:
    problems_path = Path(args.problems).expanduser()
    cache_root = Path(args.cache_root).expanduser()
    selected = load_pr_af_subset(problems_path, args.limit, args.id)
    problem_file_hash = hash_text(problems_path.read_text(encoding="utf-8"))
    manifest_cases: list[dict[str, Any]] = []
    changed = 0

    for problem in selected:
        case_id = str(problem["id"])
        pr_url = str(problem["pr_url"])
        goldens = problem_goldens(problem)
        goldens_hash = hash_json(goldens)
        case_dir = cache_root / "cases" / slugify(case_id)
        review_input = {
            "case_id": case_id,
            "repo_label": problem.get("repo"),
            "pr_url": pr_url,
            "language": problem.get("language"),
            "num_files": problem.get("num_files"),
        }
        evaluator_payload = {
            "case_id": case_id,
            "goldens_hash": goldens_hash,
            "goldens": goldens,
            "note": "Evaluator-only. Do not pass this file to the reviewer.",
        }
        if write_json_if_changed(case_dir / "review-input.json", review_input):
            changed += 1
        if write_json_if_changed(case_dir / "evaluator" / "pr-af-goldens.json", evaluator_payload):
            changed += 1
        manifest_cases.append(
            {
                "case_id": case_id,
                "pr_url": pr_url,
                "review_input": str(case_dir / "review-input.json"),
                "evaluator_goldens": str(case_dir / "evaluator" / "pr-af-goldens.json"),
            }
        )

    subset_key = hash_json([case["case_id"] for case in manifest_cases])[:12]
    manifest = {
        "generated_at": utc_now(),
        "problems_path": str(problems_path),
        "problems_hash": problem_file_hash,
        "case_count": len(manifest_cases),
        "cases": manifest_cases,
    }
    manifest_path = cache_root / "manifests" / f"pr-af-subset-{subset_key}.json"
    write_json_if_changed(manifest_path, manifest)
    print(f"Prepared {len(manifest_cases)} cases ({changed} files changed)")
    print(manifest_path)


def fetch_pr(args: argparse.Namespace) -> None:
    pr_url = args.pr_url
    owner, repo, number = parse_pr_url(pr_url)
    fields = ",".join(
        [
            "number",
            "url",
            "title",
            "body",
            "author",
            "baseRefName",
            "headRefName",
            "headRefOid",
            "state",
            "mergeCommit",
            "changedFiles",
            "additions",
            "deletions",
        ]
    )
    metadata = run_json(["gh", "pr", "view", pr_url, "--json", fields])
    diff_text = run_text(["gh", "pr", "diff", pr_url])
    patch_hash = hash_text(diff_text)
    pr_head_sha = str(metadata.get("headRefOid") or "unknown")
    merge_commit = metadata.get("mergeCommit") or {}
    merge_commit_sha = str(merge_commit.get("oid") or "")
    review_target_sha = merge_commit_sha if metadata.get("state") == "MERGED" and merge_commit_sha else pr_head_sha
    cache_dir = (
        Path(args.cache_root).expanduser()
        / "snapshots"
        / f"{owner}_{repo}"
        / f"PR-{number}"
        / f"{review_target_sha[:12]}-{patch_hash[:12]}"
    )
    snapshot = {
        "fetched_at": utc_now(),
        "owner": owner,
        "repo": repo,
        "number": number,
        "pr_url": pr_url,
        "head_sha": pr_head_sha,
        "pr_head_sha": pr_head_sha,
        "merge_commit_sha": merge_commit_sha,
        "review_target_sha": review_target_sha,
        "patch_hash": patch_hash,
        "metadata": metadata,
    }
    write_json_if_changed(cache_dir / "snapshot.json", snapshot)
    write_text_if_changed(cache_dir / "patch.diff", diff_text)
    analyze_diff_to_dir(diff_text, cache_dir)
    print(cache_dir)


def fetch_commit(args: argparse.Namespace) -> None:
    commit_url = args.commit_url
    owner, repo, sha = parse_commit_url(commit_url)
    metadata = run_json(["gh", "api", f"repos/{owner}/{repo}/commits/{sha}"])
    commit_sha = str(metadata.get("sha") or sha)
    parents = metadata.get("parents") or []
    parent_sha = str(parents[0].get("sha") or "") if parents else ""
    diff_text = run_text(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.v3.diff",
            f"repos/{owner}/{repo}/commits/{commit_sha}",
        ]
    )
    patch_hash = hash_text(diff_text)
    cache_dir = (
        Path(args.cache_root).expanduser()
        / "snapshots"
        / f"{owner}_{repo}"
        / f"commit-{commit_sha[:12]}"
        / f"{commit_sha[:12]}-{patch_hash[:12]}"
    )
    snapshot = {
        "fetched_at": utc_now(),
        "owner": owner,
        "repo": repo,
        "commit_url": commit_url,
        "commit_sha": commit_sha,
        "parent_sha": parent_sha,
        "head_sha": commit_sha,
        "review_target_sha": commit_sha,
        "patch_hash": patch_hash,
        "metadata": metadata,
    }
    write_json_if_changed(cache_dir / "snapshot.json", snapshot)
    write_text_if_changed(cache_dir / "patch.diff", diff_text)
    analyze_diff_to_dir(diff_text, cache_dir)
    print(cache_dir)


def parse_added_lines(diff_text: str) -> list[AddedLine]:
    return [AddedLine(line.path, line.line, line.text) for line in parse_changed_lines(diff_text) if line.side == "added"]


def parse_changed_lines(diff_text: str) -> list[DiffLine]:
    changed: list[DiffLine] = []
    old_path = ""
    new_path = ""
    old_line: int | None = None
    new_line: int | None = None
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("--- "):
            path = raw_line[4:].strip()
            old_path = "" if path == "/dev/null" else (path[2:] if path.startswith("a/") else path)
            continue
        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            new_path = "" if path == "/dev/null" else (path[2:] if path.startswith("b/") else path)
            continue
        if raw_line.startswith("@@"):
            old_match = re.search(r"-(\d+)(?:,(\d+))?", raw_line)
            new_match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            old_line = int(old_match.group(1)) if old_match else None
            new_line = int(new_match.group(1)) if new_match else None
            continue
        if new_line is None or old_line is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            if new_path:
                changed.append(DiffLine(new_path, new_line, raw_line[1:], "added"))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            if old_path:
                changed.append(DiffLine(old_path, old_line, raw_line[1:], "removed"))
            old_line += 1
            continue
        else:
            old_line += 1
            new_line += 1
    return changed


def parse_diff_hunks(diff_text: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    new_path = ""
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            new_path = "" if path == "/dev/null" else (path[2:] if path.startswith("b/") else path)
            continue
        if not raw_line.startswith("@@") or not new_path:
            continue
        old_match = re.search(r"-(\d+)(?:,(\d+))?", raw_line)
        new_match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
        if not new_match:
            continue
        old_count = int(old_match.group(2) or "1") if old_match else 0
        new_start = int(new_match.group(1))
        new_count = int(new_match.group(2) or "1")
        hunks.append(
            DiffHunk(
                path=new_path,
                new_start=new_start,
                new_count=new_count,
                old_count=old_count,
                deletion_only=new_count == 0,
            )
        )
    return hunks


def changed_files_from_diff(diff_text: str) -> list[str]:
    files: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path != "/dev/null":
                files.append(path[2:] if path.startswith("b/") else path)
    return sorted(set(files))


def is_test_path(path: str) -> bool:
    lowered = f"/{path.lower()}"
    return any(pattern in lowered for pattern in TEST_PATH_PATTERNS)


def is_doc_path(path: str) -> bool:
    file_name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    return suffix in DOC_EXTENSIONS or file_name in AGENT_INSTRUCTION_FILES


def is_runtime_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in RUNTIME_EXTENSIONS and not is_test_path(path) and not is_doc_path(path)


def is_reviewable_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in REVIEWABLE_EXTENSIONS and not is_doc_path(path)


def classify_added_line(line: AddedLine | DiffLine) -> list[str]:
    text = line.text.strip()
    lowered = text.lower()
    if not text or text.startswith(("#", "//", "*", "/*", "*/")):
        return []
    categories: list[str] = []
    if re.search(r"\b(if|elif|else|switch|case|when|match)\b", text):
        categories.append("branch-contract")
    if re.search(r"\b(return|throw|raise|panic|error)\b", text):
        categories.append("error-or-return-contract")
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", text):
        categories.append("call-contract")
    if re.search(r"['\"][^'\"]{2,}['\"]", text):
        categories.append("string-key-consistency")
    if any(term in lowered for term in ("auth", "user", "credential", "token", "permission")):
        categories.append("identity-boundary")
    if any(term in lowered for term in ("metric", "tag", "log", "trace", "span")):
        categories.append("observability-consistency")
    if any(term in lowered for term in ("sleep", "timeout", "deadline", "timer", "interval", "retry")):
        categories.append("time-lifecycle")
    if any(term in lowered for term in ("env", "config", "feature", "flag", "option", "setting")):
        categories.append("configuration-contract")
    if any(term in lowered for term in ("insert", "update", "delete", "transaction", "lock", "cache")):
        categories.append("state-concurrency")
    return categories


def obligation_checks(category: str) -> list[str]:
    checks = {
        "branch-contract": [
            "Trace the opposite branch and null/missing/malformed variants.",
            "Compare old and new behavior at the caller boundary.",
        ],
        "error-or-return-contract": [
            "Verify callers handle the new return/error shape.",
            "Check whether retries, cleanup, and partial success preserve the old contract.",
        ],
        "call-contract": [
            "Read the callee definition and representative callers.",
            "Verify argument order, accepted types, ownership, side effects, and failure behavior.",
        ],
        "string-key-consistency": [
            "Search producers and consumers of the string/key.",
            "Check casing, pluralization, migration compatibility, and old persisted data.",
        ],
        "identity-boundary": [
            "Trace UI and direct API paths.",
            "Check missing user/session/actor cases and old authentication flows.",
        ],
        "observability-consistency": [
            "Search matching logs, metrics, tags, dashboards, and tests.",
            "Verify names remain stable enough for alerting and incident triage.",
        ],
        "time-lifecycle": [
            "Check deterministic behavior under slow, fast, repeated, and interrupted runs.",
            "Avoid fixed sleeps as proof of async or process lifecycle correctness.",
        ],
        "configuration-contract": [
            "Trace defaults, env/file sources, rollout behavior, and documented names.",
            "Check absent, malformed, and legacy config values.",
        ],
        "state-concurrency": [
            "Trace duplicate requests, concurrent actors, retry order, and cache/write ordering.",
            "Verify state keys match between create, lookup, update, and cleanup.",
        ],
    }
    return checks.get(category, ["Verify the other end of this changed contract."])


def removed_line_checks(category: str) -> list[str]:
    return [
        "Compare the removed behavior against the replacement, not just the new code in isolation.",
        "Identify which old inputs/states this removed line used to allow or handle.",
        *obligation_checks(category),
    ]


def extract_obligation_seeds(diff_text: str, max_seeds: int) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for line in parse_changed_lines(diff_text):
        if not is_reviewable_path(line.path):
            continue
        for category in classify_added_line(line):
            checks = obligation_checks(category) if line.side == "added" else removed_line_checks(category)
            seeds.append(
                {
                    "where": f"{line.path}:{line.line}",
                    "snippet": line.text.strip()[:300],
                    "category": category,
                    "side": line.side,
                    "checks": checks,
                }
            )
            if len(seeds) >= max_seeds:
                return seeds
    return seeds


def summarize_graph_payload(payload: Any) -> dict[str, int]:
    counts = {
        "changed_symbols": 0,
        "affected_flows": 0,
        "impacted_files": 0,
    }

    def visit(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower().replace("-", "_")
                if normalized in {"changed_symbols", "changed_functions", "symbols", "functions"}:
                    counts["changed_symbols"] += collection_size(child)
                elif normalized in {"affected_flows", "flows"}:
                    counts["affected_flows"] += collection_size(child)
                elif normalized in {"impacted_files", "impact_radius", "files"}:
                    counts["impacted_files"] += collection_size(child)
                visit(child, normalized)
        elif isinstance(value, list):
            for child in value:
                visit(child, key_hint)

    visit(payload)
    return counts


def collection_size(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    if value:
        return 1
    return 0


def build_graph_health(diff_text: str, graph_json: Path | None) -> dict[str, Any]:
    changed_files = changed_files_from_diff(diff_text)
    runtime_files = [path for path in changed_files if is_runtime_path(path)]
    health: dict[str, Any] = {
        "changed_files": len(changed_files),
        "changed_runtime_files": len(runtime_files),
        "runtime_files": runtime_files,
        "graph_present": graph_json is not None,
        "status": "unavailable",
    }
    if graph_json is None:
        return health
    payload = read_json(graph_json)
    counts = summarize_graph_payload(payload)
    health.update(counts)
    total_graph_signal = sum(counts.values())
    if runtime_files and total_graph_signal == 0:
        health["status"] = "failed-empty"
        health["reason"] = "Graph output has no symbols, flows, or impacted files for a non-empty runtime diff."
    elif total_graph_signal == 0:
        health["status"] = "empty"
    else:
        health["status"] = "ok"
    return health


def analyze_diff_to_dir(diff_text: str, out_dir: Path, graph_json: Path | None = None) -> None:
    changed_files = changed_files_from_diff(diff_text)
    summary = {
        "patch_hash": hash_text(diff_text),
        "changed_files": changed_files,
        "changed_runtime_files": [path for path in changed_files if is_runtime_path(path)],
        "added_line_count": len(parse_added_lines(diff_text)),
    }
    obligations = {
        "generated_at": utc_now(),
        "note": "Generic obligation seeds derived from changed code shape; not benchmark-specific findings.",
        "seeds": extract_obligation_seeds(diff_text, max_seeds=80),
    }
    graph_health = build_graph_health(diff_text, graph_json)
    write_json_if_changed(out_dir / "analysis" / "diff-summary.json", summary)
    write_json_if_changed(out_dir / "analysis" / "obligation-seeds.json", obligations)
    write_json_if_changed(out_dir / "analysis" / "graph-health.json", graph_health)


def analyze_diff(args: argparse.Namespace) -> None:
    diff_path = Path(args.diff).expanduser()
    out_dir = Path(args.out).expanduser()
    graph_json = Path(args.graph_json).expanduser() if args.graph_json else None
    analyze_diff_to_dir(diff_path.read_text(encoding="utf-8"), out_dir, graph_json)
    print(out_dir / "analysis")


def token_set(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text.lower()))
    return {token for token in tokens if token not in STOP_WORDS}


def identifier_set(text: str) -> set[str]:
    identifiers = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if len(token) < 3:
            continue
        if token.lower() in STOP_WORDS:
            continue
        has_signal = "_" in token or any(char.isupper() for char in token[1:]) or token.endswith("()")
        if has_signal:
            identifiers.add(token.lower().rstrip("()"))
    dotted = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", text)
    identifiers.update(value.lower() for value in dotted)
    return identifiers


def seed_terms(seed: dict[str, Any]) -> set[str]:
    text = " ".join([str(seed.get("where", "")), str(seed.get("snippet", "")), str(seed.get("category", ""))])
    return token_set(text)


def golden_terms(golden: dict[str, Any]) -> set[str]:
    return token_set(str(golden.get("comment", "")))


def coverage_score(terms: set[str], haystack_terms: set[str]) -> float:
    if not terms:
        return 0.0
    return round(len(terms & haystack_terms) / len(terms), 3)


def classify_audit_status(term_score: float, identifier_score: float, identifiers: set[str]) -> str:
    if identifiers and identifier_score < 0.34:
        return "weak-or-missing"
    if term_score >= 0.35:
        return "touched"
    return "weak-or-missing"


def classify_golden_status(term_score: float, identifier_score: float, identifiers: set[str]) -> str:
    if identifiers and identifier_score < 0.5:
        return "likely-miss"
    if term_score >= 0.5:
        return "possible-hit"
    return "likely-miss"


def safe_read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    if not path.is_file() or path.stat().st_size > max_bytes:
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def collect_target_text(snapshot_dir: Path, repo_dir: Path | None) -> str:
    patch_text = (snapshot_dir / "patch.diff").read_text(encoding="utf-8")
    parts = [patch_text]
    if repo_dir is None:
        return "\n".join(parts)

    for changed_file in changed_files_from_diff(patch_text):
        if changed_file.startswith("../") or changed_file.startswith("/"):
            continue
        parts.append(safe_read_text(repo_dir / changed_file))
    return "\n".join(part for part in parts if part)


def target_contradictions(golden_comment: str, target_text: str) -> list[str]:
    comment = golden_comment.lower()
    contradictions: list[str] = []
    helper_accepts_null = re.search(r"currentUser\s*==\s*null\s*\|\|", target_text) is not None
    helper_has_user_model = re.search(r"isConditionalPasskeysEnabled\s*\(\s*UserModel\s+\w+", target_text) is not None

    if "without usermodel parameter" in comment and helper_has_user_model:
        contradictions.append("target defines isConditionalPasskeysEnabled(UserModel ...), not only a no-arg helper")
    if "requiring user != null" in comment and helper_accepts_null:
        contradictions.append("target helper explicitly allows currentUser == null")
    if "context.getuser() is still null" in comment and "will not call" in comment and helper_accepts_null:
        contradictions.append("target null-user path can still pass the helper guard")
    return contradictions


def target_alignment(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    goldens_path = Path(args.goldens).expanduser()
    out_path = Path(args.out).expanduser()
    requested_repo_dir = Path(args.repo).expanduser() if args.repo else None
    snapshot = read_json(snapshot_dir / "snapshot.json")
    patch_text = (snapshot_dir / "patch.diff").read_text(encoding="utf-8")
    review_target_sha = str(snapshot.get("review_target_sha") or snapshot.get("head_sha") or "")
    repo_dir = requested_repo_dir
    requested_repo_head = git_head_or_none(requested_repo_dir) if requested_repo_dir else None
    source_status = "patch-only"
    if repo_dir is not None:
        source_status = "requested-repo"
        if review_target_sha and requested_repo_head != review_target_sha:
            owner = str(snapshot.get("owner") or "owner")
            repo = str(snapshot.get("repo") or "repo")
            ref_label = snapshot_ref_label(snapshot)
            candidate = (
                Path.home()
                / ".cache"
                / "code-review"
                / "pr-af-benchmark"
                / "worktrees"
                / worktree_cache_key(owner, repo)
                / f"{ref_label}-{review_target_sha[:12]}"
            )
            candidate_head = git_head_or_none(candidate)
            if candidate_head == review_target_sha:
                repo_dir = candidate
                source_status = "resolved-detached-worktree"
            else:
                repo_dir = None
                source_status = "patch-only-repo-head-mismatch"
    target_text = collect_target_text(snapshot_dir, repo_dir)
    patch_terms = token_set(patch_text)
    patch_identifiers = identifier_set(patch_text)
    target_terms = token_set(target_text)
    target_identifiers = identifier_set(target_text)
    worktree_head = git_head_or_none(repo_dir) if repo_dir is not None else None

    rows = []
    goldens_payload = read_json(goldens_path)
    for golden in goldens_payload.get("goldens", []):
        comment = str(golden.get("comment", ""))
        terms = golden_terms(golden)
        identifiers = identifier_set(comment)
        contradictions = target_contradictions(comment, target_text)
        patch_identifier_score = coverage_score(identifiers, patch_identifiers)
        target_identifier_score = coverage_score(identifiers, target_identifiers)
        if contradictions:
            status = "contradicted-by-target"
        elif patch_identifier_score == 0 and target_identifier_score == 0:
            status = "not-evidenced-in-target"
        elif target_identifier_score >= 0.6 or coverage_score(terms, target_terms) >= 0.75:
            status = "target-evidenced"
        else:
            status = "weak-target-evidence"
        rows.append(
            {
                "comment": comment,
                "severity": golden.get("severity"),
                "status": status,
                "contradictions": contradictions,
                "patch_term_score": coverage_score(terms, patch_terms),
                "target_term_score": coverage_score(terms, target_terms),
                "patch_identifier_score": patch_identifier_score,
                "target_identifier_score": target_identifier_score,
                "matched_target_identifiers": sorted(identifiers & target_identifiers)[:30],
                "missing_target_identifiers": sorted(identifiers - target_identifiers)[:30],
            }
        )

    alignment = {
        "generated_at": utc_now(),
        "snapshot_dir": str(snapshot_dir),
        "goldens_path": str(goldens_path),
        "repo_dir": str(repo_dir) if repo_dir else None,
        "requested_repo_dir": str(requested_repo_dir) if requested_repo_dir else None,
        "source_status": source_status,
        "snapshot_refs": {
            "head_sha": snapshot.get("head_sha"),
            "pr_head_sha": snapshot.get("pr_head_sha"),
            "merge_commit_sha": snapshot.get("merge_commit_sha"),
            "review_target_sha": snapshot.get("review_target_sha"),
            "worktree_head": worktree_head,
            "requested_repo_head": requested_repo_head,
            "patch_hash": snapshot.get("patch_hash"),
        },
        "golden_alignment": rows,
        "note": (
            "Evaluator-only target alignment check. A contradicted golden should not be treated as "
            "a review miss without manually confirming the intended benchmark target commit."
        ),
    }
    write_json_if_changed(out_path, alignment)
    print(out_path)


def load_snapshot_analysis(snapshot_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    analysis_dir = snapshot_dir / "analysis"
    summary = read_json(analysis_dir / "diff-summary.json")
    graph_health = read_json(analysis_dir / "graph-health.json")
    obligations = read_json(analysis_dir / "obligation-seeds.json")
    return summary, graph_health, obligations


def load_optional_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def format_context_pack(summary: dict[str, Any], graph_health: dict[str, Any], obligations: dict[str, Any]) -> str:
    seeds = obligations.get("seeds", [])
    lines = [
        "# review-lab Context Pack",
        "",
        "This pack is reviewer-facing. It contains diff-derived obligations and graph health only; it does not contain benchmark goldens.",
        "",
        "## Diff Summary",
        "",
        f"- Patch hash: `{summary.get('patch_hash', 'unknown')}`",
        f"- Changed files: {len(summary.get('changed_files', []))}",
        f"- Runtime files: {len(summary.get('changed_runtime_files', []))}",
        f"- Added lines: {summary.get('added_line_count', 0)}",
        "",
        "## Graph Health",
        "",
        f"- Status: `{graph_health.get('status', 'unknown')}`",
        f"- Graph present: {graph_health.get('graph_present', False)}",
    ]
    reason = graph_health.get("reason")
    if reason:
        lines.append(f"- Reason: {reason}")
    runtime_files = graph_health.get("runtime_files") or []
    if runtime_files:
        lines.extend(["", "Runtime files:"])
        lines.extend(f"- `{path}`" for path in runtime_files)

    coverage = load_optional_json(Path(str(graph_health.get("snapshot_dir", ""))) / "analysis" / "graphify-coverage.json")
    if coverage:
        coverage_summary = coverage.get("summary", {})
        lines.extend(
            [
                "",
                "## Graphify Coverage",
                "",
                f"- Mode: `{coverage.get('mode', 'unknown')}`",
                f"- Graph: `{coverage.get('graph_json', 'unknown')}`",
                f"- Changed files mapped: {coverage_summary.get('files_with_graph_nodes', 0)}/{coverage_summary.get('changed_files', 0)}",
                f"- Hunks mapped: {coverage_summary.get('mapped_hunks', 0)}/{coverage_summary.get('hunks', 0)}",
                f"- Unmapped hunks: {coverage_summary.get('unmapped_hunks', 0)}",
            ]
        )
        unmapped = [
            file_info
            for file_info in coverage.get("files", [])
            if is_reviewable_path(str(file_info.get("path", "")))
            and (file_info.get("unmapped_hunks") or file_info.get("node_count", 0) == 0)
        ]
        if unmapped:
            lines.extend(["", "Files needing non-graph fallback:"])
            for file_info in unmapped[:20]:
                lines.append(
                    f"- `{file_info.get('path')}`: {file_info.get('mapped_hunks', 0)}/{file_info.get('hunks', 0)} hunks mapped"
                )

    lines.extend(
        [
            "",
            "## Obligation Seeds",
            "",
            "Use these as investigation prompts, not as findings. For each high-value seed, read the changed line and the other end of the contract.",
            "",
        ]
    )
    for index, seed in enumerate(seeds[:40], start=1):
        checks = " ".join(seed.get("checks") or [])
        lines.extend(
            [
                f"### O{index}: {seed.get('category', 'contract')}",
                "",
                f"- Where: `{seed.get('where', '')}`",
                f"- Changed code: `{seed.get('snippet', '')}`",
                f"- Checks: {checks}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def make_context_pack(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    summary, graph_health, obligations = load_snapshot_analysis(snapshot_dir)
    graph_health = dict(graph_health)
    graph_health["snapshot_dir"] = str(snapshot_dir)
    out_path = Path(args.out).expanduser() if args.out else snapshot_dir / "analysis" / "reviewer-context.md"
    write_text_if_changed(out_path, format_context_pack(summary, graph_health, obligations))
    print(out_path)


def merge_line_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def format_source_excerpt_pack(
    snapshot_dir: Path,
    repo_dir: Path,
    context_lines: int,
    max_lines: int,
) -> str:
    snapshot = read_json(snapshot_dir / "snapshot.json")
    diff_text = (snapshot_dir / "patch.diff").read_text(encoding="utf-8")
    hunks_by_file: dict[str, list[DiffHunk]] = {}
    for hunk in parse_diff_hunks(diff_text):
        if hunk.path and is_reviewable_path(hunk.path):
            hunks_by_file.setdefault(hunk.path, []).append(hunk)

    lines = [
        "# review-lab Source Excerpts",
        "",
        "Exact target-source snippets around changed hunks. This pack is reviewer-facing and contains no evaluator goldens.",
        "",
        f"- Generated: {utc_now()}",
        f"- Review target: `{snapshot.get('review_target_sha', 'unknown')}`",
        f"- Context lines: {context_lines}",
        f"- Max snippet lines: {max_lines}",
        "",
    ]
    emitted = 0
    omitted: list[str] = []
    for path in sorted(hunks_by_file):
        source_path = repo_dir / path
        if emitted >= max_lines:
            omitted.append(path)
            continue
        if not source_path.is_file():
            lines.extend([f"## `{path}`", "", "_File is not present in the target worktree._", ""])
            continue
        source_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        windows: list[tuple[int, int]] = []
        for hunk in hunks_by_file[path]:
            hunk_start = max(1, hunk.new_start)
            hunk_end = hunk_start + max(hunk.new_count, 1) - 1
            start = max(1, hunk_start - context_lines)
            end = min(len(source_lines), hunk_end + context_lines)
            if start <= end:
                windows.append((start, end))
        windows = merge_line_windows(windows)
        if not windows:
            continue
        lines.extend([f"## `{path}`", ""])
        for start, end in windows:
            if emitted >= max_lines:
                omitted.append(path)
                break
            remaining = max_lines - emitted
            clipped_end = min(end, start + remaining - 1)
            lines.append(f"### Lines {start}-{clipped_end}")
            lines.append("```text")
            for line_number_value in range(start, clipped_end + 1):
                text = source_lines[line_number_value - 1]
                if len(text) > 500:
                    text = text[:497] + "..."
                lines.append(f"{line_number_value:>5}| {text}")
            lines.append("```")
            lines.append("")
            emitted += clipped_end - start + 1
            if clipped_end < end:
                omitted.append(path)
                break
    if omitted:
        lines.extend(
            [
                "## Omitted",
                "",
                "The line budget was reached before all hunk windows could be emitted.",
                "",
            ]
        )
        for path in sorted(set(omitted)):
            lines.append(f"- `{path}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def make_source_excerpt_pack(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    repo_dir = Path(args.repo).expanduser()
    if not repo_dir.exists():
        raise SystemExit(f"Repo does not exist: {repo_dir}")
    out_path = Path(args.out).expanduser() if args.out else snapshot_dir / "analysis" / "source-excerpts.md"
    write_text_if_changed(
        out_path,
        format_source_excerpt_pack(
            snapshot_dir=snapshot_dir,
            repo_dir=repo_dir,
            context_lines=args.context_lines,
            max_lines=args.max_lines,
        ),
    )
    print(out_path)


def path_for_child_manifest(path: Path, repo_dir: Path) -> str:
    try:
        return str(path.relative_to(repo_dir))
    except ValueError:
        return str(path)


def worktree_cache_key(owner: str, repo: str) -> str:
    return slugify(f"{owner}_{repo}").replace(".", "_")


def ensure_worktree(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    repo_dir = Path(args.repo).expanduser()
    if not repo_dir.exists():
        raise SystemExit(f"Repo does not exist: {repo_dir}")

    snapshot = read_json(snapshot_dir / "snapshot.json")
    review_target_sha = str(snapshot.get("review_target_sha") or snapshot.get("head_sha") or "")
    if not review_target_sha:
        raise SystemExit(f"Snapshot has no review target: {snapshot_dir / 'snapshot.json'}")

    owner = str(snapshot.get("owner") or "owner")
    repo = str(snapshot.get("repo") or "repo")
    ref_label = snapshot_ref_label(snapshot)
    out_root = (
        Path(args.out_root).expanduser()
        if args.out_root
        else Path.home() / ".cache" / "code-review" / "pr-af-benchmark" / "worktrees"
    )
    out_path = (
        Path(args.out).expanduser()
        if args.out
        else out_root / worktree_cache_key(owner, repo) / f"{ref_label}-{review_target_sha[:12]}"
    )

    if out_path.exists():
        existing_head = git_head_or_none(out_path)
        if existing_head == review_target_sha:
            print(out_path)
            return
        raise SystemExit(
            "Cached worktree exists but does not match snapshot target. "
            f"path={out_path} repo_head={existing_head or 'not-a-git-worktree'} "
            f"review_target={review_target_sha}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "worktree", "add", "--detach", str(out_path), review_target_sha],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "Failed to create worktree. "
            f"repo={repo_dir} target={review_target_sha} out={out_path}\n{proc.stderr.strip()}"
        )
    new_head = git_head_or_none(out_path)
    if new_head != review_target_sha:
        raise SystemExit(
            "Created worktree but HEAD does not match snapshot target. "
            f"path={out_path} repo_head={new_head or 'unknown'} review_target={review_target_sha}"
        )
    print(out_path)


def make_child_workspace(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    repo_dir = Path(args.repo).expanduser()
    if not repo_dir.exists():
        raise SystemExit(f"Repo does not exist: {repo_dir}")
    snapshot = read_json(snapshot_dir / "snapshot.json")
    review_target_sha = str(snapshot.get("review_target_sha") or snapshot.get("head_sha") or "")
    target = (review_target_sha or "unknown")[:12]
    patch = str(snapshot.get("patch_hash") or hash_text(safe_read_text(snapshot_dir / "patch.diff")))[:12]
    repo_head_sha = git_head_or_none(repo_dir)
    if (
        review_target_sha
        and repo_head_sha
        and repo_head_sha != review_target_sha
        and not args.allow_head_mismatch
    ):
        raise SystemExit(
            "Repo HEAD does not match snapshot review target. "
            f"repo_head={repo_head_sha} review_target={review_target_sha}. "
            "Create/use a detached target worktree, or pass --allow-head-mismatch for a diagnostic run."
        )
    workspace_name = args.name or f"{snapshot_ref_label(snapshot)}-{target}-{patch}"
    workspace_dir = Path(args.out).expanduser() if args.out else repo_dir / ".review-lab-inputs" / workspace_name
    inputs_dir = workspace_dir / "inputs"
    analysis_dir = snapshot_dir / "analysis"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    instruction_stubs = materialize_local_instruction_stubs(repo_dir) if is_generated_benchmark_worktree(repo_dir) else []

    copied: list[dict[str, str]] = []
    for src in [snapshot_dir / "patch.diff", snapshot_dir / "snapshot.json"]:
        if src.exists():
            dest = inputs_dir / src.name
            write_text_if_changed(dest, safe_read_text(src, max_bytes=20_000_000))
            copied.append({"source": str(src), "dest": path_for_child_manifest(dest, repo_dir)})
    if analysis_dir.exists():
        for src in sorted(analysis_dir.iterdir()):
            if src.suffix.lower() not in {".json", ".md", ".diff", ".txt"}:
                continue
            dest = inputs_dir / "analysis" / src.name
            write_text_if_changed(dest, safe_read_text(src, max_bytes=20_000_000))
            copied.append({"source": str(src), "dest": path_for_child_manifest(dest, repo_dir)})

    context_dest = inputs_dir / "analysis" / "reviewer-context.md"
    if not context_dest.exists():
        legacy_context = snapshot_dir / "reviewer-context.md"
        if legacy_context.exists():
            write_text_if_changed(context_dest, safe_read_text(legacy_context, max_bytes=20_000_000))
            copied.append({"source": str(legacy_context), "dest": path_for_child_manifest(context_dest, repo_dir)})
        else:
            summary, graph_health, obligations = load_snapshot_analysis(snapshot_dir)
            graph_health = dict(graph_health)
            graph_health["snapshot_dir"] = str(snapshot_dir)
            write_text_if_changed(context_dest, format_context_pack(summary, graph_health, obligations))
            copied.append({"source": "generated", "dest": path_for_child_manifest(context_dest, repo_dir)})

    readme_input_lines = [
        f"- Patch: `{path_for_child_manifest(inputs_dir / 'patch.diff', repo_dir)}`",
        f"- Context: `{path_for_child_manifest(context_dest, repo_dir)}`",
    ]
    source_excerpts = inputs_dir / "analysis" / "source-excerpts.md"
    if source_excerpts.exists():
        readme_input_lines.append(
            f"- Source excerpts: `{path_for_child_manifest(source_excerpts, repo_dir)}`"
        )
    symbol_pack = inputs_dir / "analysis" / "graphify-symbol-pack.md"
    if symbol_pack.exists():
        readme_input_lines.append(f"- Symbol pack: `{path_for_child_manifest(symbol_pack, repo_dir)}`")
    else:
        readme_input_lines.append("- Symbol pack: unavailable for this snapshot")

    readme = [
        "# review-lab child workspace",
        "",
        "Source-check inputs only. Do not inspect evaluator directories, goldens, packaged benchmark results, or prior judge outputs.",
        "",
        "Run child Codex with this repository as `--cd` and reference these local files:",
        "",
        *readme_input_lines,
        "",
        "Ignore `.review-lab-inputs/` as harness data, not product source.",
        "",
    ]
    write_text_if_changed(workspace_dir / "README.md", "\n".join(readme))
    manifest = {
        "generated_at": utc_now(),
        "repo_dir": str(repo_dir),
        "repo_head_sha": repo_head_sha,
        "repo_head_matches_review_target": bool(repo_head_sha and review_target_sha and repo_head_sha == review_target_sha),
        "snapshot_dir": str(snapshot_dir),
        "workspace_dir": str(workspace_dir),
        "review_target_sha": snapshot.get("review_target_sha"),
        "patch_hash": snapshot.get("patch_hash"),
        "copied": copied,
        "instruction_stubs": instruction_stubs,
        "note": "Source-check child workspace. Evaluator goldens are intentionally excluded.",
    }
    write_json_if_changed(workspace_dir / "manifest.json", manifest)
    print(workspace_dir)


def graph_node_line(node: dict[str, Any]) -> int | None:
    return line_number(str(node.get("source_location", "")))


def graph_node_matches_path(node: dict[str, Any], path: str) -> bool:
    source_file = str(node.get("source_file") or "")
    node_id = str(node.get("id") or "").lower()
    basename = Path(path).name
    path_fragment = normalized_path_fragment(path)
    stem_fragment = normalized_path_fragment(str(Path(path).with_suffix("")))
    return (
        source_file == path
        or source_file.endswith(path)
        or (source_file == basename and path_fragment in node_id)
        or (source_file == basename and stem_fragment in node_id)
    )


def graph_nodes_for_path(graph: dict[str, Any], path: str) -> tuple[list[dict[str, Any]], str, int]:
    basename = Path(path).name
    basename_nodes = [node for node in graph.get("nodes", []) if str(node.get("source_file") or "") == basename]
    path_nodes = [node for node in basename_nodes if graph_node_matches_path(node, path)]
    if path_nodes:
        return path_nodes, "path-id", len(basename_nodes)
    if basename_nodes:
        return basename_nodes, "basename", len(basename_nodes)
    return [], "none", 0


def graph_node_summary(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": node.get("label"),
        "line": graph_node_line(node),
        "source_file": node.get("source_file"),
    }


def nearest_graph_node(nodes: list[dict[str, Any]], line: int) -> dict[str, Any] | None:
    line_nodes = [(graph_node_line(node), node) for node in nodes]
    positioned = [(node_line, node) for node_line, node in line_nodes if node_line is not None]
    if not positioned:
        return nodes[0] if nodes else None
    before = [(node_line, node) for node_line, node in positioned if node_line <= line]
    if before:
        return max(before, key=lambda item: item[0])[1]
    return min(positioned, key=lambda item: abs(item[0] - line))[1]


def graphify_coverage_entry(
    snapshot_dir: Path,
    graph_json: Path,
    case_id: str,
    mode: str,
    owner_repo: str,
    worktree: str,
) -> dict[str, Any]:
    graph = read_json(graph_json)
    diff_text = safe_read_text(snapshot_dir / "patch.diff", max_bytes=20_000_000)
    hunks_by_file: dict[str, list[DiffHunk]] = {}
    for hunk in parse_diff_hunks(diff_text):
        if is_reviewable_path(hunk.path):
            hunks_by_file.setdefault(hunk.path, []).append(hunk)

    file_rows = []
    for path in sorted(hunks_by_file):
        nodes, match_kind, basename_count = graph_nodes_for_path(graph, path)
        sample_nodes = [graph_node_summary(node) for node in sorted(nodes, key=lambda n: graph_node_line(n) or 0)[:8]]
        sample_hunks = []
        mapped_hunks = 0
        for hunk in hunks_by_file[path]:
            mapped_node = nearest_graph_node(nodes, hunk.new_start)
            if mapped_node is not None:
                mapped_hunks += 1
            sample_hunks.append(
                {
                    "deletion_only": hunk.deletion_only,
                    "mapped_node": graph_node_summary(mapped_node) if mapped_node is not None else None,
                    "new_count": hunk.new_count,
                    "new_start": hunk.new_start,
                    "old_count": hunk.old_count,
                }
            )
        file_rows.append(
            {
                "ambiguous_basename": basename_count > len(nodes),
                "hunks": len(hunks_by_file[path]),
                "mapped_hunks": mapped_hunks,
                "match_kind": match_kind,
                "node_count": len(nodes),
                "path": path,
                "repo_basename_count": basename_count,
                "sample_hunks": sample_hunks[:20],
                "sample_nodes": sample_nodes,
                "status": "unknown",
                "unmapped_hunks": len(hunks_by_file[path]) - mapped_hunks,
            }
        )

    summary = {
        "basename_ambiguous_files": sum(1 for row in file_rows if row["ambiguous_basename"]),
        "changed_files": len(file_rows),
        "files_basename": sum(1 for row in file_rows if row["match_kind"] == "basename"),
        "files_with_graph_nodes": sum(1 for row in file_rows if row["node_count"]),
        "files_without_graph_nodes": sum(1 for row in file_rows if not row["node_count"]),
        "hunks": sum(int(row["hunks"]) for row in file_rows),
        "mapped_hunks": sum(int(row["mapped_hunks"]) for row in file_rows),
        "unmapped_hunks": sum(int(row["unmapped_hunks"]) for row in file_rows),
    }
    snapshot = read_json(snapshot_dir / "snapshot.json")
    return {
        "files": file_rows,
        "graph_json": str(graph_json),
        "id": case_id,
        "mode": mode,
        "owner_repo": owner_repo,
        "review_sha": snapshot.get("review_target_sha") or snapshot.get("head_sha"),
        "summary": summary,
        "worktree": worktree,
    }


def make_graphify_coverage(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    graph_json = Path(args.graph_json).expanduser()
    out_path = Path(args.out).expanduser()
    entry = graphify_coverage_entry(
        snapshot_dir=snapshot_dir,
        graph_json=graph_json,
        case_id=args.case_id,
        mode=args.mode,
        owner_repo=args.owner_repo,
        worktree=args.worktree,
    )
    write_json_if_changed(out_path, [entry])
    print(out_path)


def graphify_cache_owner_key(owner_repo: str) -> str:
    if "/" not in owner_repo:
        raise SystemExit(f"Expected --owner-repo as owner/repo, got {owner_repo!r}")
    owner, repo = owner_repo.split("/", 1)
    return worktree_cache_key(owner, repo)


def clean_source_marker_matches(path: Path, sha: str) -> bool:
    marker = path / ".review-lab-clean-source"
    return path.is_dir() and marker.exists() and marker.read_text(encoding="utf-8").strip() == sha


def ensure_clean_source(repo_dir: Path, owner_key: str, sha: str, force: bool = False) -> Path:
    root = Path.home() / ".cache" / "code-review" / "pr-af-benchmark" / "clean-sources" / owner_key / sha
    if clean_source_marker_matches(root, sha) and not force:
        return root
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    git_proc = subprocess.Popen(
        ["git", "-C", str(repo_dir), "archive", "--format=tar", sha],
        stdout=subprocess.PIPE,
    )
    tar_proc = subprocess.run(["tar", "-x", "-C", str(root)], stdin=git_proc.stdout, check=False)
    if git_proc.stdout is not None:
        git_proc.stdout.close()
    git_rc = git_proc.wait()
    if git_rc != 0 or tar_proc.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        raise subprocess.CalledProcessError(git_rc or tar_proc.returncode, "git archive | tar")
    (root / ".review-lab-clean-source").write_text(sha + "\n", encoding="utf-8")
    return root


def graphify_counts(graph_json: Path) -> dict[str, int]:
    graph = read_json(graph_json)
    counts: dict[str, int] = {}
    for key in ("nodes", "edges", "links", "hyperedges", "communities"):
        value = graph.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value)
    return counts


def graphify_tool_version() -> str:
    proc = subprocess.run(
        ["uvx", "--from", "graphifyy", "graphify", "--version"],
        text=True,
        capture_output=True,
    )
    version = (proc.stdout or proc.stderr).strip()
    return version or "graphify"


def graphify_cache_metadata(
    *,
    owner_repo: str,
    sha: str,
    mode: str,
    source: str,
    command: str,
    graph_json: Path,
    rc: int,
) -> dict[str, Any]:
    return {
        "backend": "graphify",
        "built_at": utc_now(),
        "build_command": command,
        "cache_schema_version": "1",
        "counts": graphify_counts(graph_json),
        "mode": mode,
        "owner_repo": owner_repo,
        "rc": rc,
        "role": "review",
        "sha": sha,
        "source": source,
        "tool_version": graphify_tool_version(),
    }


def graphify_cache_valid(path: Path, metadata_path: Path, owner_repo: str, sha: str, mode: str) -> bool:
    graph_json = path / "graphify-out" / "graph.json"
    if not graph_json.exists() or not metadata_path.exists():
        return False
    metadata = read_json(metadata_path)
    return (
        metadata.get("backend") == "graphify"
        and metadata.get("cache_schema_version") == "1"
        and metadata.get("owner_repo") == owner_repo
        and metadata.get("sha") == sha
        and metadata.get("mode") == mode
        and metadata.get("rc") == 0
    )


def ensure_graphify_cache(args: argparse.Namespace) -> None:
    owner_key = graphify_cache_owner_key(args.owner_repo)
    repo_dir = Path(args.repo).expanduser()
    if not repo_dir.exists():
        raise SystemExit(f"Repo does not exist: {repo_dir}")
    sha = args.sha
    mode = args.mode
    if mode not in {"code-only-no-cluster-clean", "code-only-cluster-clean"}:
        raise SystemExit(f"Unsupported Graphify cache mode: {mode}")

    graph_root = Path.home() / ".cache" / "code-review" / "pr-af-benchmark" / "graphs" / "graphify"
    base_dir = graph_root / owner_key / sha / "code-only-no-cluster-clean"
    cluster_dir = graph_root / owner_key / sha / "code-only-cluster-clean"
    target_dir = cluster_dir if mode == "code-only-cluster-clean" else base_dir
    metadata_path = target_dir / "metadata.json"
    graph_json = target_dir / "graphify-out" / "graph.json"
    if graphify_cache_valid(target_dir, metadata_path, args.owner_repo, sha, mode) and not args.force:
        print(graph_json)
        return

    source_dir = ensure_clean_source(repo_dir, owner_key, sha, force=args.force_clean_source)
    source_note = "git archive clean source, no .review-lab-inputs"

    base_graph = base_dir / "graphify-out" / "graph.json"
    base_metadata = base_dir / "metadata.json"
    if not graphify_cache_valid(base_dir, base_metadata, args.owner_repo, sha, "code-only-no-cluster-clean") or args.force:
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        base_cmd = [
            "uvx",
            "--from",
            "graphifyy",
            "graphify",
            "extract",
            str(source_dir),
            "--code-only",
            "--no-cluster",
            "--out",
            str(base_dir),
        ]
        subprocess.run(base_cmd, check=True)
        write_json_if_changed(
            base_metadata,
            graphify_cache_metadata(
                owner_repo=args.owner_repo,
                sha=sha,
                mode="code-only-no-cluster-clean",
                source=source_note,
                command=" ".join(base_cmd),
                graph_json=base_graph,
                rc=0,
            ),
        )

    if mode == "code-only-no-cluster-clean":
        print(base_graph)
        return

    if cluster_dir.exists():
        shutil.rmtree(cluster_dir)
    shutil.copytree(base_dir / "graphify-out", cluster_dir / "graphify-out")
    cluster_cmd = [
        "uvx",
        "--from",
        "graphifyy",
        "graphify",
        "cluster-only",
        str(cluster_dir),
        "--graph",
        str(cluster_dir / "graphify-out" / "graph.json"),
        "--no-viz",
        "--no-label",
    ]
    subprocess.run(cluster_cmd, check=True)
    write_json_if_changed(
        cluster_dir / "metadata.json",
        graphify_cache_metadata(
            owner_repo=args.owner_repo,
            sha=sha,
            mode="code-only-cluster-clean",
            source=source_note,
            command=" ".join(cluster_cmd),
            graph_json=cluster_dir / "graphify-out" / "graph.json",
            rc=0,
        ),
    )
    write_json_if_changed(cluster_dir / "metadata.base.json", read_json(base_metadata))
    print(cluster_dir / "graphify-out" / "graph.json")


def graphify_health_from_coverage(entry: dict[str, Any]) -> dict[str, Any]:
    summary = entry.get("summary", {})
    changed_files = int(summary.get("changed_files", 0) or 0)
    files_with_nodes = int(summary.get("files_with_graph_nodes", 0) or 0)
    hunks = int(summary.get("hunks", 0) or 0)
    mapped_hunks = int(summary.get("mapped_hunks", 0) or 0)
    unmapped_hunks = int(summary.get("unmapped_hunks", 0) or 0)
    if changed_files and files_with_nodes == 0:
        status = "failed-empty"
    elif unmapped_hunks or mapped_hunks < hunks:
        status = "partial"
    else:
        status = "ok"
    return {
        "backend": "graphify",
        "graph_present": True,
        "status": status,
        "changed_files": changed_files,
        "changed_runtime_files": changed_files,
        "changed_symbols": sum(int(file_info.get("node_count", 0) or 0) for file_info in entry.get("files", [])),
        "mapped_hunks": mapped_hunks,
        "unmapped_hunks": unmapped_hunks,
        "files_with_graph_nodes": files_with_nodes,
        "files_without_graph_nodes": int(summary.get("files_without_graph_nodes", 0) or 0),
        "graph_json": entry.get("graph_json"),
        "mode": entry.get("mode"),
    }


def attach_graphify_coverage(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    coverage_path = Path(args.coverage).expanduser()
    entries = read_json(coverage_path)
    if not isinstance(entries, list):
        raise SystemExit(f"Expected list in {coverage_path}")
    selected = None
    for entry in entries:
        if args.case_id and entry.get("id") != args.case_id:
            continue
        if args.mode and entry.get("mode") != args.mode and not args.graph_json_override:
            continue
        selected = entry
        break
    if selected is None:
        raise SystemExit(f"No matching Graphify coverage entry for case={args.case_id!r} mode={args.mode!r}")
    selected = dict(selected)
    if args.graph_json_override:
        selected["graph_json"] = str(Path(args.graph_json_override).expanduser())
        selected["mode"] = args.mode
    analysis_dir = snapshot_dir / "analysis"
    write_json_if_changed(analysis_dir / "graphify-coverage.json", selected)
    write_json_if_changed(analysis_dir / "graph-health.json", graphify_health_from_coverage(selected))
    print(analysis_dir / "graphify-coverage.json")


def graphify_changed_nodes(coverage: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for file_info in coverage.get("files", []):
        for hunk in file_info.get("sample_hunks", []):
            node = hunk.get("mapped_node") or {}
            label = node.get("label")
            if not label:
                continue
            key = (str(file_info.get("path", "")), str(label), int(node.get("line", 0) or 0))
            if key in seen:
                continue
            seen.add(key)
            nodes.append(
                {
                    "path": file_info.get("path"),
                    "label": label,
                    "source_file": node.get("source_file"),
                    "line": node.get("line"),
                }
            )
            if len(nodes) >= limit:
                return nodes
    return nodes


def line_number(source_location: str) -> int | None:
    match = re.search(r"L(\d+)", str(source_location))
    if not match:
        return None
    return int(match.group(1))


def normalized_path_fragment(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")


def resolve_graph_node(graph: dict[str, Any], mapped: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    label = mapped.get("label")
    path = str(mapped.get("path") or "")
    source_file = str(mapped.get("source_file") or "")
    target_line = int(mapped.get("line") or 0)
    path_fragment = normalized_path_fragment(path)
    candidates = []
    for node in graph.get("nodes", []):
        if node.get("label") != label:
            continue
        score = 0
        node_source = str(node.get("source_file") or "")
        node_id = str(node.get("id") or "").lower()
        node_line = line_number(str(node.get("source_location", "")))
        if source_file and node_source == source_file:
            score += 3
        if path and (node_source == path or node_source.endswith(path)):
            score += 5
        if target_line and node_line == target_line:
            score += 3
        if path_fragment and path_fragment in node_id:
            score += 5
        candidates.append((score, node))
    if not candidates:
        return None, []
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best = candidates[0]
    ambiguity = []
    if len(candidates) > 1 and candidates[1][0] == best_score:
        ambiguity = [str(item[1].get("id")) for item in candidates[:5]]
    return best, ambiguity


def graph_neighbors(graph: dict[str, Any], node_id: str, max_connections: int = 20) -> list[str]:
    nodes_by_id = {str(node.get("id")): node for node in graph.get("nodes", [])}
    connections = []
    for edge in graph.get("edges", graph.get("links", [])):
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source == node_id:
            neighbor = nodes_by_id.get(target, {})
            connections.append(("-->", neighbor, edge))
        elif target == node_id:
            neighbor = nodes_by_id.get(source, {})
            connections.append(("<--", neighbor, edge))
    connections.sort(key=lambda item: str(item[1].get("label", "")))
    lines = []
    for arrow, neighbor, edge in connections[:max_connections]:
        lines.append(
            f"  {arrow} {neighbor.get('label', edge.get('target'))} "
            f"[{edge.get('relation', '')}] [{edge.get('confidence', '')}]"
        )
    if len(connections) > max_connections:
        lines.append(f"  ... and {len(connections) - max_connections} more")
    return lines


def format_graph_node(graph: dict[str, Any], mapped: dict[str, Any]) -> str:
    node, ambiguity = resolve_graph_node(graph, mapped)
    if node is None:
        return f"No graph node resolved for {mapped.get('label')} at {mapped.get('path')}:{mapped.get('line')}"
    node_id = str(node.get("id"))
    neighbors = graph_neighbors(graph, node_id)
    lines = [
        f"Node: {node.get('label', node_id)}",
        f"  ID:        {node_id}",
        f"  Source:    {node.get('source_file', '')} {node.get('source_location', '')}".rstrip(),
        f"  Type:      {node.get('file_type', '')}",
    ]
    if ambiguity:
        lines.append("  Ambiguous candidates with equal score:")
        lines.extend(f"    - {candidate}" for candidate in ambiguity)
    if neighbors:
        lines.append("")
        lines.append(f"Connections ({len(neighbors)} shown):")
        lines.extend(neighbors)
    return "\n".join(lines)


def make_graphify_symbol_pack(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    coverage = read_json(snapshot_dir / "analysis" / "graphify-coverage.json")
    graph_json = coverage.get("graph_json")
    if not graph_json:
        raise SystemExit("Attached Graphify coverage has no graph_json path")
    graph = read_json(Path(str(graph_json)).expanduser())
    parts = [
        "# Graphify Symbol Pack",
        "",
        "Focused graph node output for symbols mapped from changed hunks.",
        "",
    ]
    for mapped in graphify_changed_nodes(coverage, args.limit):
        label = mapped.get("label")
        parts.extend([f"## `{label}`", "", f"Mapped from `{mapped.get('path')}:{mapped.get('line')}`.", "", "```text", format_graph_node(graph, mapped), "```", ""])
    out_path = Path(args.out).expanduser() if args.out else snapshot_dir / "analysis" / "graphify-symbol-pack.md"
    write_text_if_changed(out_path, "\n".join(parts).rstrip() + "\n")
    print(out_path)


def audit_review(args: argparse.Namespace) -> None:
    snapshot_dir = Path(args.snapshot_dir).expanduser()
    review_path = Path(args.review).expanduser()
    out_path = Path(args.out).expanduser()
    _, graph_health, obligations = load_snapshot_analysis(snapshot_dir)
    review_text = review_path.read_text(encoding="utf-8")
    review_terms = token_set(review_text)
    review_identifiers = identifier_set(review_text)
    seed_rows = []
    for seed in obligations.get("seeds", []):
        terms = seed_terms(seed)
        identifiers = identifier_set(str(seed.get("snippet", "")))
        score = coverage_score(terms, review_terms)
        identifier_score = coverage_score(identifiers, review_identifiers)
        status = classify_audit_status(score, identifier_score, identifiers)
        seed_rows.append(
            {
                "where": seed.get("where"),
                "category": seed.get("category"),
                "snippet": seed.get("snippet"),
                "coverage_score": score,
                "identifier_score": identifier_score,
                "matched_terms": sorted(terms & review_terms)[:20],
                "missing_terms": sorted(terms - review_terms)[:20],
                "matched_identifiers": sorted(identifiers & review_identifiers)[:20],
                "missing_identifiers": sorted(identifiers - review_identifiers)[:20],
                "status": status,
            }
        )
    weak = [row for row in seed_rows if row["status"] == "weak-or-missing"]
    golden_rows = []
    if args.goldens:
        goldens_payload = read_json(Path(args.goldens).expanduser())
        for golden in goldens_payload.get("goldens", []):
            terms = golden_terms(golden)
            identifiers = identifier_set(str(golden.get("comment", "")))
            score = coverage_score(terms, review_terms)
            identifier_score = coverage_score(identifiers, review_identifiers)
            golden_rows.append(
                {
                    "comment": golden.get("comment"),
                    "severity": golden.get("severity"),
                    "coverage_score": score,
                    "identifier_score": identifier_score,
                    "matched_terms": sorted(terms & review_terms)[:30],
                    "missing_terms": sorted(terms - review_terms)[:30],
                    "matched_identifiers": sorted(identifiers & review_identifiers)[:30],
                    "missing_identifiers": sorted(identifiers - review_identifiers)[:30],
                    "heuristic_status": classify_golden_status(score, identifier_score, identifiers),
                }
            )
    audit = {
        "generated_at": utc_now(),
        "review_path": str(review_path),
        "snapshot_dir": str(snapshot_dir),
        "graph_health": graph_health,
        "obligation_summary": {
            "total": len(seed_rows),
            "weak_or_missing": len(weak),
            "touched": len(seed_rows) - len(weak),
        },
        "weak_obligations": weak[:40],
        "golden_heuristics": golden_rows,
        "note": (
            "Deterministic audit only. Low coverage means the existing review text did not share many "
            "terms with a seed/golden; it is a triage signal, not a semantic judge."
        ),
    }
    write_json_if_changed(out_path, audit)
    print(out_path)


def make_eval_payload(args: argparse.Namespace) -> None:
    review_path = Path(args.review).expanduser()
    goldens_path = Path(args.goldens).expanduser()
    out_path = Path(args.out).expanduser()
    review_text = review_path.read_text(encoding="utf-8")
    goldens_payload = read_json(goldens_path)
    payload = {
        "generated_at": utc_now(),
        "case_id": args.case_id or goldens_payload.get("case_id"),
        "review": {
            "path": str(review_path),
            "sha256": hash_text(review_text),
            "text": review_text,
        },
        "goldens": goldens_payload.get("goldens", []),
        "goldens_hash": goldens_payload.get("goldens_hash"),
        "judge_contract": {
            "blind_review_required": True,
            "instruction": (
                "Compare the completed review against each golden comment. "
                "Mark a golden as hit only when the review identifies the same "
                "underlying defect and consequence, even if wording or severity differs. "
                "Do not penalize additional valid findings just because they are not goldens."
            ),
        },
    }
    write_json_if_changed(out_path, payload)
    materialize_local_instruction_stubs(out_path.parent)
    print(out_path)


def parse_recall(text: str) -> tuple[int, int] | None:
    saw_recall_heading = False
    for line in text.splitlines():
        cleaned = line.strip().strip("*").strip()
        if not cleaned:
            continue
        inline = re.search(r"^(?:Final\s+)?Recall\b[^0-9]*(\d+)\s*/\s*(\d+)\b", cleaned)
        if inline:
            return int(inline.group(1)), int(inline.group(2))
        if re.search(r"\bRecall\b", cleaned, flags=re.IGNORECASE):
            saw_recall_heading = True
            continue
        if saw_recall_heading:
            heading_value = re.search(r"\b(\d+)\s*/\s*(\d+)\b", cleaned)
            if heading_value:
                return int(heading_value.group(1)), int(heading_value.group(2))
    return None


def normalize_judge_status(status: str) -> str:
    normalized = status.upper()
    if normalized == "MATCHED":
        return "HIT"
    if normalized == "MISSED":
        return "MISS"
    return normalized


def parse_golden_match_lines(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_verdict_table = False
    table_row_index = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [cell.strip().strip("*") for cell in line.strip("|").split("|")]
            if len(cells) >= 2:
                if "golden" in cells[0].lower() and "verdict" in cells[1].lower():
                    in_verdict_table = True
                    table_row_index = 0
                    continue
                if set(cells[0]) <= {"-", ":"}:
                    continue
                id_match = re.match(
                    r"^(?:Golden\s*)?G?(\d+)\.?$",
                    cells[0],
                    flags=re.IGNORECASE,
                )
                status = cells[1].strip()
                if re.match(r"^(?:HIT|MISS|MATCHED|MISSED)$", status, flags=re.IGNORECASE):
                    if id_match:
                        golden_id = f"G{id_match.group(1)}"
                    elif in_verdict_table:
                        table_row_index += 1
                        golden_id = f"G{table_row_index}"
                    else:
                        continue
                    rows.append(
                        {
                            "golden_id": golden_id,
                            "status": normalize_judge_status(status),
                            "note": cells[2].strip() if len(cells) > 2 else "",
                        }
                    )
            continue
        line = re.sub(r"^\s*[-*]\s*", "", line)
        line = line.replace("**", "")
        match = re.match(
            r"(?:Golden\s+)?(G?[0-9A-Za-z_.-]+):\s*([A-Za-z]+)\b\s*(?:[-\u2014.]\s*)?(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            golden_id, status, note = match.groups()
            if golden_id.isdigit():
                golden_id = f"G{golden_id}"
            elif not golden_id.upper().startswith("G"):
                golden_id = f"G{golden_id}"
            else:
                golden_id = golden_id.upper()
        else:
            match = re.match(
                r"(?:Golden\s+)?(\d+)\.?\s*(?:[:\-]\s*)?([A-Za-z]+)\b\s*(?:[-\u2014.]\s*)?(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            index, status, note = match.groups()
            golden_id = f"G{index}"
        rows.append(
            {
                "golden_id": golden_id,
                "status": normalize_judge_status(status),
                "note": note.strip(),
            }
        )
    return rows


def summarize_union_recall(case_row: dict[str, Any]) -> dict[str, Any]:
    hit_matches: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()
    total = 0
    for judge in case_row["judges"]:
        total = max(total, judge["total"])
        for match in judge["golden_matches"]:
            golden_id = match["golden_id"]
            seen_ids.add(golden_id)
            if match["status"] in {"HIT", "MATCHED"} and golden_id not in hit_matches:
                hit_matches[golden_id] = match

    if not hit_matches and case_row["best"]:
        hits = case_row["best"]["hits"]
    else:
        hits = min(len(hit_matches), total)

    return {
        "hits": hits,
        "total": total,
        "recall": hits / total if total else 0.0,
        "hit_ids": sorted(hit_matches),
        "seen_ids": sorted(seen_ids),
        "golden_matches": [hit_matches[key] for key in sorted(hit_matches)],
    }


def summarize_results(args: argparse.Namespace) -> None:
    cases_root = Path(args.cases_root or (Path(args.cache_root).expanduser() / "cases")).expanduser()
    out_path = Path(args.out).expanduser() if args.out else None
    judge_paths = sorted(cases_root.glob("*/evaluator/*codex-judge.md"))
    cases: dict[str, dict[str, Any]] = {}
    for judge_path in judge_paths:
        text = judge_path.read_text(encoding="utf-8")
        recall = parse_recall(text)
        if recall is None:
            continue
        hits, total = recall
        case_id = judge_path.parent.parent.name
        row = {
            "judge_path": str(judge_path),
            "judge_file": judge_path.name,
            "hits": hits,
            "total": total,
            "recall": hits / total if total else 0.0,
            "golden_matches": parse_golden_match_lines(text),
        }
        case_row = cases.setdefault(case_id, {"case_id": case_id, "judges": [], "best": None})
        case_row["judges"].append(row)
        best = case_row["best"]
        if best is None or (row["recall"], row["hits"], row["judge_file"]) > (
            best["recall"],
            best["hits"],
            best["judge_file"],
        ):
            case_row["best"] = row

    ordered_cases = [cases[key] for key in sorted(cases)]
    for case in ordered_cases:
        case["union"] = summarize_union_recall(case)
    best_hits = sum(case["best"]["hits"] for case in ordered_cases if case["best"])
    best_total = sum(case["best"]["total"] for case in ordered_cases if case["best"])
    union_hits = sum(case["union"]["hits"] for case in ordered_cases)
    union_total = sum(case["union"]["total"] for case in ordered_cases)
    summary = {
        "generated_at": utc_now(),
        "cases_root": str(cases_root),
        "case_count": len(ordered_cases),
        "judge_count": sum(len(case["judges"]) for case in ordered_cases),
        "best_hits": best_hits,
        "best_total": best_total,
        "best_recall": best_hits / best_total if best_total else 0.0,
        "union_hits": union_hits,
        "union_total": union_total,
        "union_recall": union_hits / union_total if union_total else 0.0,
        "cases": ordered_cases,
    }
    if out_path:
        write_json_if_changed(out_path, summary)

    if args.format == "json":
        rendered = json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True)
    else:
        lines = [
            f"Best parseable recall: {best_hits}/{best_total}",
            f"Union parseable recall: {union_hits}/{union_total}",
            "",
            "| Case | Best recall | Union recall | Judge | All recalls |",
            "| --- | ---: | ---: | --- | --- |",
        ]
        for case in ordered_cases:
            best = case["best"]
            union = case["union"]
            all_recalls = ", ".join(
                f"{judge['hits']}/{judge['total']}:{judge['judge_file']}" for judge in case["judges"]
            )
            lines.append(
                f"| {case['case_id']} | {best['hits']}/{best['total']} | "
                f"{union['hits']}/{union['total']} | "
                f"{best['judge_file']} | {all_recalls} |"
            )
        rendered = "\n".join(lines)
    print(rendered)


def hit_ids_from_matches(matches: list[dict[str, str]]) -> set[str]:
    return {
        match["golden_id"]
        for match in matches
        if normalize_judge_status(match.get("status", "")) == "HIT"
    }


def variant_deltas(args: argparse.Namespace) -> None:
    summary_path = Path(args.summary or (Path(args.cache_root).expanduser() / "summary.json")).expanduser()
    out_path = Path(args.out).expanduser() if args.out else None
    summary = read_json(summary_path)
    judge_file = args.judge_file
    rows: list[dict[str, Any]] = []
    for case in summary.get("cases", []):
        variant_judges = [judge for judge in case.get("judges", []) if judge.get("judge_file") == judge_file]
        if not variant_judges:
            continue
        variant = max(
            variant_judges,
            key=lambda judge: (judge.get("recall", 0.0), judge.get("hits", 0), judge.get("judge_file", "")),
        )
        other_judges = [judge for judge in case.get("judges", []) if judge is not variant]
        other_best = (
            max(
                other_judges,
                key=lambda judge: (judge.get("recall", 0.0), judge.get("hits", 0), judge.get("judge_file", "")),
            )
            if other_judges
            else None
        )
        variant_hits = hit_ids_from_matches(variant.get("golden_matches", []))
        other_hit_ids: set[str] = set()
        for judge in other_judges:
            other_hit_ids.update(hit_ids_from_matches(judge.get("golden_matches", [])))
        other_best_hits = hit_ids_from_matches(other_best.get("golden_matches", [])) if other_best else set()
        unique_to_variant = sorted(variant_hits - other_hit_ids)
        missed_from_other_union = sorted(other_hit_ids - variant_hits)
        recovered_vs_other_best = sorted(variant_hits - other_best_hits)
        lost_vs_other_best = sorted(other_best_hits - variant_hits)
        rows.append(
            {
                "case_id": case["case_id"],
                "variant": {
                    "hits": variant.get("hits", 0),
                    "total": variant.get("total", 0),
                    "recall": variant.get("recall", 0.0),
                    "judge_file": variant.get("judge_file", ""),
                },
                "other_best": {
                    "hits": other_best.get("hits", 0) if other_best else 0,
                    "total": other_best.get("total", variant.get("total", 0)) if other_best else variant.get("total", 0),
                    "recall": other_best.get("recall", 0.0) if other_best else 0.0,
                    "judge_file": other_best.get("judge_file", "") if other_best else "",
                },
                "other_union": {
                    "hits": len(other_hit_ids),
                    "total": variant.get("total", 0),
                },
                "delta_vs_other_best": variant.get("hits", 0) - (other_best.get("hits", 0) if other_best else 0),
                "unique_to_variant": unique_to_variant,
                "missed_from_other_union": missed_from_other_union,
                "recovered_vs_other_best": recovered_vs_other_best,
                "lost_vs_other_best": lost_vs_other_best,
                "trade": bool(recovered_vs_other_best and lost_vs_other_best),
            }
        )

    variant_hits_total = sum(row["variant"]["hits"] for row in rows)
    variant_total = sum(row["variant"]["total"] for row in rows)
    other_best_hits_total = sum(row["other_best"]["hits"] for row in rows)
    other_best_total = sum(row["other_best"]["total"] for row in rows)
    report = {
        "generated_at": utc_now(),
        "summary_path": str(summary_path),
        "judge_file": judge_file,
        "case_count": len(rows),
        "variant_hits": variant_hits_total,
        "variant_total": variant_total,
        "variant_recall": variant_hits_total / variant_total if variant_total else 0.0,
        "other_best_hits": other_best_hits_total,
        "other_best_total": other_best_total,
        "other_best_recall": other_best_hits_total / other_best_total if other_best_total else 0.0,
        "unique_to_variant_count": sum(len(row["unique_to_variant"]) for row in rows),
        "missed_from_other_union_count": sum(len(row["missed_from_other_union"]) for row in rows),
        "trade_count": sum(1 for row in rows if row["trade"]),
        "rows": rows,
    }
    if out_path:
        write_json_if_changed(out_path, report)

    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True)
    else:
        lines = [
            f"Variant: `{judge_file}`",
            f"Cases: {report['case_count']}",
            f"Variant recall on variant-run cases: {variant_hits_total}/{variant_total}",
            f"Other-best recall on same cases: {other_best_hits_total}/{other_best_total}",
            f"Unique-to-variant hits: {report['unique_to_variant_count']}",
            f"Missed hits found by other runs: {report['missed_from_other_union_count']}",
            f"Trade cases: {report['trade_count']}",
            "",
            "| Case | Variant | Other best | Delta | Unique to variant | Missed from other union | Trade |",
            "| --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                f"| {row['case_id']} | {row['variant']['hits']}/{row['variant']['total']} | "
                f"{row['other_best']['hits']}/{row['other_best']['total']} | "
                f"{row['delta_vs_other_best']:+d} | "
                f"{', '.join(row['unique_to_variant']) or '-'} | "
                f"{', '.join(row['missed_from_other_union']) or '-'} | "
                f"{'yes' if row['trade'] else 'no'} |"
            )
        rendered = "\n".join(lines)
    print(rendered)


def latest_target_alignment(evaluator_dir: Path) -> dict[str, Any] | None:
    paths = sorted(evaluator_dir.glob("target-alignment-*.json"), key=lambda path: path.stat().st_mtime)
    if not paths:
        return None
    return read_json(paths[-1])


def load_remaining_miss_annotations(path_arg: str | None) -> dict[str, dict[str, Any]]:
    path = Path(path_arg).expanduser() if path_arg else DEFAULT_REMAINING_MISS_ANNOTATIONS
    if not path.exists():
        return {}
    payload = read_json(path)
    rows = payload.get("misses", [])
    annotations: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        golden_id = row.get("golden_id")
        if not case_id or not golden_id:
            continue
        annotations[f"{case_id}/{golden_id}"] = row
    return annotations


def remaining_misses(args: argparse.Namespace) -> None:
    cases_root = Path(args.cases_root or (Path(args.cache_root).expanduser() / "cases")).expanduser()
    out_path = Path(args.out).expanduser() if args.out else None
    annotations = load_remaining_miss_annotations(args.annotations)

    case_rows: dict[str, dict[str, Any]] = {}
    for judge_path in sorted(cases_root.glob("*/evaluator/*codex-judge.md")):
        text = judge_path.read_text(encoding="utf-8")
        recall = parse_recall(text)
        if recall is None:
            continue
        hits, total = recall
        case_id = judge_path.parent.parent.name
        row = {
            "judge_path": str(judge_path),
            "judge_file": judge_path.name,
            "hits": hits,
            "total": total,
            "recall": hits / total if total else 0.0,
            "golden_matches": parse_golden_match_lines(text),
        }
        case_row = case_rows.setdefault(case_id, {"case_id": case_id, "judges": [], "best": None})
        case_row["judges"].append(row)
        best = case_row["best"]
        if best is None or (row["recall"], row["hits"], row["judge_file"]) > (
            best["recall"],
            best["hits"],
            best["judge_file"],
        ):
            case_row["best"] = row

    cases = []
    for case_id in sorted(case_rows):
        case = case_rows[case_id]
        case["union"] = summarize_union_recall(case)
        if case["union"]["hits"] >= case["union"]["total"]:
            continue
        evaluator_dir = cases_root / case_id / "evaluator"
        goldens_path = evaluator_dir / "pr-af-goldens.json"
        goldens = read_json(goldens_path).get("goldens", []) if goldens_path.exists() else []
        alignment = latest_target_alignment(evaluator_dir)
        alignment_rows = alignment.get("golden_alignment", []) if alignment else []
        hit_ids = set(case["union"].get("hit_ids", []))
        misses = []
        for index, golden in enumerate(goldens, start=1):
            golden_id = f"G{index}"
            if golden_id in hit_ids:
                continue
            judge_notes = []
            for judge in case["judges"]:
                for match in judge["golden_matches"]:
                    if match["golden_id"] == golden_id:
                        judge_notes.append(
                            {
                                "judge_file": judge["judge_file"],
                                "status": match["status"],
                                "note": match["note"],
                            }
                        )
            alignment_row = alignment_rows[index - 1] if index - 1 < len(alignment_rows) else {}
            annotation = annotations.get(f"{case_id}/{golden_id}", {})
            misses.append(
                {
                    "golden_id": golden_id,
                    "comment": golden.get("comment", ""),
                    "severity": golden.get("severity"),
                    "alignment_status": alignment_row.get("status"),
                    "target_identifier_score": alignment_row.get("target_identifier_score"),
                    "target_term_score": alignment_row.get("target_term_score"),
                    "assessment": annotation.get("assessment"),
                    "category": annotation.get("category"),
                    "next_action": annotation.get("next_action"),
                    "annotation_note": annotation.get("note"),
                    "judge_notes": judge_notes,
                }
            )
        cases.append(
            {
                "case_id": case_id,
                "best": {"hits": case["best"]["hits"], "total": case["best"]["total"]},
                "union": {"hits": case["union"]["hits"], "total": case["union"]["total"]},
                "misses": misses,
            }
        )

    report = {
        "generated_at": utc_now(),
        "cases_root": str(cases_root),
        "case_count": len(cases),
        "miss_count": sum(len(case["misses"]) for case in cases),
        "cases": cases,
    }
    if out_path:
        write_json_if_changed(out_path, report)

    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True)
    else:
        lines = [
            f"Remaining miss cases: {report['case_count']}",
            f"Remaining missed goldens: {report['miss_count']}",
            "",
            "| Case | Best | Union | Golden | Severity | Alignment | Assessment | Comment |",
            "| --- | ---: | ---: | --- | --- | --- | --- | --- |",
        ]
        for case in cases:
            for miss in case["misses"]:
                comment = str(miss["comment"]).replace("|", "\\|")
                assessment = str(miss.get("assessment") or miss.get("category") or "").replace("|", "\\|")
                lines.append(
                    f"| {case['case_id']} | {case['best']['hits']}/{case['best']['total']} | "
                    f"{case['union']['hits']}/{case['union']['total']} | {miss['golden_id']} | "
                    f"{miss.get('severity') or ''} | {miss.get('alignment_status') or ''} | "
                    f"{assessment} | {comment} |"
                )
        rendered = "\n".join(lines)
    print(rendered)


DO_NOT_TUNE_CATEGORIES = {
    "contradicted-golden",
    "low-value-side-effect",
    "low-value-style",
    "low-value-test-contract",
    "low-value-test-style",
    "misattached-or-stale",
    "source-rejected-low-value",
    "stale-golden",
    "weak-golden",
}

ADJUDICATION_CATEGORIES = {
    "contradicted-golden",
    "imprecise-golden",
    "misattached-or-stale",
    "overbroad-golden",
    "stale-golden",
    "weak-golden",
}


def write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def build_outtake(args: argparse.Namespace) -> None:
    cache_root = Path(args.cache_root).expanduser()
    summary_path = Path(args.summary).expanduser() if args.summary else cache_root / "summary.json"
    remaining_path = (
        Path(args.remaining).expanduser() if args.remaining else cache_root / "remaining-misses.json"
    )
    out_path = Path(args.out).expanduser() if args.out else None

    summary = read_json(summary_path)
    remaining = read_json(remaining_path)

    misses: list[dict[str, Any]] = []
    for case in remaining.get("cases", []):
        for miss in case.get("misses", []):
            misses.append(
                {
                    "case_id": case.get("case_id"),
                    "golden_id": miss.get("golden_id"),
                    "category": miss.get("category") or "uncategorized",
                    "assessment": miss.get("assessment") or "",
                    "next_action": miss.get("next_action") or "",
                    "severity": miss.get("severity") or "",
                    "alignment_status": miss.get("alignment_status") or "",
                    "comment": miss.get("comment") or "",
                }
            )

    category_counts = Counter(miss["category"] for miss in misses)
    assessment_counts = Counter(miss["assessment"] for miss in misses if miss["assessment"])
    remaining_by_case = Counter(miss["case_id"] for miss in misses)
    annotated_count = sum(1 for miss in misses if miss["category"] != "uncategorized")
    do_not_tune_count = sum(1 for miss in misses if miss["category"] in DO_NOT_TUNE_CATEGORIES)
    adjudication_count = sum(1 for miss in misses if miss["category"] in ADJUDICATION_CATEGORIES)
    prompt_candidate_count = sum(
        1
        for miss in misses
        if miss["category"] not in DO_NOT_TUNE_CATEGORIES
        and miss["category"] not in ADJUDICATION_CATEGORIES
    )

    payload = {
        "generated_at": utc_now(),
        "summary_path": str(summary_path),
        "remaining_path": str(remaining_path),
        "score": {
            "best_hits": summary.get("best_hits"),
            "best_total": summary.get("best_total"),
            "union_hits": summary.get("union_hits"),
            "union_total": summary.get("union_total"),
            "case_count": summary.get("case_count"),
            "judge_count": summary.get("judge_count"),
        },
        "remaining": {
            "case_count": remaining.get("case_count"),
            "miss_count": remaining.get("miss_count"),
            "annotated_count": annotated_count,
            "category_counts": dict(sorted(category_counts.items())),
            "assessment_counts": dict(sorted(assessment_counts.items())),
            "case_counts": dict(sorted(remaining_by_case.items())),
        },
        "outtake": {
            "do_not_tune_count": do_not_tune_count,
            "adjudication_count": adjudication_count,
            "prompt_candidate_count": prompt_candidate_count,
            "note": (
                "Prompt candidates are misses not already categorized as do-not-tune "
                "or adjudication rows. Zero means more benchmark tuning is unlikely "
                "to improve source-review quality without manual benchmark cleanup."
            ),
        },
        "misses": misses,
    }

    if args.format == "json":
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    else:
        score = payload["score"]
        if prompt_candidate_count:
            next_action = (
                "Work the source-backed prompt-improvement candidates first. Keep "
                "adjudication and do-not-tune rows separate so benchmark-quality "
                "noise does not drive reviewer behavior."
            )
        else:
            next_action = (
                "Do not tune the main reviewer against the remaining rows without "
                "manual benchmark adjudication. The cached evidence currently points "
                "to stale, contradicted, misattached, imprecise, or low-value rows."
            )
        lines = [
            "# Review Lab Outtake",
            "",
            f"Best parseable recall: {score['best_hits']}/{score['best_total']}",
            f"Union parseable recall: {score['union_hits']}/{score['union_total']}",
            f"Cases / judges: {score['case_count']} / {score['judge_count']}",
            "",
            f"Remaining: {remaining.get('case_count')} cases, {remaining.get('miss_count')} misses, "
            f"{annotated_count} annotated.",
            f"Prompt-improvement candidates: {prompt_candidate_count}",
            f"Adjudication/benchmark-quality rows: {adjudication_count}",
            f"Do-not-tune rows: {do_not_tune_count}",
            "",
            "## Remaining Categories",
            "",
            "| Category | Count |",
            "| --- | ---: |",
        ]
        for category, count in sorted(category_counts.items()):
            lines.append(f"| {category} | {count} |")
        lines.extend(
            [
                "",
                "## Remaining Cases",
                "",
                "| Case | Misses | Categories |",
                "| --- | ---: | --- |",
            ]
        )
        for case_id, count in sorted(remaining_by_case.items()):
            categories = sorted({miss["category"] for miss in misses if miss["case_id"] == case_id})
            lines.append(f"| {case_id} | {count} | {', '.join(categories)} |")
        lines.extend(
            [
                "",
                "## Next Action",
                "",
                next_action,
            ]
        )
        rendered = "\n".join(lines)

    if out_path:
        if args.format == "json":
            write_json_if_changed(out_path, payload)
        else:
            write_text_if_changed(out_path, rendered)
    print(rendered)


def benchmark_status(args: argparse.Namespace) -> None:
    problems_path = Path(args.problems).expanduser()
    cache_root = Path(args.cache_root).expanduser()
    summary_path = Path(args.summary).expanduser() if args.summary else cache_root / "summary.json"
    out_path = Path(args.out).expanduser() if args.out else None

    problems = read_json(problems_path)
    if not isinstance(problems, list):
        raise SystemExit(f"Expected a list of problems in {problems_path}")
    summary = read_json(summary_path) if summary_path.exists() else {"cases": []}
    summary_cases = {case["case_id"]: case for case in summary.get("cases", [])}

    rows: list[dict[str, Any]] = []
    for problem in problems:
        problem_id = str(problem.get("id") or "")
        case_id = slugify(problem_id)
        goldens = problem_goldens(problem)
        summary_case = summary_cases.get(case_id)
        rows.append(
            {
                "id": problem_id,
                "case_id": case_id,
                "repo": problem.get("repo"),
                "url": problem.get("pr_url"),
                "language": problem.get("language"),
                "num_files": problem.get("num_files"),
                "golden_count": len(goldens),
                "severity_mix": problem.get("severity_mix") or Counter(
                    str(golden.get("severity") or "unknown") for golden in goldens
                ),
                "judged": summary_case is not None,
                "best": summary_case.get("best") if summary_case else None,
                "union": summary_case.get("union") if summary_case else None,
                "judge_count": len(summary_case.get("judges", [])) if summary_case else 0,
            }
        )

    judged = [row for row in rows if row["judged"]]
    unjudged = [row for row in rows if not row["judged"]]
    payload = {
        "generated_at": utc_now(),
        "problems_path": str(problems_path),
        "summary_path": str(summary_path),
        "problem_count": len(rows),
        "judged_count": len(judged),
        "unjudged_count": len(unjudged),
        "judged_golden_count": sum(row["golden_count"] for row in judged),
        "unjudged_golden_count": sum(row["golden_count"] for row in unjudged),
        "rows": rows,
    }

    if args.format == "json":
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    else:
        lines = [
            "# PR-AF Benchmark Status",
            "",
            f"Problems: {len(rows)}",
            f"Judged: {len(judged)} cases / {payload['judged_golden_count']} goldens",
            f"Unjudged: {len(unjudged)} cases / {payload['unjudged_golden_count']} goldens",
            "",
            "## Unjudged Cases",
            "",
            "| Case | Repo | Files | Goldens | Severity | URL |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
        for row in unjudged:
            severity = row["severity_mix"]
            if isinstance(severity, dict):
                severity_text = ", ".join(f"{key}:{value}" for key, value in sorted(severity.items()))
            else:
                severity_text = str(severity or "")
            url = str(row.get("url") or "")
            lines.append(
                f"| {row['case_id']} | {row.get('repo') or ''} | {row.get('num_files') or ''} | "
                f"{row['golden_count']} | {severity_text} | {url} |"
            )
        rendered = "\n".join(lines)

    if out_path:
        if args.format == "json":
            write_json_if_changed(out_path, payload)
        else:
            write_text_if_changed(out_path, rendered)
    print(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-pr-af-subset")
    prepare.add_argument("--problems", default=str(DEFAULT_PR_AF_PROBLEMS))
    prepare.add_argument("--limit", type=int, default=5)
    prepare.add_argument("--id", action="append", default=[])
    prepare.set_defaults(func=prepare_pr_af_subset)

    fetch = subparsers.add_parser("fetch-pr")
    fetch.add_argument("pr_url")
    fetch.set_defaults(func=fetch_pr)

    fetch_commit_cmd = subparsers.add_parser("fetch-commit")
    fetch_commit_cmd.add_argument("commit_url")
    fetch_commit_cmd.set_defaults(func=fetch_commit)

    analyze = subparsers.add_parser("analyze-diff")
    analyze.add_argument("--diff", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--graph-json")
    analyze.set_defaults(func=analyze_diff)

    context = subparsers.add_parser("make-context-pack")
    context.add_argument("--snapshot-dir", required=True)
    context.add_argument("--out")
    context.set_defaults(func=make_context_pack)

    excerpts = subparsers.add_parser("make-source-excerpt-pack")
    excerpts.add_argument("--snapshot-dir", required=True)
    excerpts.add_argument("--repo", required=True)
    excerpts.add_argument("--out")
    excerpts.add_argument("--context-lines", type=int, default=20)
    excerpts.add_argument("--max-lines", type=int, default=1200)
    excerpts.set_defaults(func=make_source_excerpt_pack)

    worktree = subparsers.add_parser("ensure-worktree")
    worktree.add_argument("--snapshot-dir", required=True)
    worktree.add_argument("--repo", required=True)
    worktree.add_argument("--out")
    worktree.add_argument("--out-root")
    worktree.set_defaults(func=ensure_worktree)

    child_workspace = subparsers.add_parser("make-child-workspace")
    child_workspace.add_argument("--snapshot-dir", required=True)
    child_workspace.add_argument("--repo", required=True)
    child_workspace.add_argument("--out")
    child_workspace.add_argument("--name")
    child_workspace.add_argument("--allow-head-mismatch", action="store_true")
    child_workspace.set_defaults(func=make_child_workspace)

    child_home = subparsers.add_parser("ensure-child-codex-home")
    child_home.add_argument("--source-home", default=str(Path.home() / ".codex"))
    child_home.add_argument("--out", default=str(DEFAULT_CHILD_CODEX_HOME))
    child_home.add_argument("--force", action="store_true")
    child_home.set_defaults(func=ensure_child_codex_home)

    event_scan = subparsers.add_parser("scan-codex-event-log")
    event_scan.add_argument("--event-log", required=True)
    event_scan.add_argument("--out")
    event_scan.add_argument("--max-bytes", type=int, default=50_000_000)
    event_scan.add_argument("--max-excerpt-chars", type=int, default=500)
    event_scan.set_defaults(func=scan_codex_event_log)

    make_graphify = subparsers.add_parser("make-graphify-coverage")
    make_graphify.add_argument("--snapshot-dir", required=True)
    make_graphify.add_argument("--graph-json", required=True)
    make_graphify.add_argument("--case-id", required=True)
    make_graphify.add_argument("--mode", default="code-only-no-cluster")
    make_graphify.add_argument("--owner-repo", required=True)
    make_graphify.add_argument("--worktree", required=True)
    make_graphify.add_argument("--out", required=True)
    make_graphify.set_defaults(func=make_graphify_coverage)

    graphify_cache = subparsers.add_parser("ensure-graphify-cache")
    graphify_cache.add_argument("--owner-repo", required=True)
    graphify_cache.add_argument("--repo", required=True)
    graphify_cache.add_argument("--sha", required=True)
    graphify_cache.add_argument("--mode", default="code-only-cluster-clean")
    graphify_cache.add_argument("--force", action="store_true")
    graphify_cache.add_argument("--force-clean-source", action="store_true")
    graphify_cache.set_defaults(func=ensure_graphify_cache)

    graphify = subparsers.add_parser("attach-graphify-coverage")
    graphify.add_argument("--snapshot-dir", required=True)
    graphify.add_argument("--coverage", required=True)
    graphify.add_argument("--case-id", required=True)
    graphify.add_argument("--mode", default="code-only-no-cluster")
    graphify.add_argument("--graph-json-override")
    graphify.set_defaults(func=attach_graphify_coverage)

    symbols = subparsers.add_parser("make-graphify-symbol-pack")
    symbols.add_argument("--snapshot-dir", required=True)
    symbols.add_argument("--limit", type=int, default=12)
    symbols.add_argument("--out")
    symbols.set_defaults(func=make_graphify_symbol_pack)

    audit = subparsers.add_parser("audit-review")
    audit.add_argument("--snapshot-dir", required=True)
    audit.add_argument("--review", required=True)
    audit.add_argument("--out", required=True)
    audit.add_argument("--goldens")
    audit.set_defaults(func=audit_review)

    alignment = subparsers.add_parser("target-alignment")
    alignment.add_argument("--snapshot-dir", required=True)
    alignment.add_argument("--goldens", required=True)
    alignment.add_argument("--out", required=True)
    alignment.add_argument("--repo")
    alignment.set_defaults(func=target_alignment)

    eval_payload = subparsers.add_parser("make-eval-payload")
    eval_payload.add_argument("--review", required=True)
    eval_payload.add_argument("--goldens", required=True)
    eval_payload.add_argument("--out", required=True)
    eval_payload.add_argument("--case-id")
    eval_payload.set_defaults(func=make_eval_payload)

    summarize = subparsers.add_parser("summarize-results")
    summarize.add_argument("--cases-root")
    summarize.add_argument("--out")
    summarize.add_argument("--format", choices=("markdown", "json"), default="markdown")
    summarize.set_defaults(func=summarize_results)

    deltas = subparsers.add_parser("variant-deltas")
    deltas.add_argument("--summary")
    deltas.add_argument("--judge-file", default="pipeline-v2.2-codex-judge.md")
    deltas.add_argument("--out")
    deltas.add_argument("--format", choices=("markdown", "json"), default="markdown")
    deltas.set_defaults(func=variant_deltas)

    misses = subparsers.add_parser("remaining-misses")
    misses.add_argument("--cases-root")
    misses.add_argument("--out")
    misses.add_argument("--annotations")
    misses.add_argument("--format", choices=("markdown", "json"), default="markdown")
    misses.set_defaults(func=remaining_misses)

    outtake = subparsers.add_parser("outtake")
    outtake.add_argument("--summary")
    outtake.add_argument("--remaining")
    outtake.add_argument("--out")
    outtake.add_argument("--format", choices=("markdown", "json"), default="markdown")
    outtake.set_defaults(func=build_outtake)

    status = subparsers.add_parser("benchmark-status")
    status.add_argument("--problems", default=str(DEFAULT_PR_AF_PROBLEMS))
    status.add_argument("--summary")
    status.add_argument("--out")
    status.add_argument("--format", choices=("markdown", "json"), default="markdown")
    status.set_defaults(func=benchmark_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return exc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
