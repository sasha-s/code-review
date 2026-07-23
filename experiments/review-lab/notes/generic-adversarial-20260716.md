# Generic adversarial subset experiment - 2026-07-16

This experiment tests generic adversarial review structure on benchmark cases
without injecting the analysis-only concern repository.

## Setup

- Prompt v1: `prompts/generic-adversarial.md`
  - Strict no-checklist finder plus adversarial falsification.
- Prompt v2: `prompts/generic-adversarial-v2.md`
  - Adds a coverage ledger and operation-shaped boundary probes.
- Prompt v3: `prompts/generic-adversarial-v3.md`
  - Adds three output tiers: findings, source-backed boundary concerns, and
    rejected candidates.
- Prompt v4: `prompts/generic-adversarial-v4.md`
  - Adds a hunk-level micro-contract ledger.
- Prompt v5: `prompts/generic-adversarial-v5.md`
  - Adds mandatory external-sink and renderability proofs.
- Prompt v6: `prompts/generic-adversarial-v6.md`
  - Adds caller-evidenced sink proof, trusted-string interpolation proof, and
    explicit browser/security-header proof.
- Prompt v7: `prompts/generic-adversarial-v7.md`
  - Narrow derivative of v5: keeps sink/render proofs, adds focused
    trusted-HTML/string interpolation and browser frame/security proof, and
    supports the existing single `.review-lab-inputs/*/README.md` fallback.
- Prompt v8: `prompts/generic-adversarial-v8.md`
  - Adds operation-triggered remote-fetch, distinct trusted-string failure-mode,
    CSS/legacy-browser, lazy-state/concurrency, and external-command argument
    proof obligations.
- Child Codex isolation:
  - `--ignore-user-config`
  - `--ignore-rules`
  - `--ephemeral`
  - `--disable plugins`
  - `--sandbox read-only`
- Cases:
  - `cal_dot_com-10600`
  - `keycloak-41249`
  - `sentry-92393`
  - `discourse-commit-4f8aed295a`
- All child event scans reported `hit_count=0` after tightening the scanner to
  ignore negative-glob skill-path exclusions. One earlier v3 Cal scan was a
  false positive from the review text saying it did not inspect evaluator files.
  v7 added another scanner refinement for denial/prohibition text such as
  "avoid benchmark-golden/evaluator material".

## Benchmark Recall

| Case | Prior best | v1 | v2 | v3 | v4 | v5 | v6 | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `cal_dot_com-10600` | 4/4 | 1/4 | 1/4 | 1/4 | 2/4 | 2/4 | not run | v4/v5 add the case-normalization miss while retaining concurrent backup-code reuse. The remaining misses are low-value naming/text issues; do not tune hard toward them. |
| `keycloak-41249` | 1/2 | 0/2 | 0/2 | 0/2 | 0/2 | not run | not run | Target alignment marks both goldens contradicted by the actual target source, so this is adjudication noise, not prompt signal. |
| `sentry-92393` | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | not run | not run | Goldens are paginator issues, while the target patch is span buffering; treat as misattached/stale and do not tune. |
| `discourse-commit-4f8aed295a` | 0/6 | 1/6 | 0/6 | 1/6 | 1/6 | 3/6 | 2/6 | v5 adds full-referrer `postMessage` and invalid ERB via generic sink/render proofs. v6 catches frame-header weakening but regresses on message-origin issues. |

Aggregate after v6:

- Best parseable recall: `98/136`
- Union parseable recall: `103/136`
- Cases / judge records: `50 / 118`
- This is +3 best and +4 union over the starting `95/136` best and
  `99-100/136` union state observed before this iteration, depending on which
  early child runs are included.

Aggregate after v7 and judge-parser repair:

