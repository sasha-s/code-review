# Proposed deepreview changes — MISS 1 (description↔head divergence) and MISS 2 (proof quality)

## SHIPPING STATUS (2026-08-19)

| change | status |
| --- | --- |
| 1. Step 0g provenance pre-pass (Signal A) | **SHIPPED** to SKILL.md:328 |
| 2. Re-review rule 7 (body re-checked every round) | **SHIPPED** to SKILL.md:163 |
| 3. `commits` + `lastEditedAt` on the Input step | **SHIPPED** to SKILL.md:30 |
| 4. Signal B — claim-support check | prototype only, NOT shipped |
| 5. Signal C — explicit-contradiction check | prototype only, NOT shipped |
| 6. Proof-constraint / mutation check | deferred; scoped separately as new capability |
| 7. Hazard-claims channel | not built, and not recommended |

Reference snapshot hashes used during development: `a3042131…` (original 863
lines), `175a3891…` (936), and `66b71144…` (962). The duplicate files are not
committed.
Cumulative applied diff: **+143 / -1**, 863 → 1005 lines.
SKILL.md line numbers below are against the ORIGINAL 863-line file.

### PROCESS HAZARD — do not repeat

**The skill changed under a live reviewer mid-run** (1005 -> 1138 lines while
they were writing). Their results stand — they diffed and confirmed rule 7's
selector and Step 0g's threshold were byte-identical across the change — but
two of the gaps they hit had already been fixed concurrently, so their run is
the **pre-edit baseline** for the forced-same-head and empty-graph-index items.
Editing a skill while a reviewer executes it makes results ambiguous by
default; it happened to be recoverable here only because the reviewer checked.
Freeze the skill for the duration of a validation run.

### MEASUREMENT CAVEAT — a low claim count validated cost, not coverage

Rule 7's v1 selector measured at median 2 claims/body and I reported that as if
it validated the rule. It did not: the budget was measured **on the selector**,
so a low count says the selector is cheap, not that the body has few claims.
On a claim-dense 47-line body v1 took 2 of ~8 verifiable claims because it was
keyed on bold and normative keywords, which that author does not use. The v2
selector (assertion-shaped, formatting-independent) measures at **median 9,
p90 17, max 26** — ~4.5x the cost, and the correct price. Whenever a selector's
own output is the cost metric, state which question the number answers.

### VALIDATION STATUS — read before trusting the acceptance tables

Only **one** live run of Step 0g has ever happened (PR #1214, pre-fix). It
exercised neither of the two things changed since:

| behaviour | validated by a live reviewer run? |
| --- | --- |
| suppressions (head-anchor, transition line) | **yes** — mechanical, not prose-dependent |
| `createdAt` fallback | **yes** — a live reviewer took the never-edited branch with zero deliberation on PR #1222 |
| firing threshold (pin/count, not commit count) | **yes** — 2 commits reported as precondition, escalation driven by the pin; and it was material, catching a verification claim credited to a SHA that excludes the PR's two highest-risk commits |
| rule 7 body-claims table (v1 selector) | **yes, and it FAILED** — took 2 of ~8 claims; v2 selector is unvalidated |
| author-date fix | **NO** |
| coverage ledger / scope assignment | **NO** |
| mutation control axis | **NO** by the skill, but the technique produced a clean killed/survived split in ~90s on PR #1222 |

Every acceptance result in this file below is from **my own hand-execution of
the spec**, not from the reviewer executing it. That distinction is exactly
what the #1214 run exposed: prototype, corpus calibration, and hand-run dry
test all passed while the shipped prose said something different. Treat the
tables as evidence the spec is executable, not as evidence the reviewer
follows it.

### What Signal B needs before it can ship

A portable implementation of the locally evaluated Signal B prototypes is
still needed. The scratch-bound prototypes were intentionally not committed.
The prototype fired on 11/166 multi-round PRs; 3 were verified true,
**1 was verified false (PR-1060)**, and 7 remain unadjudicated.
- Widen the deletion-context suppression. PR-1060's body says "**Deleted** the
  orphaned promo assets: `hero-art.webp` …" and the sentence splitter breaks on
  the bolded prefix, so the absence is flagged even though the body announced
  it. The suppression must cover bolded/list-prefixed deletion sentences.
- Adjudicate the remaining 7 firings before claiming a precision number.
- Cost is ~30 `git grep` invocations per review, which is real but bounded.
It is the only one of the three signals that catches the six divergences we
historically *did* catch (it recovers PR-1000's `ignoreCommand` exactly), so it
is worth finishing.

### What Signal C needs before it can ship

**A `messageBody` field in the ledger's commit cache.** `ledger/cache/gh/PR-*/
commits.json` stores commit *subjects* only — `3ab8c5200`'s `message` is 75
chars with zero newlines against a ~2,400-char real body. Run on subjects,
Signal C loses PR #1223 (its subject carries no contradiction term while its
body says "fails licence condition (2)" and "the floor's buildable set is
EMPTY"); `pr-description-mining` measured their equivalent signal at **0 fires
across 887 PRs** on subject-only input. This is structural to
conventional-commit style and is NOT fixable by widening the vocabulary —
widening is what produced the 20.5% garbage run. One field on the `gh` fetch is
the difference between 13 fires and 0.

---

Line numbers are against SKILL.md at 863 lines.

---

## Change 1 — fetch the one metadata field the check needs (SKILL.md:30)

```diff
 # Fetch PR metadata
-gh pr view <N> --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles,url,state,mergeCommit
+gh pr view <N> --json title,body,author,baseRefName,headRefName,additions,deletions,changedFiles,url,state,mergeCommit,commits
+
+# Body edit time is not exposed by `gh pr view`; it needs one GraphQL call.
+gh api graphql -f query='{repository(owner:"OWNER",name:"REPO"){pullRequest(number:N){
+  lastEditedAt createdAt}}}'
```

Cost: one extra API call, ~0 tokens of reviewer reasoning.

---

## Change 2 — new deterministic pre-pass, inserted at SKILL.md:305 (before "### Store results for later passes")

```markdown
### Step 0g — Description↔head divergence (deterministic, no model reasoning)

