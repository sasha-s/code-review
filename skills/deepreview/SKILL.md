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
gh pr view <N> --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles,url,state,mergeCommit,commits

# Body edit time drives the Step 0g provenance check and is NOT exposed by
# `gh pr view`. Fetch it explicitly; when null, fall back to `createdAt`.
# Fetch AUTHORED dates too: `gh pr view --json commits` reports `committedDate`,
# which a rebase rewrites to the rebase time on every commit. Step 0g must
# compare against `authoredDate`. (Measured: 34.3% of PRs here carry rebased or
# amended commits, and 15.1% get a wrong post-body commit count from
# `committedDate` — one reports 64 commits against a true 39.)
gh api graphql -f query='{repository(owner:"<OWNER>",name:"<REPO>"){
  pullRequest(number:<N>){ createdAt lastEditedAt
    commits(first:250){nodes{commit{oid authoredDate committedDate
      messageHeadline messageBody}}}}}}'

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
REVIEW_DIR="${DEEPREVIEW_REVIEW_DIR:-$HOME/reviews/${REPO_NAME}}/PR-<N>"
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
2. **Review only the delta — with two mandatory exceptions.** Run the passes on
   the incremental diff plus any code an open finding points at. Do not
   re-derive findings on unchanged code; an unchanged scope gets one line
   ("unchanged since round {k}"). **Except:**
   - **Error-boundary changes re-open their callees.** If the delta adds,
     removes, moves, or widens a `try`/`catch`, a transaction boundary, a
     retry, or any other error handler, every function it now wraps is back
     in scope *even though unchanged*. Catching an error changes what stays
     committed, so write ordering inside the callee that was irrelevant last
     round becomes load-bearing this round. Walk the callee's writes in order
     and name what survives a throw at each step. (Observed failure: a
     per-order `catch` added at a settlement call site made an escrow
     decrement commit ahead of the status patch it was paired with, stranding
     orders in a non-terminal state — the callee was unchanged and was
     skipped on that basis.)
   - **A behaviour change re-opens its published surface.** If the delta
     changes what an endpoint/CLI/API accepts or returns, grep the contract or
     docs for that parameter's **examples**, not just its schema. A shipped
     example the new behaviour rejects is a contract break. (Observed failure
     twice: a declared default and a documented filter example, both rejected
     by newly-added validation nobody checked the document for.)
3. **A delta implementing a prior recommendation puts the recommendation
   itself under review, not just its implementation.** Conformance is not
   correctness. Do not ask "did they do what round {k} said?" — ask "is what
   round {k} said right for *this* call site?" This matters most when the
   recommendation said to copy a pattern from elsewhere in the codebase:
   state explicitly what made the pattern safe at its original site and
   verify that property holds here. If the reviewer wrote the prior
   recommendation, say so in the round header and treat the reviewer as a
   non-independent frame for that item — the review has no adversary on it.
4. **Never restate.** A prior question or recommendation may reappear only if
   still-open, referenced by its ID — not rephrased as if new.
5. **Same head, no new comments** → tell the user nothing changed and ask
   what they want re-examined instead of redoing the same review, unless
   the user or scheduler explicitly requested a forced re-review.

   **Forced same-head mode inverts rule 2.** The delta is empty, so "review
   only the delta" would instruct you to produce nothing — do not follow it
   here. Instead:
   - Re-derive on the highest-risk **unchanged** code, choosing targets by
     consequence rather than by recency.
   - You **may re-open findings a prior round marked resolved**. A prior
     round's "resolved" is that round's own judgment, not an author
     confirmation, and forced mode exists because someone doubts it.
   - Set `GRAPH_BASE` to the PR's real base (merge-base or `mergeCommit^1`),
     **not** `${PRIOR_HEAD}` — at the same head that is an empty diff, and
     Pass 0 would return nothing while Step 0e sent you chasing a wrong base
     ref that is in fact correct.
   - **On a MERGED PR the diff is not empty — it is wrong, which is worse.**
     The worktree checks out the *merge commit*, so `${PRIOR_HEAD}..HEAD`
     picks up everything merged from the base branch in between. Observed: 57
     files and 6,591 insertions of unrelated main-branch work, i.e. following
     the instruction literally means reviewing other people's PRs and
     attributing their code to this author. **Always diff against
     `mergeCommit^1`** for a merged PR, and if the file list contains paths no
     scope explains, stop and re-derive the base before reviewing anything.
   - Overwrite that SHA's artifacts with the fresh verification.
