#!/usr/bin/env python3
"""v2.10 ledger pipeline: branch/consequence audit before selection."""

from __future__ import annotations

import pipeline_v1 as runner


runner.PIPELINE_NAME = "pipeline-v2"
runner.PIPELINE_VERSION = "pipeline-v2.10"
runner.PROMPT_DIR = runner.SCRIPT_DIR / "prompts" / "pipeline-v2.10"
runner.STAGES = (
    runner.Stage("01-contract-planner", "contract-planner.md"),
    runner.Stage(
        "02-browser-render-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "browser/frame/origin/referrer/messaging, renderability, templates, generated "
            "code, trusted rendered output, assets/layout, resource bundles, locale/message "
            "files, placeholders, translated HTML/anchors, message key spelling, and "
            "client-visible contracts"
        ),
    ),
    runner.Stage(
        "03-remote-import-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "remote fetch/open/file/network sinks, parser/import fields, external content "
            "ingress, trusted-string construction, nil/type handling, and sink guards"
        ),
    ),
    runner.Stage(
        "04-state-api-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "persistence, model callbacks, migrations, normalization/canonicalization, "
            "controller/API CRUD actions, auth/routing, state/cache, tests, and client/server "
            "serialization contracts"
        ),
    ),
    runner.Stage(
        "05-hole-finder",
        "hole-finder.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
        ),
    ),
    runner.Stage(
        "06-evidence-verifier",
        "evidence-verifier.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
            "05-hole-finder",
        ),
    ),
    runner.Stage(
        "07-transition-challenger",
        "transition-challenger.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
            "05-hole-finder",
            "06-evidence-verifier",
        ),
    ),
    runner.Stage(
        "08-branch-consequence-auditor",
        "branch-consequence-auditor.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
            "05-hole-finder",
            "06-evidence-verifier",
            "07-transition-challenger",
        ),
    ),
    runner.Stage(
        "09-candidate-selector",
        "candidate-selector.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
            "05-hole-finder",
            "06-evidence-verifier",
            "07-transition-challenger",
            "08-branch-consequence-auditor",
        ),
    ),
    runner.Stage(
        "10-synthesis",
        "synthesis.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-remote-import-ledger",
            "04-state-api-ledger",
            "05-hole-finder",
            "06-evidence-verifier",
            "07-transition-challenger",
            "08-branch-consequence-auditor",
            "09-candidate-selector",
        ),
    ),
)


if __name__ == "__main__":
    raise SystemExit(runner.main())
