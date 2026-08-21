# Review Output Format

Structured markdown that works in three contexts:

1. **Terminal.** Raw markdown, readable as-is.
2. **Bridge thread.** Rendered with syntax highlighting and clickable paths.
3. **Bridge and voice.** Narration reads verdict sections.

## Document structure

````markdown
# PR #{number}: {title}

**Author:** {author} | **Base:** {base} → **Head:** {head} @ {short_sha}
**Files changed:** {count} | **+{additions}** | **-{deletions}**
**Review round:** {n}. Prior rounds: r1 {date} @ {sha} (omit this line on round 1)
**Description↔head:** {in sync | provenance finding | unavailable reason}

## Coverage ledger

| File | Read status | Scope | Evidence or not-opened reason |
| --- | --- | --- | --- |
| `{path}` | reviewed | 1 | full file opened |
| `{path}` | targeted-read | 2 | `{symbols or hunks}` |
| `{path}` | not-opened | n/a | `{reason}` |

**Coverage:** {reviewed}/{changed} files reviewed, {targeted} targeted-read, {not_opened} not-opened. {percent}% of changed lines read.

For more than about 60 files, group rows by directory with reviewed,
targeted-read, and not-opened counts. Keep individual rows for not-opened files
that carry runtime risk. The totals line remains mandatory.

---

{PR description summary in 1-2 sentences}

---

## Body claims

| Claim from PR body/title | Head evidence | Status |
| --- | --- | --- |
| {verbatim falsifiable claim} | `{path}:{line}` | verified |
| {verbatim falsifiable claim} | `{reversing commit}` | CONTRADICTED |

Carry this table across rounds. Step 0g owns SHA pins, commit counts, trailers,
and check-run status; keep all other assertion-shaped code and quantity claims.

---

## Scope map

| #   | Scope  | Files       | Lenses        | Nature   | Risk | Flows |
| --- | ------ | ----------- | ------------- | -------- | ---- | ----- |
| 1   | {name} | {file list} | Dev, Security | bugfix   | 0.65 | 42    |
| 2   | {name} | {file list} | Dev, Research | refactor | 0.30 | 8     |

(Omit Risk and Flows columns if code-review-graph is not available.)

Every changed file must appear in exactly one scope or in the Coverage Ledger
as not-opened with a reason. For each non-Dev lens, record either its assignment
or a per-scope decline with the reason.

---

## Graph reconnaissance (if available)

**Risk score:** {overall} | **Changed functions:** {count} | **Affected flows:** {count} | **Impacted files:** {count}

**Top-risk functions:**
| Function | File | Risk | Tests |
|----------|------|------|-------|
| {name} | {path} | {score} | {yes/no} |

**Highest-criticality flows:**
- {flow name} (criticality {score}). {node_count} nodes, {file_count} files.
- ...

(Omit this entire section if code-review-graph is not available.)

---

## PR design and problem fit

**Problem (as evidenced):** {from linked issue/discussion/data; flag if it differs from the PR description}

**Approach:** {high-level strategy}

**Design rationale:** {stated or inferred; mark which}

**Established patterns:** {whether it follows repo conventions}

**If we do nothing:** {consequence, or "unknown; asked below"}

