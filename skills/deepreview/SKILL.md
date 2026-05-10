---
name: deepreview
description: >-
  Performs adversarial three-step PR review: scopes changes, summarizes PR
  design and approach, then runs reviewer-challenger dialogs through dev,
  security, sre, and research lenses. Outputs structured markdown with severity
  ratings and verdicts. Use when given a PR number, PR URL, or asked to review
  a pull request.
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

# Fetch PR metadata (include merge state)
gh pr view <N> --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles,url,state,mergeCommit

# Fetch the diff
gh pr diff <N>
```

If `gh` is not installed or not authenticated, stop and tell the user.

### Compute the graph base ref

Graph tools (`detect_changes`, `get_affected_flows`, `get_impact_radius`) diff the
working tree against a `base` ref. If you pass the wrong ref, the diff is empty and
the tools return zero results.

**The problem:** For merged PRs, `HEAD` already includes the PR's changes. Diffing
against the base branch (e.g. `main`) produces an empty diff because the merge commit
is the tip of `main`.

**Compute `GRAPH_BASE` before Pass 0:**

```bash
# Get the PR's merge status and refs
STATE=$(gh pr view <N> --json state --jq '.state')
BASE_BRANCH=$(gh pr view <N> --json baseRefName --jq '.baseRefName')
HEAD_BRANCH=$(gh pr view <N> --json headRefName --jq '.headRefName')

if [ "$STATE" = "MERGED" ]; then
  # For merged PRs: use the merge commit's first parent (the base branch before merge)
  MERGE_COMMIT=$(gh pr view <N> --json mergeCommit --jq '.mergeCommit.oid')
  GRAPH_BASE="${MERGE_COMMIT}^1"
  # Verify it produces a real diff:
  # git diff --stat ${GRAPH_BASE}..${MERGE_COMMIT} should show the PR's files
else
  # For open PRs: use the merge base between head and base branch
  GRAPH_BASE=$(git merge-base "origin/${BASE_BRANCH}" "origin/${HEAD_BRANCH}")
fi
```

Use `GRAPH_BASE` as the `base` parameter for all graph tool calls in Pass 0.
If `GRAPH_BASE` cannot be computed (e.g. branch deleted, shallow clone), fall back
to `HEAD~1` and note the limitation.

## Pass 0: Graph Reconnaissance (if code-review-graph available)

Before reading the diff, check whether `mcp__code-review-graph__detect_changes_tool`
is available. If it is, run graph analysis **first** — it's faster, cheaper, and gives
structural context (callers, dependents, flows, test coverage) that file scanning cannot.

**Step 0a — Detect changes.** Run `detect_changes` with the PR's changed files
and `GRAPH_BASE` (computed in the Input section) as `base`. Use `detail_level="minimal"`
and `include_source=false` to keep token cost low. This returns:

- Risk-scored list of changed functions/classes
- Test coverage gaps (functions lacking tests)
- Overall risk score
- Affected communities

**Step 0b — Affected flows.** Run `get_affected_flows` with the same changed files
and `GRAPH_BASE` as `base`. This returns execution paths (HTTP handlers, tests, CLI
commands) that pass through the changed code, sorted by criticality. Extract the
**top 10 highest-criticality flows** — these are the paths most likely to break.

**Step 0c — Impact radius.** Run `get_impact_radius` with `detail_level="minimal"`
and `GRAPH_BASE` as `base` for the highest-risk changed files only. This shows the
blast radius in terms of dependent functions and files.

**Step 0d — Validate results.** If `detect_changes` returns 0 changed functions
despite a non-empty diff, the `base` ref is likely wrong (common for merged PRs).
Debug: run `git diff --stat ${GRAPH_BASE}..HEAD` to verify the ref produces a diff.
If empty, recompute `GRAPH_BASE` and retry before proceeding.

Store these results — they feed into every subsequent pass:
- Pass 1 uses risk scores and test gaps to prioritize scopes
- Pass 2 uses affected flows and impact radius during reviewer investigation
- Pass 3 uses flow criticality for cross-scope data flow tracing

If graph tools are **not** available, skip this pass entirely and proceed as before.

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
  that assumption is right.

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

Then proceed to Pass 1b.

## Pass 1b: PR Design Summary

Before analyzing what might be wrong, write a clear description of **what the PR is doing**.

Answer these questions:

- **What problem does this PR solve?** (from the PR description and code)
- **What approach does it take?** (the high-level strategy, not implementation details)
- **Why this approach?** (stated or inferred design rationale)
- **Does it use established patterns in the repo?** (reference prior art if applicable)

Output as a markdown section:

```markdown
## PR Design

**Problem**: {what needs to be fixed or added}

**Approach**: {high-level strategy}

**Design rationale**: {why this approach was chosen}

**Established patterns**: {does it follow repo patterns? if not, why?}
```

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
1. **Graph tools first** (if available): Use `query_graph` with `callers_of` /
   `callees_of` / `tests_for` to trace relationships. Use `get_impact_radius`
   on specific changed functions to understand blast radius. Use
   `semantic_search_nodes` to find related patterns in the codebase.
2. **Read/Grep/Glob** for anything the graph doesn't cover: exact code content,
   string literals, configuration values, recent git history.

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

## Large PR handling

If the diff exceeds ~2000 lines:

1. **Pass 0**: Graph reconnaissance is *especially* valuable here — `detect_changes`
   and `get_affected_flows` give you risk-prioritized scope without reading every line
2. **Pass 1**: Use file list and stats only — `gh pr view N --json files`
3. **Pass 2**: Fetch per-scope diffs — `gh pr diff N -- path/to/relevant/dir`.
   Start with the highest graph-risk scopes.
4. Focus investigation on the highest-risk scopes first
5. If a scope is too large to analyze fully, note what was not examined

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
- End with `### Questions for the Author`, then `### Recommendations`, then `### Short version`
- `### Short version` should be brief, plain-English, and sound human

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