The PR body and title are shipped artifacts: the title lands in the merge
commit, and for a docs/spec PR the body's ruling IS the deliverable. Run
these three checks mechanically and carry the output into Pass 1b. They are
string/timestamp comparisons — do not spend reasoning on them.

1. **Provenance freshness.** Compare the body's `lastEditedAt` with each
   commit's date. List every commit that landed after the body was last
   edited. If the body states a commit count or pins a SHA
   ("At `abc1234`:", "Base X, five commits"), compare against the real list.
   **Two structural suppressions are mandatory, and firing without them
   punishes the exact remediation we want:**
   - If the body cites head at all, every older SHA it cites is history, not a
     stale pin — suppress the whole pin check.
   - A SHA cited on the same line as a strictly newer cited SHA is a transition
     ("`A` -> `B`"), not a claim about what the PR describes.
   Both are structural — no dependence on past tense, "originally", or
   blockquote formatting, so they generalize past one PR's phrasing.
   **And every check here requires at least one commit after the body edit.**
   A stale-looking citation in a body edited *since* the last commit is
   history by construction.
2. **Claim support.** For every backticked identifier, path, flag, or metric
   name in the body, check it still exists at head
   (`git ls-tree -r --name-only HEAD`, then `git grep -F`). Report any that
   do not. Suppress tokens the body itself says were deleted, branch names,
   SHA ranges, and commit trailers.
3. **Ruling reversal.** For each commit that landed after the body freeze,
   scan its FULL message (`gh pr view <N> --json commits` returns
   `messageBody`, so no clone is needed) for EXPLICIT contradiction only:
   `no longer`, `does not qualify`, `fails licence/condition`, `falsifies`,
   `supersedes`, `retracts`, `is EMPTY`, `was wrong`, `contradicts`,
   `opposite`. Do NOT match `instead of` / `rather than` / `replaces` /
   `drop the` — those describe ordinary "I changed X to Y" development and
   are the single largest source of false fires.
   Apply this check only when the body actually states a ruling (contains
   MUST/SHALL/REQUIRED/normative/invariant, or the form "is a X, not a Y").

Emit a fixed block into the review, even when clean:

    **Description↔head:** {in sync | N commits since body edit; body pins `X` (K behind); tokens absent at head: [...]}