6. **Delta size never justifies skipping the contract pass.** A small repair
   round is not a cheap round. The mandatory code-derived contract pass in
   Pass 2 — especially the failure matrix (thrown error, partial success,
   cleanup) — runs on every repair delta regardless of line count. Risk
   tracks *what the change touches and who specified it*, not how many lines
   it is.
7. **The PR body and title are re-checked every round, even though they are
   never in the delta.** Re-review moves the "Problem (as evidenced)" anchor to
   the prior review ledger and the new commit messages, and the body silently
   stops being read. Re-run **Step 0g** each round and restate its one-line
   verdict in the round header — but Step 0g is **provenance only, and an "in
   sync" verdict does not discharge this rule.**

   **Carry the CLAIMS, not the pin.** Maintain a body-claims table in the
   ledger. Populate it at round 1 and carry it forward:

   - **Select by assertion shape, never by formatting.** A claim is any
     sentence or list item that (a) carries a code identifier — backticked,
     camelCase, snake_case, or a bracketed field list — or a quantity, and
     (b) asserts a property with a verb like *is / are / never / only /
     preserves / copies / indexes / derives / bounded / disagree / must*.
     **Bullets count.** Do not require bold or a normative keyword: many
     authors use neither, and a selector keyed on formatting silently reads
     such a body as almost claimless. (Observed: on a claim-dense 47-line
     body a formatting-keyed selector took 2 of ~8 verifiable claims, and the
     six it dropped — `archiveMarketOrders` now preserving `clientOrderId`,
     both tables indexing `[traderId, clientOrderId, clientLookupSortKey]`,
     `sequence` never being copied, `nonce` unique only in the live table, the
     `2 * (N + 1)` page bound, the compound-key cursor — were exactly the ones
     a reader would build code from.)
   - **Exclude** only what Step 0g already owns deterministically: SHA pins,
     commit counts, trailer and check-run status. Keep verification *counts*
     ("29 focused tests", "516 edge files") — those go stale silently and are
     nobody else's job.
   - Record each one **verbatim, one line**, with the `file:line` **at head**
     that backs it. **A fragment is verified as its enclosing clause.** If the
     selected span is a noun phrase that asserts nothing standing alone —
     a bolded `` `Order.{a, b, c}` are chain-scoped `` inside a longer
     sentence — record the enclosing clause, which is what is actually
     falsifiable, and note the widening. Verifying the fragment as written is
     vacuous, and "record it verbatim" must never be read as licence to test
     something unfalsifiable.
   - Measured budget for **this** selector over 166 real PR bodies: **median 9,
     p75 12, p90 17, p95 20, max 26** claims — one `file:line` lookup each.
     **Cap the table at 20**, which truncates only 3% of bodies; past the cap,
     keep first the claims the **title** echoes, then those naming a symbol the
     diff touches. Note this is ~4.5× the cost of a formatting-keyed selector,
     and that is the correct price: the cheap version was cheap because it was
     missing claims, and a low claim count measures the selector, not the body.

   **Verify at every round including round 1.** For each claim, name the
   `file:line` at head that still states it, or mark it **CONTRADICTED** and
   cite the commit that reversed it. A claim you cannot locate at head is
   contradicted, not merely unlocated. Any CONTRADICTED claim is a
   Recommendation in its own right, at the severity of the wrong thing a reader
   would build from it. Do not resolve a claim by re-reading the body — that is
   circular; settle it against head.

   (Validated against two observed misses on the same PR, #1223. **(a) The
   seq-floor claim** — "Snapshot `seq` is a per-page replay floor, not a cursor
   pin; `getPositionsSnapshot` qualifies" — was reversed by `3ab8c5200` "anchor
   both paginated snapshots exactly". Missed at rounds 3 and 4; rounds 1 and 2
   were correctly silent because it was still true then. Round 3 quoted that
   commit's message saying positions had become exact, two paragraphs from
   where the comparison would have happened. **(b) The chain-scope claim** —
   "`Order.{quantity, filledQuantity, remainingQuantity}` are chain-scoped" —
   was reversed for `remainingQuantity` by `a03a6147b` at 22:21:19Z, and the
   body was written at 22:44:18Z, twenty-three minutes later. It was false the
   moment it was written, was already contradicted at round 1's head
   (`openapi.yaml:6306` read "NOT chain-scoped" there), survived all four
   rounds *and* the author's own remediation edit, and is still in the merged
   description. **No provenance check can ever reach (b)** — the body's
   effective time is after the reversal, so Step 0g correctly reports "in
   sync". That is why this rule runs independently of Step 0g, and why round 1
   must verify rather than merely extract: an extract-only round 1 would have
   recorded (b) and still shipped it.)

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
**Except in forced same-head mode**, where `${PRIOR_HEAD}` *is* the head and the
diff is empty by construction: use the PR's real base there, or Pass 0 returns
nothing and Step 0e sends you recomputing a base ref that was already right.

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

