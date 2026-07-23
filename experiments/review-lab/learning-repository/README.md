# review-lab learning repository

This directory is an analysis-only knowledge base for review concern patterns.

Hard boundary:

- Do not load this repository into benchmark reviewer prompts.
- Do not reference it from `prompts/source-check.md`.
- Do not reference it from any global skill.
- Do not copy it into child workspaces.
- If a future experiment wants to use it, add an explicit opt-in selector and measure that path separately.

Why it exists:

- Preserve patterns learned from benchmark failures and PR-AF architecture review.
- Let us analyze concern coverage by family, trigger, and invariant.
- Keep the live reviewer small and trigger-driven instead of dumping a huge checklist into every review.

Files:

- `concerns.json`: machine-readable analysis catalog.
- `pr-af-comparison.md`: notes on how PR-AF differs from our current lab/deepreview setup.

Quick analysis:

```bash
jq '.concerns | length' experiments/review-lab/learning-repository/concerns.json
jq -r '.concerns[].family' experiments/review-lab/learning-repository/concerns.json | sort | uniq -c | sort -nr
jq -r '.concerns[] | [.id, .family, (.trigger_signals | join(","))] | @tsv' experiments/review-lab/learning-repository/concerns.json
```

The intended next step is to mine this repository offline, not use it directly in review. Good future work is a small trigger detector that selects a few relevant concern families, then validates that selector in a separate experiment.
