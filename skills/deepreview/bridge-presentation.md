# Bridge Presentation Spec

How the bridge UI can enhance `/review` output. This is a specification
for bridge-side implementation — not part of the skill prompt itself.

The skill produces structured markdown (see output-format.md). Bridge
renders it through the existing pipeline. Most things work already.
This doc describes what's free, what needs minor work, and what's future.

---

## Already works (no changes needed)

### Diff syntax highlighting

`CodeBlock.tsx` registers `"diff"` as a Shiki language. Fenced
` ```diff ` blocks get full syntax coloring through the existing
`MarkdownView → CodeBlock → Shiki` pipeline.

### Clickable file paths

`MarkdownView.tsx` detects inline code matching `LOCAL_PATH_RE`
(absolute or project-relative paths with optional `:line` suffix).
Renders as `FilePathLink` — click opens `FilePreview` modal.
Review output uses `` `path/to/file.ts:42` `` format, which matches.

### Section tree parsing

`markdown-parser.ts` splits markdown by headings into a
`ContentSection` tree. The review output's H1/H2/H3 hierarchy
aligns with this parser. Belt items with `kind: "section"` are
created via `withLazyChildren()` — drill-in reveals subsections.

### Voice narration

`useThreadNarration.ts` narrates completed assistant responses
via the voice operator session. When the review finishes, the
voice operator receives the full output and narrates a summary.
This works out of the box with no changes.

---

## Enhancement 1: Challenger blockquote styling

**File:** `MarkdownView.tsx`
**Effort:** Small (CSS-only)

Detect blockquotes whose first text node starts with `**Challenger:**`.
Apply a distinct visual treatment to separate adversarial dialog from
reviewer analysis.

```tsx
// In the custom blockquote component:
const isChallenger = typeof children === "string"
  ? children.startsWith("**Challenger:**")
  : /* check first child text node */;

return (
  <blockquote className={cn(
    "border-l-2 pl-3 my-2",
    isChallenger
      ? "border-l-amber-400 bg-amber-500/5"
      : "border-l-border"
  )}>
    {children}
  </blockquote>
);
```

The reviewer's text remains unstyled (default paragraph). The visual
contrast makes the back-and-forth scannable at a glance.

---

## Enhancement 2: Scope section collapsibility

**Files:** `BeltItemRow.tsx` or new component
**Effort:** Medium
**Model:** `expandedDigestIds` pattern in `BeltRenderer.tsx`

H2 scope sections (## Scope N: ...) could default to collapsed,
showing only the verdict line from each lens. Click expands the
full analysis and dialog.

Implementation approach:

1. The `markdown-parser.ts` section tree already produces the H2/H3
   hierarchy
2. Add a `collapsedScopeIds` state set (similar to `expandedDigestIds`)
3. For sections matching `## Scope \d+:`, render collapsed by default
4. Show: scope name + verdict markers from each H3 child
5. Click toggles expansion

The verdict line needs to be extractable from the section content.
The output format places it as the last line of each H3:
`**Verdict:** {marker} {summary}`. A simple regex extraction works.

---

## Enhancement 3: Severity badge rendering

**File:** `MarkdownView.tsx`
**Effort:** Small (cosmetic)
**Priority:** Low

The emoji severity markers (🔴🟡🟢⚪) render natively in both
terminal and browser. Bridge could optionally replace them with
styled `<span>` badges for a more polished look.

Detection: regex match on `🔴|🟡|🟢|⚪` followed by `**Critical**`
etc. Replace with colored chip component.

Not needed for v1 — emoji is clear and works everywhere.

---

## Enhancement 4: Review-aware narration

**File:** `useThreadNarration.ts` or new `useReviewNarration.ts`
**Effort:** Medium-Large
**Priority:** v2

### v1 (works today)

Voice operator narrates the full review after completion.
The operator's system prompt already handles summarizing long
responses into spoken highlights.

### v2 (streaming segment narration)

When voice is on during a review, narrate per-scope verdicts
as they stream:

1. Parse streaming `assistant_text` deltas for H2 heading boundaries
2. When a scope section completes (next H2 starts or response ends),
   extract the verdict lines
3. Send verdict text to voice operator for narration
4. Operator speaks: "Scope 1, auth middleware: caution on the dev
   review — missing input validation on the new endpoint."

This requires delta buffering and heading boundary detection in the
narration hook. The existing `useThreadNarration.ts` debounces at
2 seconds — review narration would need section-boundary awareness
instead.

---

## Enhancement 5: Review session type indicator

**File:** `SessionCard.tsx`, `CompactSessionBelt.tsx`
**Effort:** Small
**Priority:** Low

When a session's first turn invokes the `/review` skill, the pulse
card could show a "Review" badge and display the PR number. Detection:
check if the first turn's tool calls include the `review` skill name.

Not critical — the session name already provides context.