If empty, recompute `GRAPH_BASE` and retry before proceeding. In forced
same-head mode an empty diff is expected, not a wrong base — see re-review
rule 5 before recomputing anything.

**A zero result on a non-empty diff also means the index is empty.** If the
tool logged a schema migration or an index build on *this* invocation — e.g.
`Schema version 1 -> 6: running migrations` — it built a fresh empty index for
this worktree path and its zero is meaningless, not a finding. Check the tool's
own output before concluding anything from a zero. (Observed: 0 changed
functions, 0 flows, risk 0.00 on a genuinely non-empty 8-file diff, purely
because the worktree path was new to the index.) Rebuild or point at the
existing base graph, or record graph output as unavailable — never report
risk 0.00 as evidence of low risk.

**Also validate the tree, not just the count.** A substantive-looking result is
not a valid one. Check that the returned symbol paths actually exist in the
worktree you passed via `--repo`:

```bash
# every path the graph reports should resolve inside the review worktree
ls "${WORKTREE}/<one reported path>"
```

If the paths resolve against the caller's checkout rather than the worktree,
the whole result is scored against the wrong tree and must be discarded — the
counts and risk scores will still look plausible. (Observed: a run reported
risk 0.60, 72 changed functions and 38 test gaps computed against the wrong
tree; two of its four highest-risk symbols had been **deleted** by the PR under
review, and its ranking pointed away from every file where the findings
actually were.) Validating only "0 changed functions returned" is blind to
this. Note in the review that graph risk is anchored to the base graph, so
PR-head-only files may be absent from it entirely.

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

### Step 0g — Description↔head provenance (deterministic; no model reasoning)

The PR body and title are shipped artifacts, not just evidence. The title
lands in the merge commit, and for a docs/spec PR the body's ruling **is** the
deliverable. This step is timestamp and string comparison only — do not spend
reasoning on it, and do not skip it because the body "looks fine".

Inputs are already fetched: the body, its `lastEditedAt`, and `commits`.

