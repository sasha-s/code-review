#!/usr/bin/env python3
"""Isolated multi-stage source-check pipeline for review-lab experiments."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PIPELINE_NAME = "pipeline-v1"
PIPELINE_VERSION = "pipeline-v1.2"
DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "code-review" / "review-lab"
DEFAULT_CHILD_CODEX_HOME = DEFAULT_CACHE_ROOT / "codex-home-auth-only"
DEFAULT_CODEX = Path.home() / ".codex" / "plugins" / ".plugin-appserver" / "codex"
SCRIPT_DIR = Path(__file__).resolve().parent
PROMPT_DIR = SCRIPT_DIR / "prompts" / PIPELINE_NAME
REVIEW_LAB = SCRIPT_DIR / "review_lab.py"


@dataclass(frozen=True)
class Stage:
    name: str
    prompt_file: str
    previous: tuple[str, ...] = ()
    include_v7: bool = False
    include_v8: bool = False
    focus: str = ""


STAGES = (
    Stage("01-planner", "planner.md"),
    Stage(
        "02-browser-render-v7",
        "cluster-reviewer-v7.md",
        ("01-planner",),
        include_v7=True,
        focus=(
            "Browser, frame, origin/referrer, postMessage, CSP/X-Frame-Options, "
            "template/renderability, asset/layout, trusted rendered HTML, and CSS/legacy "
            "clusters."
        ),
    ),
    Stage(
        "03-remote-import-v7",
        "cluster-reviewer-v7.md",
        ("01-planner",),
        include_v7=True,
        focus=(
            "Remote fetch, URL opening/parsing, feed/import parser fields, external content "
            "ingress, sink guards, nil/type handling, and raw trusted-string construction "
            "clusters."
        ),
    ),
    Stage(
        "04-persistence-tests-v7",
        "cluster-reviewer-v7.md",
        ("01-planner",),
        include_v7=True,
        focus=(
            "Persistence, model callbacks, migrations, enum/default compatibility, raw HTML "
            "cooking, revision/update semantics, settings/routes, and changed test/runtime "
            "contract clusters."
        ),
    ),
    Stage(
        "05-focused-v8",
        "focused-v8.md",
        ("01-planner", "02-browser-render-v7", "03-remote-import-v7", "04-persistence-tests-v7"),
        include_v8=True,
    ),
    Stage(
        "06-verifier",
        "verifier.md",
        (
            "01-planner",
            "02-browser-render-v7",
            "03-remote-import-v7",
            "04-persistence-tests-v7",
            "05-focused-v8",
        ),
    ),
    Stage(
        "07-challenger",
        "challenger.md",
        (
            "01-planner",
            "02-browser-render-v7",
            "03-remote-import-v7",
            "04-persistence-tests-v7",
            "05-focused-v8",
            "06-verifier",
        ),
    ),
    Stage(
        "08-synthesis",
        "synthesis.md",
        (
            "01-planner",
            "02-browser-render-v7",
            "03-remote-import-v7",
            "04-persistence-tests-v7",
            "05-focused-v8",
            "06-verifier",
            "07-challenger",
        ),
    ),
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and read_text(path) == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def write_json_if_changed(path: Path, data: Any) -> bool:
    return write_text_if_changed(path, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def extract_text_prompt(path: Path) -> str:
    text = read_text(path)
    match = re.search(r"```text\n(.*?)\n```", text, flags=re.S)
    if match:
        return match.group(1).strip()
    return text.strip()


def git_head(worktree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def directory_fingerprint(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rows.append({"path": file_path.relative_to(path).as_posix(), "sha256": sha256_file(file_path)})
    return rows


def resolve_codex(path_arg: str | None) -> Path:
    if path_arg:
        path = Path(path_arg).expanduser()
        if path.exists():
            return path
        raise SystemExit(f"Codex binary does not exist: {path}")
    if DEFAULT_CODEX.exists():
        return DEFAULT_CODEX
    discovered = shutil.which("codex")
    if discovered:
        return Path(discovered)
    raise SystemExit("Could not find Codex binary. Pass --codex explicitly.")


def ensure_child_codex_home(codex_home: Path) -> None:
    if codex_home.exists():
        return
    subprocess.run(
        [sys.executable, str(REVIEW_LAB), "ensure-child-codex-home", "--out", str(codex_home)],
        check=True,
    )


def stage_output(case_dir: Path, stage: Stage) -> Path:
    return case_dir / PIPELINE_NAME / f"{stage.name}.md"


def stage_manifest(case_dir: Path, stage: Stage) -> Path:
    return case_dir / PIPELINE_NAME / f"{stage.name}.manifest.json"


def workspace_stage_output(worktree: Path, stage: Stage) -> Path:
    return worktree / ".review-lab-inputs" / PIPELINE_NAME / f"{stage.name}.md"


def relative_to_worktree(worktree: Path, path: Path) -> str:
    try:
        return path.relative_to(worktree).as_posix()
    except ValueError:
        return str(path)


def previous_artifact_text(worktree: Path, stage: Stage) -> str:
    if not stage.previous:
        return "- None"
    lines = []
    for previous_name in stage.previous:
        artifact = worktree / ".review-lab-inputs" / PIPELINE_NAME / f"{previous_name}.md"
        lines.append(f"- `{relative_to_worktree(worktree, artifact)}`")
    return "\n".join(lines)


def render_prompt(
    *,
    stage: Stage,
    case_id: str,
    worktree: Path,
    input_readme: Path,
    v7_protocol: str,
    v8_protocol: str,
) -> str:
    template = read_text(PROMPT_DIR / stage.prompt_file)
    replacements = {
        "{{PIPELINE_VERSION}}": PIPELINE_VERSION,
        "{{CASE_ID}}": case_id,
        "{{INPUT_README}}": relative_to_worktree(worktree, input_readme),
        "{{PIPELINE_README}}": f".review-lab-inputs/{PIPELINE_NAME}/README.md",
        "{{PREVIOUS_ARTIFACTS}}": previous_artifact_text(worktree, stage),
        "{{CLUSTER_FOCUS}}": stage.focus,
        "{{V7_PROTOCOL}}": v7_protocol if stage.include_v7 else "",
        "{{V8_PROTOCOL}}": v8_protocol if stage.include_v8 else "",
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template.strip() + "\n"


def stage_signature(
    *,
    stage: Stage,
    case_id: str,
    model: str,
    dry_run: bool,
    worktree_head: str,
    input_fingerprint: list[dict[str, str]],
    prompt: str,
    previous_outputs: dict[str, str],
) -> dict[str, Any]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "stage": stage.name,
        "case_id": case_id,
        "model": model,
        "dry_run": dry_run,
        "worktree_head": worktree_head,
        "input_fingerprint": input_fingerprint,
        "prompt_sha256": sha256_text(prompt),
        "previous_outputs": previous_outputs,
    }


def cached_stage_valid(manifest_path: Path, output_path: Path, signature_hash: str, allow_scan_hits: bool) -> bool:
    if not manifest_path.exists() or not output_path.exists():
        return False
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError:
        return False
    if manifest.get("signature_hash") != signature_hash or manifest.get("returncode") != 0:
        return False
    scan = manifest.get("scan") or {}
    if not allow_scan_hits and int(scan.get("hit_count") or 0) != 0:
        return False
    return True


def scan_event_log(event_log: Path, scan_path: Path) -> dict[str, Any]:
    subprocess.run(
        [
            sys.executable,
            str(REVIEW_LAB),
            "scan-codex-event-log",
            "--event-log",
            str(event_log),
            "--out",
            str(scan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(read_text(scan_path))


def run_codex_stage(
    *,
    codex: Path,
    codex_home: Path,
    model: str,
    worktree: Path,
    output_path: Path,
    event_log: Path,
    stderr_log: Path,
    prompt: str,
    timeout_seconds: int,
) -> int:
    event_log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(codex),
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--disable",
        "plugins",
        "-m",
        model,
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--cd",
        str(worktree),
        "-o",
        str(output_path),
        prompt,
    ]
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["NO_COLOR"] = "1"
    with event_log.open("w", encoding="utf-8") as stdout, stderr_log.open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(
            command,
            stdout=stdout,
            stderr=stderr,
            text=True,
            env=env,
            timeout=timeout_seconds,
        )
    return completed.returncode


def write_pipeline_workspace_readme(worktree: Path, input_readme: Path, completed: list[str]) -> None:
    lines = [
        f"# {PIPELINE_NAME} stage artifacts",
        "",
        "Blind source-check pipeline artifacts. These are harness outputs, not product source.",
        "",
        f"- Original blind input README: `{relative_to_worktree(worktree, input_readme)}`",
        "",
        "Completed stages:",
    ]
    if completed:
        lines.extend(f"- `{name}.md`" for name in completed)
    else:
        lines.append("- None yet")
    lines.append("")
    write_text_if_changed(worktree / ".review-lab-inputs" / PIPELINE_NAME / "README.md", "\n".join(lines))


def copy_stage_to_workspace(worktree: Path, stage: Stage, output_path: Path) -> None:
    if not output_path.exists():
        raise SystemExit(f"Stage did not produce output: {output_path}")
    write_text_if_changed(workspace_stage_output(worktree, stage), read_text(output_path))


def run_pipeline(args: argparse.Namespace) -> None:
    case_id = args.case_id
    cache_root = Path(args.cache_root).expanduser()
    case_dir = Path(args.case_dir).expanduser() if args.case_dir else cache_root / "cases" / case_id
    worktree = Path(args.worktree).expanduser()
    input_readme = worktree / ".review-lab-inputs" / args.input_name / "README.md"
    input_dir = input_readme.parent
    if not worktree.exists():
        raise SystemExit(f"Worktree does not exist: {worktree}")
    if not input_readme.exists():
        raise SystemExit(f"Blind input README does not exist: {input_readme}")

    codex = resolve_codex(args.codex)
    codex_home = Path(args.codex_home).expanduser()
    ensure_child_codex_home(codex_home)

    v7_protocol = extract_text_prompt(SCRIPT_DIR / "prompts" / "generic-adversarial-v7.md")
    v8_protocol = extract_text_prompt(SCRIPT_DIR / "prompts" / "generic-adversarial-v8.md")
    worktree_head = git_head(worktree)
    input_fingerprint = directory_fingerprint(input_dir)
    completed: list[str] = []
    stage_records: list[dict[str, Any]] = []

    write_pipeline_workspace_readme(worktree, input_readme, completed)

    for stage in STAGES:
        prompt = render_prompt(
            stage=stage,
            case_id=case_id,
            worktree=worktree,
            input_readme=input_readme,
            v7_protocol=v7_protocol,
            v8_protocol=v8_protocol,
        )
        previous_outputs = {
            name: sha256_file(worktree / ".review-lab-inputs" / PIPELINE_NAME / f"{name}.md")
            for name in stage.previous
        }
        signature = stage_signature(
            stage=stage,
            case_id=case_id,
            model=args.model,
            dry_run=args.dry_run,
            worktree_head=worktree_head,
            input_fingerprint=input_fingerprint,
            prompt=prompt,
            previous_outputs=previous_outputs,
        )
        signature_hash = sha256_text(stable_json(signature))
        output_path = stage_output(case_dir, stage)
        manifest_path = stage_manifest(case_dir, stage)
        event_log = case_dir / PIPELINE_NAME / f"{stage.name}.events.jsonl"
        stderr_log = case_dir / PIPELINE_NAME / f"{stage.name}.stderr.log"
        scan_path = case_dir / PIPELINE_NAME / f"{stage.name}-event-scan.json"

        if args.force or not cached_stage_valid(manifest_path, output_path, signature_hash, args.allow_scan_hits):
            print(f"Running {stage.name}", flush=True)
            if args.dry_run:
                write_text_if_changed(output_path, f"# {stage.name}\n\nDry run placeholder.\n")
                rc = 0
                scan = {"hit_count": 0, "hits": []}
            else:
                rc = run_codex_stage(
                    codex=codex,
                    codex_home=codex_home,
                    model=args.model,
                    worktree=worktree,
                    output_path=output_path,
                    event_log=event_log,
                    stderr_log=stderr_log,
                    prompt=prompt,
                    timeout_seconds=args.timeout_seconds,
                )
                if rc != 0:
                    write_json_if_changed(
                        manifest_path,
                        {
                            "generated_at": utc_now(),
                            "pipeline_version": PIPELINE_VERSION,
                            "stage": stage.name,
                            "returncode": rc,
                            "signature_hash": signature_hash,
                            "output": str(output_path),
                            "event_log": str(event_log),
                            "stderr_log": str(stderr_log),
                        },
                    )
                    raise SystemExit(f"{stage.name} failed with exit code {rc}. See {stderr_log}")
                scan = scan_event_log(event_log, scan_path)
                if not args.allow_scan_hits and int(scan.get("hit_count") or 0) != 0:
                    write_json_if_changed(
                        manifest_path,
                        {
                            "generated_at": utc_now(),
                            "pipeline_version": PIPELINE_VERSION,
                            "stage": stage.name,
                            "returncode": rc,
                            "signature_hash": signature_hash,
                            "output": str(output_path),
                            "event_log": str(event_log),
                            "stderr_log": str(stderr_log),
                            "scan": scan,
                        },
                    )
                    raise SystemExit(f"{stage.name} event scan found isolation hits: {scan_path}")
            record = {
                "generated_at": utc_now(),
                "pipeline_version": PIPELINE_VERSION,
                "stage": stage.name,
                "cached": False,
                "returncode": rc,
                "signature": signature,
                "signature_hash": signature_hash,
                "output": str(output_path),
                "event_log": str(event_log),
                "stderr_log": str(stderr_log),
                "scan_path": str(scan_path),
                "scan": scan,
            }
            write_json_if_changed(manifest_path, record)
        else:
            print(f"Using cached {stage.name}", flush=True)
            record = json.loads(read_text(manifest_path))
            record["cached"] = True

        copy_stage_to_workspace(worktree, stage, output_path)
        completed.append(stage.name)
        write_pipeline_workspace_readme(worktree, input_readme, completed)
        stage_records.append(record)

    pipeline_manifest = {
        "generated_at": utc_now(),
        "pipeline_version": PIPELINE_VERSION,
        "case_id": case_id,
        "model": args.model,
        "worktree": str(worktree),
        "worktree_head": worktree_head,
        "input_readme": relative_to_worktree(worktree, input_readme),
        "case_dir": str(case_dir),
        "final_review": str(stage_output(case_dir, STAGES[-1])),
        "stages": stage_records,
    }
    write_json_if_changed(case_dir / PIPELINE_NAME / "manifest.json", pipeline_manifest)
    print(stage_output(case_dir, STAGES[-1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-dir")
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--input-name", default="generic-adversarial")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--codex")
    parser.add_argument("--codex-home", default=str(DEFAULT_CHILD_CODEX_HOME))
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-scan-hits", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(func=run_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except subprocess.TimeoutExpired as exc:
        print(f"Timed out after {exc.timeout} seconds", file=sys.stderr)
        return 124
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return exc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
