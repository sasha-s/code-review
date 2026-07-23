#!/usr/bin/env python3
"""Ledger-oriented multi-stage source-check pipeline for review-lab experiments."""

from __future__ import annotations

import pipeline_v1 as runner


runner.PIPELINE_NAME = "pipeline-v2"
runner.PIPELINE_VERSION = "pipeline-v2.3"
runner.PROMPT_DIR = runner.SCRIPT_DIR / "prompts" / "pipeline-v2.3"
runner.STAGES = (
    runner.Stage("01-contract-planner", "contract-planner.md"),
    runner.Stage(
        "02-browser-render-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "browser/frame/origin/referrer/messaging, renderability, templates, generated "
            "code, trusted rendered output, assets/layout, and client-visible contracts"
        ),
    ),
    runner.Stage(
        "03-resource-locale-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "resource bundles, locale/message files, translated UI text, expected language "
            "or script, neighboring/base-locale consistency, message key spelling, "
            "placeholder/interpolation grammar, translated HTML/anchor matcher grammar, "
            "resource loaders, generated metadata, and user-visible copied strings"
        ),
    ),
    runner.Stage(
        "04-remote-import-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "remote fetch/open/file/network sinks, parser/import fields, external content "
            "ingress, trusted-string construction, nil/type handling, and sink guards"
        ),
    ),
    runner.Stage(
        "05-state-api-ledger",
        "ledger-reviewer.md",
        ("01-contract-planner",),
        focus=(
            "persistence, model callbacks, migrations, normalization/canonicalization, "
            "controller/API CRUD actions, auth/routing, state/cache, tests, and client/server "
            "serialization contracts"
        ),
    ),
    runner.Stage(
        "06-hole-finder",
        "hole-finder.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-resource-locale-ledger",
            "04-remote-import-ledger",
            "05-state-api-ledger",
        ),
    ),
    runner.Stage(
        "07-evidence-verifier",
        "evidence-verifier.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-resource-locale-ledger",
            "04-remote-import-ledger",
            "05-state-api-ledger",
            "06-hole-finder",
        ),
    ),
    runner.Stage(
        "08-transition-challenger",
        "transition-challenger.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-resource-locale-ledger",
            "04-remote-import-ledger",
            "05-state-api-ledger",
            "06-hole-finder",
            "07-evidence-verifier",
        ),
    ),
    runner.Stage(
        "09-synthesis",
        "synthesis.md",
        (
            "01-contract-planner",
            "02-browser-render-ledger",
            "03-resource-locale-ledger",
            "04-remote-import-ledger",
            "05-state-api-ledger",
            "06-hole-finder",
            "07-evidence-verifier",
            "08-transition-challenger",
        ),
    ),
)


if __name__ == "__main__":
    raise SystemExit(runner.main())