1. **Commits after the body's effective time.** Compare against each commit's
   **`authoredDate`, never `committedDate`** — a rebase rewrites every
   committer date to the rebase timestamp, which fabricates the count on ~15%
   of PRs here. If only `committedDate` is available, say so on the output line
   rather than reporting a number you cannot stand behind.
   The body's effective time is
   **`lastEditedAt` if present, otherwise `createdAt`** — never treat a null
   `lastEditedAt` as unknown. GitHub returns null there when the body has
   **never been edited since it was written**, in which case `createdAt` is
   the body's authoritative timestamp and provenance is fully checkable. This
   is the common case, not the exception: `lastEditedAt` is null on ~54% of
   PRs, so reading null as "unknown" makes this step inert on the majority of
   reviews. Count the commits that landed after the effective time. **If that
   count is zero, this step reports "in sync" and stops** — every check below
   requires at least one commit after the body's effective time.
2. **Stale pin.** If the body cites a commit SHA on this branch, report how
   many commits behind head it is. If the body states a commit count, compare
   it to the real count.
3. **Two suppressions, both mandatory.** Firing without them punishes the exact
   remediation we want — an author who documents their own reversal:
   - If the body cites **head** at all, every older SHA it cites is history,
     not a stale pin. Suppress the pin check entirely.
   - A SHA cited on the same line as a strictly **newer** cited SHA is a
     transition (`` `A` → `B` ``), not a claim about what the PR describes.
   Both are structural — they do not depend on past tense, "originally", or
   blockquote formatting, so they generalize past one PR's phrasing.

Emit one line into the review, **always, including when clean**. Say which
timestamp the effective time came from, so the reader can tell whether the
author ever revisited the body:

    **Description↔head:** in sync
    **Description↔head:** body last edited T; N commits since; body pins `X` (K behind); body says N commits, actual M
    **Description↔head:** body written at PR creation and never edited; N commits since; body pins `X` (K behind)
    **Description↔head:** UNAVAILABLE — no `createdAt` or `lastEditedAt` available, provenance not checked

The `UNAVAILABLE` form is reserved for the genuine failure: **both** timestamps
missing, or the GraphQL call failing. A null `lastEditedAt` alone is **not**
that case — fall back to `createdAt` and run the check.
**Never omit the line and never silently pass** — a check that can disappear
without anyone noticing is how this class of defect survived four review rounds
on PR #1223. (Observed failure of this very step: its first live run on PR
#1214 emitted `UNAVAILABLE` on a null `lastEditedAt` while holding a perfectly
good `createdAt`. Visible-and-inert is still inert.)

Report the edited/never-edited distinction as fact, not as severity. Across 166
multi-round PRs, never-edited bodies sit a median of 3 commits behind head
against 0 for edited ones — authors typically revise the body last — but
*conditional on this step firing* the two groups are equivalent (median 4.5 vs
5.0 commits). So an unedited body means more exposure in the population, not a
worse finding in the individual case.

**"Fires" means a pin or count discrepancy — not a commit count.** Commits
landing after the body's effective time is the *precondition* for the check,
not a finding: 57% of PRs have that and nothing else, and treating it as a
firing would push work into Pass 1b on 74% of reviews instead of 17%. Report
the commit count on the line for context and stop there. Only a surviving
stale pin or a wrong stated commit count escalates.

When it does fire, Pass 1b must state whether the body's stated deliverable
still describes head, and a divergence becomes a Recommendation in its own
right, not a footnote.

**Holding both halves at once.** The body is never *evidence* for what the PR
does — Pass 1b is right to derive the problem from issues, commits and code
rather than from the description. But the body and title are also *shipped
artifacts* whose claims can be wrong, and for a docs/spec PR the ruling they
state **is** the deliverable. These are not in tension once the roles are
separated: **never believe the body; always check it.** Read it only as a set
of falsifiable claims about head, never as a source of truth about the change.
Resolving "does the body still describe head?" by re-reading the body is
circular; every claim must be settled against a file:line at head.

