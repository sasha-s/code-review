# Review Output Format

Structured markdown that works in three contexts:

1. **Terminal** — raw markdown, readable as-is
2. **Bridge thread** — rendered with syntax highlighting and clickable paths
3. **Bridge + voice** — narration reads verdict sections

## Document structure

````markdown
# PR #{number}: {title}

**Author:** {author} | **Base:** {base} → **Head:** {head}
**Files changed:** {count} | **+{additions}** | **-{deletions}**

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

## PR Design

**Problem:** {what the PR solves}

**Approach:** {high-level strategy}

**Design rationale:** {why this approach}

**Established patterns:** {whether it follows repo conventions}

---

## Scope 1: {name}

### Dev Review

**Reviewer:**
{Analysis with severity markers and code references}

```diff
- old code
+ new code
```
````

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

## Overall Verdict

| Scope  | Dev         | Security   | Research   |
| ------ | ----------- | ---------- | ---------- |
| {name} | 🟢 Good     | 🟡 Caution | —          |
| {name} | 🔴 Critical | —          | 🟡 Caution |

### Questions for the Author

1. {Questions the review could not resolve from code alone}

### Recommendations

1. {Ordered by severity, most critical first}
2. ...

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
- In the final section, use this order: `Questions for the Author` → `Recommendations` → `Short version`
- `Short version` should sound like a person talking, not a template dump
````
