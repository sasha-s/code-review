#!/usr/bin/env python3
"""v2.5 ledger pipeline: structured verified-candidate carry."""

from __future__ import annotations

import pipeline_v1 as runner


runner.PIPELINE_NAME = "pipeline-v2"
runner.PIPELINE_VERSION = "pipeline-v2.5"
runner.PROMPT_DIR = runner.SCRIPT_DIR / "prompts" / "pipeline-v2.5"
runner.STAGES = (
    runner.Stage("01-contract-planner", "contract-planner.md"),
    runner.Stage(
        "02-browser-render-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "browser/frame/origin/referrer/messaging, renderability, templates, generated "
            "code, trusted rendered output, assets/layout, resource bundles, locale/message "
            "files, placeholders, translated HTML/anchors, message key spelling, naming/API "
            "contracts, and client-visible contracts"
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
        "08-synthesis",
        "synthesis.md",
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
)


if __name__ == "__main__":
    raise SystemExit(runner.main())