Evidentiary basis, for whoever tunes this next: the two suppressions were
validated on PR #1223 as a positive→negative pair (fires at rounds 2/3/4 on
the stale body; silent at round 1 and silent again after the author fixed the
title and changelogged the reversal) plus a zero-regression run over 166
multi-round PRs — identical firings before and after. Only 7 of those 166
bodies anchor on head at all, so the suppression is not yet validated on a
large sample of the pattern it protects.

### Store results for later passes

- Pass 1 uses risk scores and test gaps to prioritize scopes
- Pass 2 uses available graph risk/test-gap data and repo-intel owner/proof hints during review
- Pass 3 uses flow criticality for cross-scope tracing only if an affected-flow tool was actually exposed

## Pass 1: Scope Analysis

Read the full diff (or file list + stats if diff > 2000 lines).

Group changes into logical scopes. A scope is a cohesive unit of change — not
a file, but a concern. Changes across multiple files that serve the same
purpose belong in one scope. Aim for **1-5 scope narratives** to keep the
document readable, but that is a bound on *narratives*, never on *coverage*:

**Every changed file must be assigned — to exactly one scope, or to an explicit
not-reviewed bucket with a stated reason.** A file that appears in neither is a
defect in the scope map. Each scope must also list which of its files were
actually opened, as against merely named. Every cost in this skill is paid per
scope (lens dialogs, the contract pass, the reviewer/challenger loop), so with
a fixed scope cap and no assignment obligation, cost stays constant while
coverage silently absorbs PR size. That is the failure this obligation exists
to prevent: a 64-file, 12,325-line PR received a 370-line review covering 17.3%
of changed lines, with 36 of 64 files never opened and 52 absent from the scope
map entirely — and the scope table looked complete because it was internally
consistent.

**Size increases work, it does not reduce it.** A bigger diff means more scopes
and more files opened, not the same scopes read more thinly. If you cannot open
a file, that is a not-reviewed entry with a reason, not silence.

For each scope determine:

- **Name**: 2-5 words describing the concern
- **Files**: which files are involved
- **Nature**: feature | refactor | bugfix | config | test | docs
- **Lenses**: which review lenses apply (see assignment rules below)
- **Risk** (if graph available): highest risk score among the scope's changed functions
- **Flows** (if graph available): count of affected execution flows passing through this scope

Output the scope map as a markdown table (see below).

### Lens assignment

**Assignment is per scope, and a lens may be declined per scope.** For each
lens below other than Dev, either assign it or record one line saying why this
scope does not need it — `Security: declined, no untrusted input in this
scope`. A declined lens costs one line; an assigned lens owes real findings.

Do not write a lens section that restates the scope without a finding. On a PR
shipping runtime code everywhere, 11 lens sections produced ~8 distinct
contributions with 4 concentrated in a single scope, and Security and SRE were
rehearsals on 3 of 4 runtime scopes. Those rehearsals crowd out the reader's
attention and inflate the review's apparent thoroughness. The previous
always-assigned mandate was in practice routinely violated — the reviewer
silently dropped Research from one scope, Dev from another, and SRE and
Research from a third, precisely because the rehearsals were empty. Relaxing it
deliberately is better than leaving a mandate that is ignored.