**Simplest credible alternative:** {what a newcomer would build and why the PR's approach is or is not better}

**Problem-fit verdict:** {🟢|🟡|🔴} {one sentence, citing evidence}

---

## Delta since last review (re-review only)

**Resolved:** {ID in one clause, with resolving commit/comment}
**Still open:** {ID with current state and escalation status}
**New since {prior short_sha}:** {what the incremental diff touches}

Unchanged scopes: {list}. These were not re-reviewed.

---

## Scope 1: {name}

### Dev review

**Reviewer:**
{Analysis with severity markers and code references}

```diff
- old code
+ new code
```

> **Challenger:** {Probing question or challenge}

**Reviewer:**
{Response may revise, add, or defend with evidence}

> **Challenger:** {Follow-up or satisfaction}

**Verdict:** 🟡 Caution. {one-sentence summary}

### Security review

{Same dialog pattern}

---

## Scope 2: {name}

{Repeat per scope}

---

## Step back: cross-scope research

{Cross-scope research synthesis from SKILL.md Pass 3}

## Overall verdict

| Scope  | Dev         | Security   | Research   |
| ------ | ----------- | ---------- | ---------- |
| {name} | 🟢 Good     | 🟡 Caution | n/a        |
| {name} | 🔴 Critical | n/a        | 🟡 Caution |

### Questions for the author

1. **Q1** {severity}. {Only what the review could not answer itself after trying (author intent, ops policy, external context); never anything resolvable by grepping/reading the repo; ≤5 items; 1-2 sentences with `file:line`}

### Recommendations

1. **R1** {severity}. {Root-cause-deduped, severity-ordered; ≤7 items; 1-2 sentences with `file:line`}
2. ...

### Findings ledger

| ID | Sev | Scope | Finding | Status |
| R1 | 🔴 | 2 | {one line} | open (r1) |
| Q1 | 🟡 | 1 | {one line} | resolved (r2: author comment) |

### Short version

{2-4 short sentences in plain, human voice explaining what the PR is doing and why it matters.}

````

## Conventions

### Severity markers

Use inline, not in headings:
- 🔴 **Critical.** Must fix before merge.
- 🟡 **Caution.** Should fix or explicitly acknowledge.
- 🟢 **Good.** Positive observation.
- ⚪ **Neutral.** Informational, no action needed.

### Code references

- Inline file paths: `` `src/auth/middleware.ts:42` ``
- Diff blocks: ` ```diff ` fenced code blocks
- Quote PR diff hunks directly when referencing specific changes

### Dialog formatting

- **Reviewer** text: plain paragraphs under `**Reviewer:**` bold label
- **Challenger** questions: blockquotes with `> **Challenger:**` prefix
- Each round flows naturally. No round numbering is needed.
- Keep each reviewer response focused (2-5 findings per lens)
- Keep each challenger probe focused (2-3 questions per round)

### Scope sections

- One H2 per scope, titled `## Scope N: {name}`
- One H3 per lens within the scope
- Dialog rounds stay within the H3. Do not add deeper heading levels.
- In the final section, use this order: `Questions for the author` → `Recommendations` → `Findings ledger` → `Short version`
- `Short version` should sound like a person talking, not a template dump

### Plain language

The final sections (Questions, Recommendations, Short version) may be read
by people who never saw the rest of the review. For those sections:

- Complete sentences only. Do not use fragments, arrow chains, or telegraphic
  compression
- No shorthand or labels invented during the review; say what is meant in
  place
- Unfamiliar identifiers get their role on first mention:
  "`probeMintDrift` (the mint health check)"
- Every 🔴/🟡 states its concrete consequence, including what breaks and for whom

### Unslop gate

- Load and apply the global `unslop` skill to the full review and GitHub draft.
- Keep colored severity markers because they carry status; remove decorative emoji.
- Use sentence case headings and sentences instead of prose dash separators.
- Run `scripts/check_review_unslop.py` against both files. Any finding blocks
  completion and posting until the prose is repaired.
- A clean checker result covers objective patterns only. The full editorial
  pass remains mandatory.

### Finding evidence contract

- Every 🔴/🟡 recommendation or ledger row names the changed source ref, the
  branch/input shape that triggers it, the immediate source-level outcome, and
  the downstream consequence
- A Findings ledger row that is not posted as a Recommendation must say why:
  `merged into R#`, `rejected: {source fact}`, `unresolved gap: {missing
  proof}`, or `low-value/non-runtime`
- A rejection source fact only applies to the exact branch and consequence it
  proves. Sibling branches or sibling consequences need their own disposition

### Actionable items

- Questions and Recommendations are built per the Actionable Output rules in
  SKILL.md: clustered by root cause, capped (≤5 Q / ≤7 R), stable IDs across
  review rounds, question-vs-recommendation never overlapping, written as
  self-contained plain sentences
- The Findings ledger is cumulative across rounds. Never delete a row; only
  update its Status
- A ready-to-post GitHub comment containing only Short version, Questions, and
  Recommendations is signed `<driver> on behalf of <repo owner>`, using the
  agent that actually ran the review. If the driver is unknown, use `Automated
  review on behalf of <repo owner>`. Write it to
  `~/reviews/<repo>/PR-<N>/<short-sha>-comment.md`
````
