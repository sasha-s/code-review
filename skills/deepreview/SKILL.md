---
name: deepreview
description: >-
  Performs adversarial three-step PR review: scopes changes, summarizes PR
  design and approach, then runs reviewer-challenger dialogs through dev,
  security, sre, and research lenses. Uses code-review-graph CLI (preferred)
  or MCP tools when available. Outputs structured markdown with severity
  ratings and verdicts. Supports incremental re-review: when a prior review
  exists in the out-of-repo PR review directory it verifies old findings against
  the new head and reviews only the delta. Use when given a PR number, PR URL,
  or asked to review or re-review a pull request.
---

# Adversarial PR Review

Three-step review:
1. **Scope Analysis** — map the changes into logical units
2. **PR Design Summary** — describe what the PR is doing before analyzing issues
3. **Adversarial Review** — run reviewer-challenger dialogs through dev, security, sre, and research lenses

## Input

Accept a PR number or full GitHub URL. Resolve against the current repo.

```bash
# Verify gh is available and authenticated
gh auth status

# Fetch PR metadata
gh pr view <N> --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles,url,state,mergeCommit

# Fetch the diff
gh pr diff <N>
```

If `gh` is not installed or not authenticated, stop and tell the user.

### Prepare a PR review worktree

Do not run graph/repo-intel/source inspection against the caller's current
branch unless that branch is already the exact PR head or merge commit being
reviewed. For open PRs, a repository left on `main` will make graph analysis
silently review the wrong tree. Create a detached, per-PR worktree and perform
all Pass 0-3 code reads from there.

```bash
PR_ARG="<N-or-full-PR-URL>"
STATE=$(gh pr view "${PR_ARG}" --json state --jq '.state')
PR_NUM=$(gh pr view "${PR_ARG}" --json number --jq '.number')
HEAD_SHA=$(gh pr view "${PR_ARG}" --json headRefOid --jq '.headRefOid')
REPO_NAME="$(basename "$(git rev-parse --show-toplevel)")"
REVIEW_WORKTREE="${TMPDIR:-/tmp}/deepreview-${REPO_NAME}-PR-${PR_NUM}-${HEAD_SHA:0:12}"

if [ ! -e "${REVIEW_WORKTREE}/.git" ]; then
  if [ "${STATE}" = "MERGED" ]; then
    MERGE_COMMIT=$(gh pr view "${PR_ARG}" --json mergeCommit --jq '.mergeCommit.oid')
    git worktree add --detach "${REVIEW_WORKTREE}" "${MERGE_COMMIT}"
  else
    git worktree add --detach "${REVIEW_WORKTREE}" HEAD
    (cd "${REVIEW_WORKTREE}" && gh pr checkout "${PR_ARG}" --detach)
  fi
fi

cd "${REVIEW_WORKTREE}"
```

If worktree creation fails, continue from the current worktree only after
running `git rev-parse HEAD` and confirming it equals `HEAD_SHA` (open PR) or
the merge commit (merged PR). Otherwise stop and report that the review cannot
be trusted against the current checkout.

### Check for a prior review (re-review mode)

Reviews live **outside the repo**, one directory per PR, one file per
reviewed head SHA:

```
~/reviews/<repo>/PR-<N>/<short-sha>.md           # the review
~/reviews/<repo>/PR-<N>/<short-sha>-comment.md   # GitHub comment draft
```

Before Pass 0, check whether this PR has been reviewed before:

```bash
REPO_NAME="$(basename "$(git rev-parse --show-toplevel)")"
REVIEW_DIR="$HOME/reviews/${REPO_NAME}/PR-<N>"
ls -t "${REVIEW_DIR}"/*.md 2>/dev/null | grep -v -- '-comment.md'
# Legacy fallback: older reviews may live in-repo at reviews/PR-<N>.md
```

If a prior review exists, this is a **re-review**. The newest file is the
prior round. Extract from it:

- The **reviewed head SHA** — the filename (confirm against the header; a
  legacy in-repo review may lack it — then use `gh pr view <N> --json
  commits` and the file's date to find which commits are new)
- The **Findings Ledger** (IDs, severities, statuses)
- The prior Questions for the Author and Recommendations

Then compute the incremental diff and check for author responses:

```bash
NEW_HEAD=$(gh pr view <N> --json headRefOid --jq '.headRefOid')
git fetch origin "${HEAD_BRANCH}" 2>/dev/null
git diff ${PRIOR_HEAD}..${NEW_HEAD}
gh pr view <N> --json comments --jq '.comments[] | {author: .author.login, body: .body}'
```

Re-review rules (these override the normal pass instructions):

1. **Re-verify prior findings first.** For each open ledger item, check the
   new head and mark it `resolved`, `still-open`, or `obsolete` — citing the
   commit or author comment that settles it. Author replies in PR comments
   count as answers to prior Questions.
2. **Review only the delta.** Run the passes on the incremental diff plus any
   code an open finding points at. Do not re-derive findings on unchanged
   code; an unchanged scope gets one line ("unchanged since round {k}").
3. **Never restate.** A prior question or recommendation may reappear only if
   still-open, referenced by its ID — not rephrased as if new.
4. **Same head, no new comments** → tell the user nothing changed and ask
   what they want re-examined instead of redoing the same review, unless
   the user or scheduler explicitly requested a forced re-review. In forced
   same-head mode, re-run the requested checks and overwrite that SHA's
   artifacts with the fresh verification.

If no prior review exists, proceed as round 1.

### Compute the graph base ref

The `code-review-graph` CLI and MCP tools both diff against a `base` ref. For
merged PRs, `HEAD` already includes the PR's changes, so diffing against `main`
produces an empty diff. Compute `GRAPH_BASE` before Pass 0:

```bash
STATE=$(gh pr view <N> --json state --jq '.state')
BASE_BRANCH=$(gh pr view <N> --json baseRefName --jq '.baseRefName')
HEAD_BRANCH=$(gh pr view <N> --json headRefName --jq '.headRefName')

if [ "$STATE" = "MERGED" ]; then
  # For merged PRs: use the merge commit's first parent (the base branch before merge)
  MERGE_COMMIT=$(gh pr view <N> --json mergeCommit --jq '.mergeCommit.oid')
  GRAPH_BASE="${MERGE_COMMIT}^1"
  # Verify: git diff --stat ${GRAPH_BASE}..${MERGE_COMMIT} should show the PR's files
else
  # For open PRs: use the merge base between head and base branch
  GRAPH_BASE=$(git merge-base "origin/${BASE_BRANCH}" "origin/${HEAD_BRANCH}")
fi
```

If `GRAPH_BASE` cannot be computed (branch deleted, shallow clone), fall back
to `HEAD~1` and note the limitation.

**Re-review mode**: use `GRAPH_BASE=${PRIOR_HEAD}` instead — the graph should
score only what changed since the last review, matching the incremental diff.

## Pass 0: Graph Reconnaissance

Check for `code-review-graph` CLI first, then MCP tools as fallback, then repo-intel for enhanced context.

### Step 0a — CLI detect-changes (preferred)

```bash
export PATH="$HOME/.local/bin:$HOME/.local/share/uv/tools/code-review-graph/bin:$PATH"
code-review-graph detect-changes --repo "${PWD}" --base "${GRAPH_BASE}" 2>&1
```

This returns:
- Risk-scored list of changed functions/classes
- Test coverage gaps (functions lacking tests)
- Overall risk score
- Review priorities sorted by risk

If the CLI is not initially on PATH, check the known uv-tool location above before
falling through to MCP. If CLI succeeds, use these results.

### Step 0b — MCP tools (fallback)

If CLI is unavailable or you need graph features the CLI does not expose, use
`tool_search` to discover the `code-review-graph` MCP tools. Feature-detect the
available tool names and use only those. Call `detect_changes_tool` with
`GRAPH_BASE` as `base` and `detail_level="minimal"` when it is exposed.

If neither CLI nor MCP is available, skip Pass 0 entirely.

### Step 0c — Affected flows and impact radius, if exposed

The currently installed `code-review-graph` CLI exposes `detect-changes` but not
`get-affected-flows` or `get-impact-radius`. Do **not** call nonexistent CLI
subcommands. If `tool_search` exposes MCP tools such as
`get_affected_flows_tool` or `get_impact_radius_tool`, use them against the
same PR worktree and `GRAPH_BASE`; otherwise record these fields as unavailable
and continue with `detect-changes` output plus normal source inspection.

### Step 0e — Validate code-review-graph results

If `detect_changes` returns 0 changed functions despite a non-empty diff, the
`base` ref is likely wrong (common for merged PRs). Debug:

```bash
git diff --stat ${GRAPH_BASE}..HEAD
```

If empty, recompute `GRAPH_BASE` and retry before proceeding.

### Step 0f — Repo-Intel ask (enhanced context)

After code-review-graph Pass 0, run repo-intel for bounded owner/proof localization:

```bash
REPO_INTEL_HOOK="${REPO_INTEL_LIVE_HOOK:-/Users/sasha/code-intelligence/integrations/vap/scripts/repo_intel_live_hook.py}"
REPO_INTEL_WORKSPACE_ARG=()
if [ -n "${REVIEW_REPO_INTEL_WORKSPACE_ROOT:-}" ]; then
  REPO_INTEL_WORKSPACE_ARG=(--workspace-root "${REVIEW_REPO_INTEL_WORKSPACE_ROOT}")
fi

# Get PR context
PR_TITLE=$(gh pr view "${PR_NUM}" --json title --jq '.title')
PR_FILES=$(gh pr view "${PR_NUM}" --json files --jq '.files[].path' | tr '\n' ' ')

# Optional: refresh in the PR worktree first when reviewing a detached PR head,
# especially for new files/subtrees. Do not use stale local-main indexes as
# authoritative evidence for a PR-head-only subtree.
python3 "${REPO_INTEL_HOOK}" \
  --repo-root "${PWD}" \
  --repo-slug "$(basename "$(git rev-parse --show-toplevel)")" \
  "${REPO_INTEL_WORKSPACE_ARG[@]}" \
  refresh \
  --tracked-only

# Run repo-intel ask for bounded Q&A with citations
python3 "${REPO_INTEL_HOOK}" \
  "${REPO_INTEL_WORKSPACE_ARG[@]}" \
  tool \
  --action ask \
  --issue-summary "${PR_TITLE}" \
  --question "Deep code review: Identify ownership, potential bugs, security issues, and test gaps for these changed files: ${PR_FILES}" \
  --task-kind unknown \
  --pretty
```

**Use `likely_subsystem` hint when PR scope is known:**
```bash
python3 "${REPO_INTEL_HOOK}" \
  "${REPO_INTEL_WORKSPACE_ARG[@]}" \
  tool \
  --action ask \
  --issue-summary "${PR_TITLE}" \
  --question "<question>" \
  --likely-subsystem mm/convex/jobs mm/convex/sportsApi mm/convex/odds \
  --task-kind unknown \
  --pretty
```

**Also run find-tests for nearest proof sites:**
```bash
python3 "${REPO_INTEL_HOOK}" \
  "${REPO_INTEL_WORKSPACE_ARG[@]}" \
  tool \
  --action find-tests \
  --issue-summary "${PR_FILES}" \
  --question "Find tests for: ${PR_FILES}" \
  --pretty
```

Store repo-intel results for Pass 2. Repo-intel provides:
- Term-based likely owners from the codebase vocabulary
- Bounded Q&A synthesis with citations and confidence
- Nearest regression test neighbors (may differ from code-review-graph test gaps)

**Skip this step** if repo-intel hook is not available (review still works with code-review-graph alone).

### Store results for later passes

- Pass 1 uses risk scores and test gaps to prioritize scopes
- Pass 2 uses available graph risk/test-gap data and repo-intel owner/proof hints during review
- Pass 3 uses flow criticality for cross-scope tracing only if an affected-flow tool was actually exposed

## Pass 1: Scope Analysis

Read the full diff (or file list + stats if diff > 2000 lines).

Group changes into **1-5 logical scopes**. A scope is a cohesive unit of
change — not a file, but a concern. Changes across multiple files that serve
the same purpose belong in one scope.

For each scope determine:

- **Name**: 2-5 words describing the concern
- **Files**: which files are involved
- **Nature**: feature | refactor | bugfix | config | test | docs
- **Lenses**: which review lenses apply (see assignment rules below)
- **Risk** (if graph available): highest risk score among the scope's changed functions
- **Flows** (if graph available): count of affected execution flows passing through this scope

Output the scope map as a markdown table (see below).

### Lens assignment

- **Dev**: Always assigned. Every scope gets dev review.
- **Security**: Assign when the scope touches authentication, authorization,
  cryptography, network communication, user input parsing, data
  serialization/deserialization, secrets/environment variables, permissions,
  external service integration, or any code that handles untrusted data.
- **SRE**: Assign broadly. Any scope that adds or modifies code running in
  production gets SRE review — not just infra changes. SRE catches missing
  telemetry, suggests observability improvements, flags resource risks, and
  evaluates operational safety. Skip only for pure docs, tests, or type-only
  changes with no runtime impact.
- **Research**: Always assigned. Every scope gets research review. The other
  lenses review whether the code is correct, safe, and operable. Research
  reviews whether it should exist. This is not optional — the most expensive
  bugs are well-implemented solutions to the wrong problem. Even a 3-line
  bugfix encodes an assumption about the right fix. Research asks whether
  that assumption is right. Per-scope research examines **scope-local**
  assumptions only — PR-level direction questions (wrong problem, wrong
  approach) belong to Pass 1b and Pass 3. Raise them once there; never
  duplicate the same direction-level concern across scopes.

Output the scope map as a markdown table:

```markdown
## Scope Map

| #   | Scope | Files | Lenses        | Nature   | Risk | Flows |
| --- | ----- | ----- | ------------- | -------- | ---- | ----- |
| 1   | ...   | ...   | Dev, Security | bugfix   | 0.65 | 42    |
| 2   | ...   | ...   | Dev, Research | refactor | 0.30 | 8     |
```

(Omit Risk and Flows columns if graph tools are not available.)

### Graph-informed scope prioritization

When graph data is available, review scopes in **descending risk order**. A scope
with risk > 0.5 and many affected flows deserves deeper investigation than a low-risk
scope with few flows. The graph's test gap data also informs which scopes need extra
scrutiny — untested changed functions are higher-risk regardless of the score.

Before Pass 2, turn tool output into a short review checklist:

- Assign every high-risk changed symbol and every graph-reported test gap to a
  scope, or state why it is irrelevant to the PR's runtime behavior.
- Open at least the top repo-intel proof/owner files for each represented
  runtime scope. If repo-intel clusters around only one concern in a multi-scope
  PR, treat it as partial coverage rather than global confidence.
- If affected-flow or impact-radius output is zero/unavailable for a non-empty
  diff, record that as a graph limitation. Do not treat "0 flows" as evidence
  that the PR has no downstream impact.

Then proceed to Pass 1b.

## Pass 1b: PR Design & Problem Validation

Before analyzing what might be wrong, establish what the PR is doing **and
whether that is the right thing to do**. This is an investigation, not a
summary — do not paraphrase the PR description and move on.

Gather evidence first (each step mandatory; note explicitly when a source
does not exist):

1. **The original ask.** Fetch linked issues (`gh issue view`), the PR
   discussion (`gh pr view <N> --json comments`), and any design doc the PR
   references. State the underlying problem in your own words — from this
   evidence, not from the PR title.
2. **The history.** `git log --oneline -15 -- <changed files>`. Has this
   problem been attempted or reverted before? Is the area high-churn?
3. **The data** (when the PR processes data): inspect an actual input. Does
   the pipeline shape match the data shape?
4. **The null hypothesis.** What happens if this PR is never merged — who is
   affected, how badly, how soon? If you cannot answer from the evidence,
   that becomes the first Question for the Author.

Output as a markdown section. Every line must cite its evidence (issue,
comment, log, file) — a problem-fit verdict without cited evidence is
invalid:

```markdown
## PR Design & Problem Fit

**Problem (as evidenced)**: {the problem the evidence shows — may differ from the PR description; say so if it does}

**Approach**: {high-level strategy}

**Design rationale**: {stated or inferred — mark which}

**Established patterns**: {does it follow repo patterns? if not, why?}

**If we do nothing**: {consequence, or "unknown — asked below"}

**Simplest credible alternative**: {what a newcomer would build, and why the PR's approach is or isn't better}

**Problem-fit verdict**: {🟢|🟡|🔴} {one sentence}
```

A 🔴 problem-fit verdict means the rest of the review is secondary: say so
up front, and make it the first item of the actionable output.

Then proceed to Pass 2.

## Pass 2: Adversarial Review by Lens

Now that we understand what the PR is doing, examine it through each lens for issues.

For each scope, for each assigned lens, conduct a reviewer-challenger dialog.
The reviewers ask: Is it solving the right problem? Are there bugs? Are established
patterns followed?

### Lens instructions

Read the lens file before starting each review:

- **Dev**: [lenses/dev.md](lenses/dev.md)
- **Security**: [lenses/security.md](lenses/security.md)
- **SRE**: [lenses/sre.md](lenses/sre.md)
- **Research**: [lenses/research.md](lenses/research.md)

### Dialog protocol

**Step 1 — Reviewer analysis.** Analyze the scope through the lens.
Produce findings with severity markers. Reference specific code using
`` `path/to/file.ts:42` `` and ` ```diff ` blocks.

**Investigation tools (in priority order):**
1. **CLI tools first** (if available): Use `code-review-graph query-graph`
   if the installed CLI exposes such a command. The current CLI may expose only
   `detect-changes`; do not call invalid subcommands.
2. **MCP tools** (if available): Use discovered tools such as
   `detect_changes_tool`, `get_affected_flows_tool`, and
   `get_impact_radius_tool`. Do not assume approximate tool names exist.
3. **Read/Grep/Glob** for anything the graph doesn't cover: exact code content,
   string literals, configuration values, recent git history.

**Mandatory code-derived contract pass.** Tests are verification, not the
primary discovery mechanism. For every runtime scope, reconstruct the behavior
from code before deciding whether it is safe:

1. **Contract map:** list the changed entry points, callers, callees,
   preconditions, postconditions, state transitions, and invariants. For a
   refactor or performance PR that claims "no behavior change", compare old and
   new behavior at the caller boundary; do not accept the claim from comments or
   PR text.
2. **Data semantics:** check null vs absent, malformed vs wrong-shaped but valid
   data, units/conversions, ordering, deduplication, caps, keying/scope, and
   serialization/deserialization boundaries.
3. **Failure matrix:** check empty input, duplicate input, partial success,
   all-failed, thrown error, timeout, stale data, retry, cleanup, and whether
   callers distinguish missing, null, false, and error.
4. **Temporal/lifecycle behavior:** check before/during/after states,
   idempotency, stale actors, concurrent actors, retry cadence, progress across
   repeated runs, and whether old state can be reactivated or stranded.
5. **Resource/operability bounds:** check what consumes bounded budgets, whether
   work drains or repeats the same prefix, whether cost-saving paths preserve
   failure posture, and whether logs/metrics retain enough cause and freshness
   data for incident response.
6. **Boundary/integrity checks:** where applicable, check authorization,
   identity binding, untrusted input, external service trust, and cross-system
   consistency.

The challenger must pick concrete inputs/states from these axes and force the
reviewer to trace them through the changed code. A green verdict is invalid if
it says "semantics preserved" without showing which old/new path was compared.
If an applicable axis cannot be checked because it needs production data or an
external system, state that gap and decide whether it becomes a Question or
Recommendation.

**Candidate preservation audit.** Before writing the final review, build an
internal ledger of every non-style issue candidate raised by any reviewer,
challenger, graph/repo-intel hint, failed check, or unresolved contract gap. For
each candidate, record the changed source ref, the other-end source ref, the
exact branch/input shape, the immediate source-level outcome, the downstream
runtime/build/user/state consequence, affected caller/user/state, confidence,
and disposition.

Preservation rules:

- A source-backed 🟡/🔴 candidate must become a Recommendation or a clearly
  named Finding Ledger row unless another final item covers the same root cause
  and same consequence.
- A rejection must cite the source fact that rejects the same branch and same
  consequence. Evidence for one branch does not reject sibling branches.
- If one changed source location has multiple plausible consequences, enumerate
  the sibling consequences separately before merging or rejecting them.
- Do not demote a reachable invariant mismatch solely because no test was run.
  Put the missing execution proof in the evidence/gap text; keep the candidate
  if source proves reachability and consequence.
- Low-severity style/name candidates may be dropped unless they affect a public,
  runtime, build, or source-visible contract.

**Step 2 — Challenger questions.** Challenge the reviewer's analysis with
2-5 probing questions. Look for:

- Findings that lack evidence ("did you actually verify this?")
- Missing findings ("what about X that you didn't check?")
- Severity inflation or deflation
- Assumptions about author intent
- Alternative explanations

**Step 3 — Reviewer response.** Address each challenge. May revise findings,
add new ones, or defend the original analysis with evidence.

**Step 4 — Convergence check.** If the challenger is satisfied or this is
round 3, emit the verdict. Otherwise return to Step 2.

### Agent dispatch

**When subagents are available** (Task/Agent tool): Dispatch the reviewer
and challenger as separate subagents. Give each the relevant lens file as
context. The reviewer gets codebase access. The challenger gets the
reviewer's output. This provides genuine context separation.

**When subagents are not available**: Simulate the dialog inline. Use
clearly labeled sections. Maintain the adversarial stance — the challenger
must not agree too easily. Switch cognitive frames between roles.

### Per-lens output structure

```markdown
### {Lens} Review

**Reviewer:**
{Analysis with severity markers and code references}

> **Challenger:** {Probing question or challenge}

**Reviewer:**
{Response to challenge, may revise findings}

> **Challenger:** {Follow-up or satisfaction signal}

**Verdict:** {severity marker} {one-sentence summary}
```

## Pass 3: Step Back — Cross-Scope Research Synthesis

After all per-scope reviews complete, run a final research pass that examines
the PR **as a whole**. This pass is the critic to the PR's implicit actor.

The per-scope research reviews ask "should this scope's code exist?" The
step-back pass asks **"should this PR's approach exist?"** — a question that
often can't be answered from inside any single scope.

This pass starts from the Pass 1b problem-fit verdict and re-tests it
against what the detailed review uncovered. It must either confirm that
verdict or change it with new evidence — not re-derive it from scratch,
and not repeat Pass 1b's text.

### What to examine

1. **Trace the full data flow** across all scopes. Count input events vs
   processing steps. If the code creates 60K iterations from 14 data points,
   that's a signal — not a performance issue, a design issue. Name the ratio
   explicitly: "N inputs → M processing steps, ratio M/N = X."

   **When graph data is available**, use the affected flows from Pass 0 to
   ground this analysis. Name the top-criticality flows by name and explain
   which scopes they pass through. If a single change touches flows with
   criticality > 0.7, the risk is structural — not just local. Cross-reference
   the flow paths with scope boundaries to identify coupling between scopes.

2. **The newcomer test** (mandatory, must produce an explicit answer):
   "A competent engineer with no knowledge of this codebase is given the same
   requirements. What would they build?" If the answer is structurally
   different from the PR, explain why the PR's approach is better — or flag
   that it may not be.

3. **Sunk cost audit**: List every decision in the PR that is inherited from
   prior code rather than made fresh. For each, ask: "If we were starting
   today, would we make this same choice?" Inherited decisions are not
   automatically wrong, but they must be examined — not assumed.

4. **The deletion test**: "What would we lose if we deleted this PR entirely
   and wrote 50 lines of the simplest possible thing?" If the answer is
   "not much," the PR may be over-engineered. If the answer is "we'd lose
   important correctness guarantees," the approach is justified.

### Output

Add a section after all per-scope reviews:

```markdown
## Step Back: Cross-Scope Research

**Data flow**: {input} → {transformations} → {output}. Ratio: {N}:{M}.

**Critical flows touched** (if graph available):
- {flow name} (criticality {score}) — passes through scopes {N, M}
- {flow name} (criticality {score}) — passes through scope {N} only
{what this tells us about coupling and risk}

**Test coverage gaps** (if graph available):
- {function name} — {why this gap matters given the change}

**Newcomer test**: {what they'd build} vs {what the PR does}.
{why the difference exists — sunk cost, good reason, or unexamined}

**Inherited decisions**: {list}

**Verdict**: {severity} {summary}
```

This verdict can override per-scope verdicts. Well-implemented code that
collectively solves the wrong problem is 🔴 Critical regardless of how
many 🟢 Good verdicts individual scopes received.

## Combined Analysis (code-review-graph + repo-intel)

When **both** code-review-graph and repo-intel are available, combine their outputs in a single analysis section:

```markdown
## Graph Analysis (code-review-graph + repo-intel)

**code-review-graph findings:**
- Risk score: {score}
- High-risk changed functions: {list from detect-changes}
- Test coverage gaps: {list from detect-changes}
- Affected flows: {top 10 if tool exposed; otherwise "unavailable"}
- Impact radius: {top files if tool exposed; otherwise "unavailable"}

**repo-intel findings:**
- Likely owners: {file1}, {file2}
- Owner terms: {term1}, {term2}
- Nearest proof sites: {test1}, {test2}
- Confidence: {high/medium/low}
- Missing test hint: {hint if any}
```

If only one tool is available, note which and proceed:
- **code-review-graph only**: Use its risk scores and test gaps
- **repo-intel only**: Use its owner/proof hints, skip flow criticality
- **Neither**: Skip Pass 0, proceed with diff-only analysis

## Large PR handling

If the diff exceeds ~2000 lines:

1. **Pass 0**: Graph reconnaissance is *especially* valuable here — `detect_changes`
   gives risk-prioritized scope without reading every line; include affected-flow
   data only when a discovered MCP tool exposes it
2. **Pass 1**: Use file list and stats only — `gh pr view N --json files`
3. **Pass 2**: Fetch per-scope diffs — `gh pr diff N -- path/to/relevant/dir`.
   Start with the highest graph-risk scopes.
4. Focus investigation on the highest-risk scopes first
5. If a scope is too large to analyze fully, note what was not examined

## Verification and dependency bootstrap

Run focused local verification when the changed surface has nearby tests or a
cheap type/static check. For scheduled detached-worktree reviews, assume
untracked dependency directories such as `node_modules` may be absent unless the
runner linked them in.

If a test or check fails because the runner binary or package is missing
(`command not found`, `Cannot find module`, missing `node_modules`, missing
Vitest/Jest/pytest/etc.), do not stop there. First:

1. Identify the affected package directory and package manager from lockfiles
   and `packageManager` fields.
2. If package files changed in the PR, prefer a fresh install over any linked
   dependency directory.
3. Run the deterministic install for that package before retrying verification:
   `npm ci` for `package-lock.json`, `pnpm install --frozen-lockfile` for
   `pnpm-lock.yaml`, `yarn install --frozen-lockfile` for `yarn.lock`, or
   `bun install --frozen-lockfile` for `bun.lockb`.
4. If there is no lockfile, use the repo's documented install command if one is
   present; otherwise report that the install path is ambiguous.
5. After installing, rerun the focused tests/checks. If install fails, record the
   exact install command and the failure reason in the review.

Only say verification could not run after the install path was attempted or
shown to be ambiguous. A GitHub comment that says a test runner is not installed
must also say what install command was attempted.

## Output format

See [output-format.md](output-format.md) for the complete output structure.

Key conventions:

- H1 = PR title with number
- H2 = scope map + per-scope sections + overall verdict
- H3 = lens findings, dialog rounds, verdict
- Severity: `🔴 Critical` `🟡 Caution` `🟢 Good` `⚪ Neutral`
- Code refs: `` `path/to/file.ts:42` `` inline
- Diff blocks: ` ```diff ` fenced code
- Challenger dialog: blockquotes with `**Challenger:**` prefix
- End with `### Questions for the Author`, `### Recommendations`,
  `### Findings Ledger`, then `### Short version` — built per the
  Actionable Output rules below
- `### Short version` should be brief, plain-English, and sound human — a
  teammate who hasn't read the diff or the review should understand it
  without looking anything up

## Actionable Output

The Questions and Recommendations are the part of the review the user may
actually send to GitHub. Build them with an explicit dedup pass — do not
concatenate per-lens findings:

1. Collect every candidate question and recommendation from all scopes,
   lenses, and the step-back pass.
2. **Cluster by root cause.** Items pointing at the same underlying decision
   are ONE item, even if three lenses discovered them independently. Name
   the root cause, not each symptom.
3. **Preserve source-backed candidates.** Run the Candidate preservation audit
   before applying caps. If a source-backed 🟡/🔴 candidate is not posted as a
   Recommendation, the Findings Ledger must explain whether it was merged into
   another item, rejected by a source fact, or left as an unresolved gap.
4. **Question vs recommendation.** If the review knows what should change,
   it's a recommendation. Only genuinely unresolved uncertainties — things
   that could not be determined from the code — are questions. Never both
   for the same point.
   - **Self-answer gate.** Before a candidate question makes the list, try
     to answer it yourself with the tools at hand (grep/read the repo, git
     log/blame, check tests and call sites). If the question contains its
     own investigation plan ("grep the repo", "check the callers", "is X
     dead code?"), that is a signal you must run it, not ask it. A resolved
     question becomes a finding or recommendation (or is dropped); only
     what remains unanswerable from the repo — author intent, product
     decisions, ops policy, external systems — may stay a question.
5. **Caps**: ≤5 questions, ≤7 recommendations, each 1-2 sentences with a
   severity marker and a `file:line` ref. Drop the lowest-severity overflow
   (it stays in the per-scope sections for the record).
6. **Stable IDs**: `Q1, Q2…` / `R1, R2…`. On re-review, keep prior IDs and
   continue numbering; never reuse a retired ID.
7. **Re-review**: resolved items appear once under **Resolved** (ID + one
   clause + the resolving commit/comment). Still-open items keep their ID
   and may be escalated. Only genuinely new findings get new IDs.
8. **Self-contained plain sentences.** Each item must be understandable by
   someone reading only the GitHub comment — they did not watch the review
   happen. Complete sentences naming the code, the problem, and the
   consequence, then the ask or change. Never sentence fragments
   ("Schedule for the X flag follow-up?"), arrow chains (`A → B → fails`),
   or shorthand coined earlier in the review ("the exact incident
   signature", "Scope 2's helper") — say what is meant in place. Give an
   unfamiliar identifier its role on first mention: "`probeMintDrift` (the
   mint health check)", not the bare name.
9. **Severity claims carry their consequence.** A 🔴 or 🟡 must state what
   breaks and for whom ("loses payment events on restart"), not leave the
   reader to infer why the marker is there.

Maintain a `### Findings Ledger` table, cumulative across rounds:

```markdown
| ID | Sev | Scope | Finding | Status |
| R1 | 🔴 | 2 | Rollback writes after confirm | open (r1) |
| Q1 | 🟡 | 1 | Why poll instead of webhook? | resolved (r2: author comment) |
```

### GitHub comment draft

Assemble a ready-to-post review comment containing exactly these sections, in
this order: Short version, Questions for the Author, Recommendations. Do not
include Delta Since Last Review, Findings Ledger, scope details, graph analysis,
or any other section in the comment draft. Append the signature:
`Codex on behalf of Sasha`. Write it to `${REVIEW_DIR}/<short-sha>-comment.md`.
Do not duplicate the draft inline in the chat; mention the path. Offer (but
never run unprompted):

```bash
gh pr review <N> --comment --body-file "${REVIEW_DIR}/<short-sha>-comment.md"
```

On re-review, keep the draft to the same three sections. The Short version may
summarize whether there was a delta; Questions and Recommendations should list
only currently relevant items. A reviewer reading it on GitHub should not see
internal review bookkeeping.

## Persist the review

Before ending the turn, write the **full review output** (everything from the H1 PR title through the `Short version` section) to the out-of-repo review directory so the user can find it later without scrolling back through the chat.

```bash
REPO_NAME="$(basename "$(git rev-parse --show-toplevel)")"
SHORT_SHA="$(git rev-parse --short "${NEW_HEAD:-HEAD}")"   # the reviewed head
REVIEW_DIR="$HOME/reviews/${REPO_NAME}/PR-<N>"
mkdir -p "${REVIEW_DIR}"
# Write ${REVIEW_DIR}/${SHORT_SHA}.md and ${REVIEW_DIR}/${SHORT_SHA}-comment.md
```

- One file per reviewed head SHA — rounds never overwrite each other.
  Re-reviewing the same SHA (user asked to re-examine) overwrites that
  SHA's file only.
- The header MUST still record the full head SHA and the round number, and
  list prior rounds (`Round 2 — r1: 2026-06-01 @ abc1234`).
- The Findings Ledger in the newest file is cumulative across all rounds —
  it alone is enough to resume; older round files are history.
- The file content is the same markdown you produced inline. Do not abbreviate. Keep the H1 title, scope map, per-scope dialogs, step-back, overall verdict, Questions for the Author, Recommendations, Findings Ledger, and Short version.
- In the chat, after writing the files, mention the paths explicitly (one line: `Wrote ~/reviews/<repo>/PR-<N>/<short-sha>.md`).
- Reviews live outside the repo by design — never write them into the repo
  tree, and never commit them.

This is what makes the review repeatable: future operators (or the same operator a week later) can read the newest file in `~/reviews/<repo>/PR-<N>/` directly rather than re-running the skill.

## After the review

Stay in the conversation. The user may:

- Ask to drill into a specific finding
- Re-review a scope with different assumptions
- Examine related code not in the diff
- Generate PR review comments: `gh pr review N --comment --body "..."`
- Post individual line comments: `gh api repos/{owner}/{repo}/pulls/{N}/comments`

## What this review is NOT

- Not a rubber stamp. If the PR is bad, say so.
- Not a style nitpick generator. Focus on what matters.
- Not a replacement for running the code. Suggest tests, don't simulate them.
- Not a single-lens tool. The research lens exists to ask whether the code
  should exist at all, not just whether it's well-written.

## CLI vs MCP vs Repo-Intel

The skill uses three tools in priority order:

1. **code-review-graph CLI** (primary for Pass 0): currently `detect-changes`
2. **code-review-graph MCP** (fallback or enhancement): use only discovered tools, commonly `detect_changes_tool`; `get_affected_flows_tool` and `get_impact_radius_tool` may be available even when the CLI lacks equivalent subcommands
3. **repo-intel** (enhancement for Pass 0e and Pass 2): bounded owner/proof localization + find-tests

Detection order for code-review-graph:
- **CLI**: `code-review-graph detect-changes --repo "$PWD" --base <ref>` via bash
- **MCP**: use `tool_search` and then discovered tools such as `detect_changes_tool`, `get_affected_flows_tool`, and `get_impact_radius_tool`
- **None**: Skip Pass 0 code-review-graph, proceed with repo-intel if available

Repo-intel is **always run if available**, even if code-review-graph provides data:
- Provides different perspective (term-based vs graph-based)
- May surface owners/tests code-review-graph misses
- Bounded Q&A with confidence and citations

If repo-intel hook is not available, skip Step 0f and proceed — review still works with code-review-graph alone.