This relaxes *assignment*, not rigour. **The reviewer/challenger dialog is not
optional and is not weakened** — it is the highest-yield element in this skill.
One challenger question ("explain why your probe disagrees with a green test
exercising the same entry point") produced the finding that explained why nine
prior rounds had missed a bug. An assigned lens runs its full dialog.

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
7. **Mutation control on the cited proof.** Where the PR adds or points at a
   test suite as the proof of a behavior, and the suite can actually be run,
   break the load-bearing expressions one at a time and record which mutations
   the suite **kills** and which it **survives**. Budget ~6 mutations; measured
   at roughly 90 seconds with dependencies already installed.
   Report it as a table, because the *pattern* is the finding, not any single
   survivor. A clean split between killed behavioural mutations and surviving
   encoder mutations says "every behavioural invariant is proven and the entire
   encoder is unproven", which is far sharper — and far more actionable — than
   "there is a proof gap". When mutations survive, name the root cause: a suite
   whose assertions all compare a stored value against the same function's
   output has no literal anchor anywhere and cannot catch an encoder change.
   Then check whether sibling call sites share the pattern, since an unproven
   encoder is usually repo-wide rather than PR-local.

   **This is verification, not simulation.** "Suggest tests, don't simulate
   them" under *What this review is NOT* forbids inventing test results and
   asserting what a test would do. Running an existing suite against a
   deliberately broken input and reporting the observed outcome is neither
   simulating nor suggesting — it is the strongest evidence available about
   whether a proof constrains anything. Restore every mutated source byte-for-
   byte and say so.

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
5. If a scope is too large to analyze fully, note what was not examined —
   as a **not-opened entry in the coverage ledger with a reason**, never as a
   passing remark in prose. This instruction is a reporting requirement, not
   permission to skip: it does not convert incomplete coverage into a complete
   review.
6. **Scale the work up, not down.** Every other instruction in this section
   reduces effort per line, which is correct for *how* to read a large diff and
   wrong for *how much*. A diff 10× the size gets more scopes and more files
   opened. Budget the coverage ledger first — decide what you will open before
   you start writing — and if the honest answer is that a meaningful share
   cannot be reviewed, say so at the top and in the Short version, so the
   reader knows the verdict covers part of the PR.
7. **Never let the output caps drop a still-open prior-round finding.** The
   ≤5 question / ≤7 recommendation caps in Actionable Output bound *new* items.
   A finding a previous round raised and this round has not resolved is carried
   regardless of the caps; if that pushes the list over, the caps yield.

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

### Coverage ledger — mandatory, immediately after the header

Before the scope map, before the graph section, before anything else, emit a
coverage ledger classifying **every changed file** as one of:

- **reviewed** — opened and read in the scope it belongs to
- **targeted-read** — specific hunks or symbols read, not the whole file
- **not-opened** — with a stated reason

End it with the totals and the share of changed lines actually read:

    **Coverage:** 10/64 files reviewed, 18 targeted-read, 36 not-opened — 17.3% of changed lines read

**Keep it one line per changed file up to ~60 files** — that covers ~85% of
PRs here at a median cost of 13 lines. Above that, group rows by directory with
per-directory {reviewed / targeted-read / not-opened} counts, which runs about
12% of the flat size, and enumerate individual files only where a not-opened
file carries runtime risk. The totals line is mandatory at every size — it is
the number a reader prices the review by.

**This goes at the top, not the bottom.** A review that buries its coverage
list reads as complete regardless of what the list says; at the top, a 17%
review is self-evidently a 17% review and the reader can price everything
below it. Placement is the whole point of this section — an accurate ledger in
the wrong position is what let a 17% review pass as finished.

Key conventions:

- H1 = PR title with number
- H2 = coverage ledger + scope map + per-scope sections + overall verdict
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
or any other section in the comment draft. Append a signature naming the agent
that **actually ran this review** and the account it runs on behalf of —
`<driver> on behalf of <repo owner>`, e.g. `Codex on behalf of Sasha` when
Codex ran it. Do not copy that example verbatim when a different driver ran the
review: the signature is an attribution line on a comment posted to GitHub, and
hardcoding one agent's name makes every other reviewer sign as that agent. If
the driver is genuinely unknown, use `Automated review on behalf of <owner>`.
Write it to `${REVIEW_DIR}/<short-sha>-comment.md`.
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
REVIEW_DIR="${DEEPREVIEW_REVIEW_DIR:-$HOME/reviews/${REPO_NAME}}/PR-<N>"
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
- Not a replacement for running the code. Suggest tests, don't simulate them —
  never assert what a test *would* do. Running an existing suite, including
  against a deliberately mutated source, and reporting what it actually did is
  verification and is explicitly in scope (see the contract pass, axis 7).
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