- Best parseable recall: `101/136`
- Union parseable recall: `107/136`
- Cases / judge records: `50 / 124`
- Remaining misses: `29`, with `8` source-backed prompt-improvement candidates.
- v7 broad source-backed subset:
  - `discourse-commit-4f8aed295a`: `2/6` standalone; union now `4/6`.
  - `discourse-commit-5b229316ee`: `0/2`.
  - `discourse-commit-d1c69189f3`: `2/4`.
  - `discourse-commit-d38c4d5f74`: `2/3`.
  - `discourse-commit-ecfa17b5a7`: `1/2`.
  - `discourse-commit-ffbaf8c542`: `2/3`.

Aggregate after v8 and markdown-table judge-parser repair:

- Best parseable recall: `102/136`
- Union parseable recall: `109/136`
- Cases / judge records: `50 / 130`
- Remaining misses: `27`, with `6` source-backed prompt-improvement candidates.
- v8 broad source-backed subset:
  - `discourse-commit-4f8aed295a`: `2/6`; adds SSRF and targetOrigin but
    regresses on invalid ERB and origin-prefix checks as a standalone run.
  - `discourse-commit-5b229316ee`: `1/2`; catches header panel layout loss.
  - `discourse-commit-d1c69189f3`: `1/4`; regresses versus v7 except migration
    normalization.
  - `discourse-commit-d38c4d5f74`: `2/3`; same as v7.
  - `discourse-commit-ecfa17b5a7`: `0/2`; regresses versus v7.
  - `discourse-commit-ffbaf8c542`: `2/3`; same as v7.

## Observations

- The generic adversarial structure improves evidence discipline. It produced
  compact findings with explicit rejected candidates instead of broad speculative
  lists.
- v1 is too narrow. It tends to stop after the most attractive source-backed
  issue.
- v2 broadens coverage but can over-prune lower-impact boundary defects. On
  Discourse it rejected the substring origin issue that v1 got credit for.
- All versions found plausible non-golden bugs. This is good review behavior
  but weak under golden-only recall.
- The current format makes "rejected" candidates invisible to benchmark scoring
  and potentially to a human reviewer, even when the candidate is a real
  lower-severity boundary defect.
- v4's hunk-level ledger improved Cal by catching case normalization, showing
  that mechanical hunk accounting helps without benchmark terms.
- v5's sink/render proofs improved Discourse to 3/6 by catching two issues that
  v1-v4 repeatedly skipped: invalid template syntax and origin-vs-full-URL
  `postMessage` behavior.
- v6 was stricter but not better as a single review. It caught frame-header
  weakening but rejected the message-origin issues. More obligations can make
  the reviewer over-discount concrete browser failures, so v5 is the better
  current default candidate.
- v7 is the strongest broad candidate so far. It preserved v5-style rigor while
  adding useful coverage on migration normalization, SCSS light-theme
  regressions, locale normalization, and upload/optimized-image runtime arity.
  It still misses some low-level or highly specific defects: SSRF/internal URL
  fetch semantics, nil receiver plus unescaped interpolation as separate issues,
  legacy browser CSS prefixes, and animated GIF geometry semantics.
- v8 improved union but is not a better single-review prompt. It catches remote
  fetch and legacy layout issues but overfits the operation triggers enough to
  lose already-caught template and locale issues. Treat v8 as a source of
  targeted sub-pass ideas, not the default prompt.
- The remaining useful Discourse misses require sharper source-to-sink proof:
  `open(url)` needs all runtime callers and their URL guards, and generated
  trusted HTML needs each interpolated value checked for nil/type/escaping.

## Next Iteration

Prefer v7 as the next default candidate protocol for broader benchmark sampling.
Use v8's remote-fetch and legacy-layout wording as optional focused sub-passes
rather than folding all of v8 into the default path.

Do not tune toward:

- Sentry 92393 paginator goldens, because they are stale/misattached for the
  target patch.
- Keycloak 41249 goldens, because target alignment marks them contradicted.
- Cal low-value naming/log-string misses unless product review quality decides
  these are worth reporting as low-severity polish.
