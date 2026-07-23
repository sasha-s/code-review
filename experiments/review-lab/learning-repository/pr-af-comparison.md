# PR-AF comparison notes

Observed upstream:

- Repository: `https://github.com/Agent-Field/pr-af`
- Cached commit inspected: `6b82efc8ade7cd48420ecd6de59eeb1cb80d3b49`
- Benchmark claim: 72/102 golden hits on the 38 runnable Martian Code-Review-Bench PRs, recall 0.706, using GLM-5.2 and a blind deep run.
- Their packaged benchmark excludes 12 of 50 problems: 10 Discourse rebase-merged commits and 2 synthetic Sentry entries.

Main architectural differences:

| Area | PR-AF | Our isolated review-lab setup |
|---|---|---|
| Review shape | Dynamic multi-agent pipeline. Meta selectors generate semantic, mechanical, and systemic review dimensions per PR. | Mostly explicit source-check prompts plus prebuilt diff/source/Graphify context. Some repeated targeted passes. |
| Planning | The system first decides what investigations are needed, then spawns reviewers. | The prompt encodes general invariants; the operator chooses follow-up passes. |
| Breadth | Up to many parallel review dimensions, sub-reviews, coverage gap reviewers, adversary batches, and consistency checks. | One child Codex run per chosen prompt unless manually repeated. |
| Evidence | Programmatically extracts code around reported findings, caller snippets, diff hunks, import context, and related code. | Builds source excerpts, Graphify symbol packs, and context packs before review, but no automatic finding-by-finding verifier loop. |
| Adversary | Separate evidence verifier and adversary challenge findings before final scoring. | Global `deepreview` has reviewer-challenger dialogs, but the benchmark lab path has not yet made that an automatic, isolated evidence loop. |
| Coverage | Coverage gate can spawn gap reviewers when clusters were missed. | Graphify coverage is measured and attached, but missed cluster review is not automatically closed. |
| Synthesis | Deterministic dedup, scoring, max comment cap, merge/polish gates. | Judge/eval harness summarizes recall, but review synthesis is mostly left to Codex output and later audit. |
| Retrieval | Programmatic diff clustering plus a Python-import-only blast radius engine. Evidence extraction uses grep and snippets. | Graphify cache can cover many languages and stores reusable graph artifacts, but CSS/SCSS coverage was weak in our runs. |
| Cost/time stance | Explicitly deep: 35-50 minute reviews, uncapped quality campaign, parallel agents. | We have relaxed timeouts, but current lab quality still depends on manually choosing extra passes. |

Why they can get high quality:

- They spend more calls per PR and diversify failure search through generated dimensions.
- The planner is the important piece: it turns a PR into specific investigation questions instead of running a fixed checklist.
- Evidence verification reduces false positives, so they can afford to be chatty.
- Coverage and consistency phases search for "what changed elsewhere must now be true" instead of only reading changed hunks.
- Their adjusted quality claim credits non-golden valid bugs and valid nits, which rewards broad high-volume reviewers if the judge accepts the findings.

Important caveats:

- Their 0.706 headline is on 38 runnable PRs, not all 50 benchmark problems.
- Their adjusted F1/valid-finding claim depends on an extra model-judge classification of non-golden findings.
- Their published runner does not demonstrate commit-ref handling for the Discourse cases that were hard for us.
- The Go blast-radius implementation intentionally reproduces a Python-only import graph, so it will not solve every JS/Ruby/CSS/Go context gap.
- Their pipeline can still miss bugs if the planner fails to create the right dimension; evidence verification starts from findings already discovered.
- A high comment cap and adjusted scoring can make "find many things" look strong even when a human maintainer would prefer fewer comments.

Overlap with our current lab:

- Our full 50-case lab summary: best single-review recall 95/136, union recall 100/136.
- On the same 38-case subset PR-AF reports, our current summary is best 83/102 (0.814), union 87/102 (0.853).
- That is not an apples-to-apples product comparison. Our number is from many exploratory lab runs and targeted follow-ups, not one uniform deployable reviewer pass. PR-AF's 72/102 is presented as a single baseline campaign.

What is worth borrowing:

- Make planning explicit: generate a few precise investigations from the diff and repo context before reviewing.
- Add a real coverage gap loop that can spawn follow-up review passes automatically.
- Add finding-level evidence verification before adversarial challenge.
- Use a consistency-obligation extractor/verifier for changed-code assumptions.
- Keep the large concern repository offline for learning. The live reviewer should receive only a small set of selected concerns, and that selector should be measured independently.