If any check fires, Pass 1b must state whether the body's stated deliverable
still describes head, and a divergence becomes a Recommendation in its own
right — not a footnote. **The PR body is never evidence for what the PR does;
it is a claim to be checked against head.**
```

Validated against PR #1223 as a labeled positive-then-negative pair. The
author later fixed the divergence (title now "exact snapshot anchors") and
documented the reversal in the body as an explicit changelog citing both old
SHAs. Post-suppression behaviour:

| #1223 state | head | fires? |
| --- | --- | --- |
| r1 (body pinned `7d197203` = head then) | `7d197203` | no — anchors head |
| r2 | `b9a6eacae` | **yes** |
| r3 (ruling reversed) | `3ab8c5200` | **yes** |
| r4 | `99b1be43f` | **yes** |
| live, author fixed + changelogged | `e1253954` | no — anchors head |

Both endpoints are correct for the same structural reason, and r1's silence
becomes principled rather than incidental.

Recall cost of the suppressions on the corpus: **zero**. Signal A fires on the
same 28/166 PRs before and after, and the per-round replay fires on the same
10 PRs at the same 10 first-fire rounds. Only 7/166 bodies (4.2%) anchor on
head at all, so the suppression is validated mainly by the #1223 pair — the
historical corpus contains few examples of the changelog-remediation pattern
it targets.

Measured on 166 multi-round TheEdge PRs: check 1 fires on 28 (16.9%), check 2
on 11 (6.6%), check 3 on 20 (12.0%). They are largely disjoint (union 48 =
28.9%), so report them as separate lines, not one alarm. **Checks 1 AND 3
together fire on 6 PRs (3.6%) and PR #1223 is one of them** — that
intersection is the escalation threshold.

Calibration that matters (both measured, both cost nothing):
- Running check 3 on commit SUBJECTS instead of full messages **loses #1223**
  — `3ab8c5200`'s subject is "anchor both paginated snapshots exactly and drop
  the client retry", while the explicit contradiction ("fails licence
  condition (2)", "the floor's buildable set is EMPTY") is in the body.
- The wide vocabulary fires on 34 PRs (20.5%) with useless matches; the narrow
  vocabulary above plus the ruling gate cuts that to 20 (12.0%) while keeping
  #1223 with the exactly-right commit and words.

Cost per review: 1 GraphQL call + ~30 `git grep` invocations + ~10 lines of
output. No extra model passes.

---

## Change 3 — re-review rule 7, inserted at SKILL.md:158 (after rule 6)

```markdown
7. **The body and title are re-reviewed every round, even though they are not
   in the delta.** Round 1 already extracts the body's pinned head SHA — the
   r1 template line "its body says ... at head `7d197203`" IS that extraction.
   At r1 the pin matched the real head, so it read as confirmation and nobody
   noticed a live check was being generated. Carry that same extraction into
   every later round and compare it to the current head; at r3 and r4 it would
   have printed a visibly stale SHA. This is a continuation of an existing
   extraction, not new body ingestion. Re-review mode moves the "Problem (as evidenced)" anchor to
   the prior review ledger and the new commit messages, and the body silently
   stops being read. Re-run Step 0g each round against the current head, and
   restate the divergence line in the round header. A body that was accurate
   at round 1 is not thereby accurate at round 3.
   (Observed failure: PR #1223. The body's bolded ruling — snapshot `seq` is a
   replay floor, `getPositionsSnapshot` qualifies — was reversed by
   `3ab8c5200` "anchor both paginated snapshots exactly". Rounds 3 and 4 both
   reviewed that commit, r3 even quoted its message, and neither round
   mentioned the body. Rounds 2, 3 and 4 contain zero references to the PR
   body; only round 1 cites it.)
```

---

## Change 4 — proof-quality obligation (MISS 2), inserted in Pass 2 at SKILL.md:517

SKILL.md today has **zero** occurrences of "mutation", "mutant", or "invert",
and the lens files have none either. repo-intel is used to *locate* proofs
("nearest proof sites"); nothing asks whether a located proof constrains
behavior. Measured: 97.1% of 788 artifacts cite a test/proof file, 4.6% run a
mutation control; 27 of 228 PRs (11.8%) ever ran one.

```markdown
**Proof-constraint check (mandatory when the delta adds or changes a test that
is cited as the proof of a behavior).** Locating the proof is not evaluating
it. For each such proof, pick the single load-bearing expression in the code
under test — the one whose removal changes the behavior the proof claims to
establish — and state what the suite would do if it were removed. Where the
suite is cheap to run, run it with that expression removed and report the
result; where it is not, name the fixture that would have to distinguish the
two and say whether it exists.

A proof that passes with the load-bearing expression removed is a 🟡 finding
in its own right, reported against the proof, not the code.

Budget: one mutation per PR — the single highest-consequence expression. This
is a targeted probe, not a mutation-testing campaign.
(Observed failure: PR #1222. `padStart(CREATED_AT_WIDTH, "0")` is what makes
lexicographic key order equal numeric order; dropping it leaves all 6 tests
green because no fixture distinguishes padded from unpadded. None of the three
review artifacts for that PR mentions padding, and no artifact in the 785-file
corpus mentions `padStart` or `CREATED_AT_WIDTH`.)
```

---

## Change 5 — hazard-claims channel (MISS 2b) — NOT recommended for SKILL.md yet

The move that made PR #1222's proof gap actionable was repo memory ("this repo
has hit a sec-vs-ms unit split before"). The reviewer supplied that; the system
cannot.

`experiments/review-lab/learning-repository/README.md` carries an explicit
"never inject into live reviewer prompts" policy, and the ledger's
`acceptance_rate` is currently unreliable. A hazard channel mined from our own
findings would violate the first and be calibrated on the second. **Do not
build it from the ledger.**

The admissible version derives hazards from the *repository's own fix history*
rather than from our findings — `git log --grep` over revert/hotfix commits
touching the changed files, surfaced as a Pass 0 input alongside repo-intel's
owner/proof hints. That is the same class of evidence Pass 1b step 2 already
authorizes (`git log --oneline -15 -- <changed files>`), just widened and
filtered. It needs its own A/B before it goes near SKILL.md.
