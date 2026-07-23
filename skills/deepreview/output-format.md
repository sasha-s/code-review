# Review Output Format

Structured markdown that works in three contexts:

1. **Terminal** — raw markdown, readable as-is
2. **Bridge thread** — rendered with syntax highlighting and clickable paths
3. **Bridge + voice** — narration reads verdict sections

## Document structure

````markdown
# PR #{number}: {title}

**Author:** {author} | **Base:** {base} → **Head:** {head} @ {short_sha}
**Files changed:** {count} | **+{additions}** | **-{deletions}**
**Review round:** {n} — prior rounds: r1 {date} @ {sha} (omit this line on round 1)

{PR description summary — 1-2 sentences}

---

## Scope Map

| #   | Scope  | Files       | Lenses        | Nature   | Risk | Flows |
| --- | ------ | ----------- | ------------- | -------- | ---- | ----- |
| 1   | {name} | {file list} | Dev, Security | bugfix   | 0.65 | 42    |
| 2   | {name} | {file list} | Dev, Research | refactor | 0.30 | 8     |

(Omit Risk and Flows columns if code-review-graph is not available.)

---

## Graph Reconnaissance (if available)

**Risk score:** {overall} | **Changed functions:** {count} | **Affected flows:** {count} | **Impacted files:** {count}

**Top-risk functions:**
| Function | File | Risk | Tests |
|----------|------|------|-------|
| {name} | {path} | {score} | {yes/no} |

**Highest-criticality flows:**
- {flow name} (criticality {score}) — {node_count} nodes, {file_count} files
- ...

(Omit this entire section if code-review-graph is not available.)

---

## PR Design & Problem Fit

**Problem (as evidenced):** {from linked issue/discussion/data — flag if it differs from the PR description}

**Approach:** {high-level strategy}

**Design rationale:** {stated or inferred — mark which}

**Established patterns:** {whether it follows repo conventions}

**If we do nothing:** {consequence, or "unknown — asked below"}

**Simplest credible alternative:** {what a newcomer would build, and why the PR's approach is or isn't better}

**Problem-fit verdict:** {🟢|🟡|🔴} {one sentence, citing evidence}

---

## Delta Since Last Review (re-review only)

**Resolved:** {ID — one clause — resolving commit/comment}
**Still open:** {ID — current state, escalated or not}
**New since {prior short_sha}:** {what the incremental diff touches}

Unchanged scopes: {list} — not re-reviewed.

---

## Scope 1: {name}

### Dev Review

**Reviewer:**
{Analysis with severity markers and code references}

```diff
- old code
+ new code
```

> **Challenger:** {Probing question or challenge}

**Reviewer:**
{Response — may revise, add, or defend with evidence}

> **Challenger:** {Follow-up or satisfaction}

**Verdict:** 🟡 Caution — {one-sentence summary}

### Security Review

{Same dialog pattern}

---

## Scope 2: {name}

{Repeat per scope}

---

## Step Back: Cross-Scope Research

{Cross-scope research synthesis from SKILL.md Pass 3}

## Overall Verdict

| Scope  | Dev         | Security   | Research   |
| ------ | ----------- | ---------- | ---------- |
| {name} | 🟢 Good     | 🟡 Caution | —          |
| {name} | 🔴 Critical | —          | 🟡 Caution |

### Questions for the Author

1. **Q1** {severity} — {only what the review could not answer itself after trying (author intent, ops policy, external context); never anything resolvable by grepping/reading the repo; ≤5 items; 1-2 sentences with `file:line`}

### Recommendations

1. **R1** {severity} — {root-cause-deduped, severity-ordered; ≤7 items; 1-2 sentences with `file:line`}
2. ...

### Findings Ledger

| ID | Sev | Scope | Finding | Status |
| R1 | 🔴 | 2 | {one line} | open (r1) |
| Q1 | 🟡 | 1 | {one line} | resolved (r2: author comment) |

### Short version

{2-4 short sentences in plain, human voice explaining what the PR is doing and why it matters.}

````

## Conventions

### Severity markers

Use inline, not in headings:
- 🔴 **Critical** — must fix before merge
- 🟡 **Caution** — should fix or explicitly acknowledge
- 🟢 **Good** — positive observation
- ⚪ **Neutral** — informational, no action needed

### Code references

- Inline file paths: `` `src/auth/middleware.ts:42` ``
- Diff blocks: ` ```diff ` fenced code blocks
- Quote PR diff hunks directly when referencing specific changes

### Dialog formatting

- **Reviewer** text: plain paragraphs under `**Reviewer:**` bold label
- **Challenger** questions: blockquotes with `> **Challenger:**` prefix
- Each round flows naturally — no round numbering needed
- Keep each reviewer response focused (2-5 findings per lens)
- Keep each challenger probe focused (2-3 questions per round)

### Scope sections

- One H2 per scope, titled `## Scope N: {name}`
- One H3 per lens within the scope
- Dialog rounds within the H3 — no deeper heading nesting
- In the final section, use this order: `Questions for the Author` → `Recommendations` → `Findings Ledger` → `Short version`
- `Short version` should sound like a person talking, not a template dump

### Plain language

The final sections (Questions, Recommendations, Short version) may be read
by people who never saw the rest of the review. For those sections:

- Complete sentences only — no fragments, no arrow chains, no telegraphic
  compression
- No shorthand or labels invented during the review; say what is meant in
  place
- Unfamiliar identifiers get their role on first mention:
  "`probeMintDrift` (the mint health check)"
- Every 🔴/🟡 states its concrete consequence — what breaks, for whom

### Finding evidence contract

- Every 🔴/🟡 recommendation or ledger row names the changed source ref, the
  branch/input shape that triggers it, the immediate source-level outcome, and
  the downstream consequence
- A Finding Ledger row that is not posted as a Recommendation must say why:
  `merged into R#`, `rejected: {source fact}`, `unresolved gap: {missing
  proof}`, or `low-value/non-runtime`
- A rejection source fact only applies to the exact branch and consequence it
  proves. Sibling branches or sibling consequences need their own disposition

### Actionable items

- Questions and Recommendations are built per the Actionable Output rules in
  SKILL.md: clustered by root cause, capped (≤5 Q / ≤7 R), stable IDs across
  review rounds, question-vs-recommendation never overlapping, written as
  self-contained plain sentences
- The Findings Ledger is cumulative across rounds — never delete a row, only
  update its Status
- A ready-to-post GitHub comment containing only Short version, Questions, and
  Recommendations, signed `Codex on behalf of Sasha`, is written to
  `~/reviews/<repo>/PR-<N>/<short-sha>-comment.md`
````
