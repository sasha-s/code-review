# Source Check Prompt

Use this prompt template for isolated review-lab child Codex runs. It avoids
global skill trigger wording so a child process can test a narrow source-check
capability without loading the host-global `deepreview` skill.

```text
You are doing a blind source check for a code change using only this workspace
and the referenced repository checkout. Do not read evaluator or benchmark-golden
files. Do not use the internet.
Do not use any named skills or skill workflows. Do not read any path under
`/Users/sasha/code-review/skills` or `/Users/sasha/.agents/skills`.

Start from README.md, inputs/snapshot.json, inputs/patch.diff,
inputs/analysis/reviewer-context.md, inputs/analysis/source-excerpts.md, and any
referenced source files needed from the repo.

Task: identify source-backed defects introduced by the changed code. Focus on
changed runtime contracts rather than style. For each changed scope, trace:
- caller intent from code, comments, method names, tests, and surrounding flow
- callee implementation and accepted input/output shapes
- old-vs-new behavior at the caller boundary
- missing/null/empty state and persisted legacy data
- zero/false/empty versus missing semantics for config, rate, count, and feature
  flag values
- writer/reader completeness for new state keys, session values, persisted
  metadata, and optional legacy records
- shared lazy singleton state and check-then-act caches/load trackers, including
  synchronization around the state container and duplicate work under concurrent
  calls
- identifier routing and ownership binding
- cache key construction and invalidation parity: writers and deleters should use
  the same deterministic identity and serialization
- canonical key normalization for membership/load/cache checks, including
  String/Symbol/case/locale-code variants
- write/update/delete side effects, including empty update payloads and
  timestamp/cache freshness semantics
- remote fetch/open/URI trust boundaries: scheme allowlists, host allowlists,
  private/internal network access, redirect behavior, timeouts, and error paths
- browser embedding and postMessage contracts: exact origin parsing/comparison,
  targetOrigin shape, sibling-domain/port/scheme variants, and frame policy
  (`X-Frame-Options`/CSP) enforcement versus referer-based checks
- normalization parity across model callbacks, direct SQL migrations, and lookup
  predicates; if code uses `lower(column)` or strips schemes/paths/ports, verify
  the parameter and migrated legacy values are normalized the same way
- wrapper/helper dispatch paths selected by runtime options; when a changed
  helper builds a shared argument, verify every implementation that can receive
  it, including animated/binary/platform-specific branches
- nil/blank mutation and not-found handling for callbacks and admin CRUD flows:
  mutating helpers like `sub!` need non-nil receivers, and find-by-id update or
  destroy paths need explicit missing-record behavior
- script/CLI/process-control behavior when changed commands are part of the
  runtime workflow, including return-code propagation and direct exit helpers
- test-contract behavior: changed test names, docstrings, setup, timing, and
  assertions should prove the behavior they claim to cover
- template syntax and renderability for changed ERB/HBS/JS templates, including
  block delimiters and compile/render sanity checks
- mechanical stylesheet substitutions: group repeated old/new value patterns and
  inspect outliers where a branch reverses lightness, contrast, spacing, or state
  semantics compared with nearby selectors
- layout migrations from float/inline-block to flex/grid: audit old and new
  formatting contexts, non-JS/noscript or legacy DOM variants, child min-width
  and flex-grow/shrink behavior, and valid vendor-prefixed property names

Important source-check rules:
- Tests are evidence, not proof. If a changed test covers one state/count/order,
  still check adjacent missing, extra, duplicate, and empty variants.
- If changed code calls a write primarily to produce a side effect, do not drop
  the issue just because a downstream reader is elsewhere. Report it when the
  changed code itself establishes the intended side effect and the callee/payload
  makes that side effect a no-op or platform-dependent.
- For each newly added or newly relied-on state value, trace who writes it,
  every path where it may be absent or None, and every later subscript,
  attribute read, comparison, or return-code decision that assumes it exists.
- For zero-like values (`0`, `0.0`, `false`, empty string/list), verify whether
  the source treats them as intentional values or as missing, and compare test
  factories with production validation.
- For cache behavior, trace both key construction and invalidation/deletion
  paths before reporting nondeterminism or stale-cache risk.
- For load trackers and memoized global state, verify that membership checks use
  canonical keys and that both the collection and the load operation are safe
  under concurrent callers.
- For URI, host, or origin checks, do not accept substring matching or one-sided
  normalization as sufficient. Compare parsed origin/host/port values exactly
  against normalized stored values, including mixed-case and legacy migrated data.
- For embed or iframe changes, check both who may frame the page and whether the
  page can successfully message the parent; receiver origin checks and sender
  targetOrigin checks are separate contracts.
- If a finding identifies one issue in a helper, keep checking adjacent nil,
  empty, escaping, and normalization paths in the same helper before finalizing.
- If a helper dispatches to different callees by option, file type, platform, or
  extension, trace the changed argument shape through each callee before
  concluding the contract is safe.
- For stylesheet-only changes, compare repeated substitutions as a batch. A
  single selector using `30%` where the surrounding migration uses `70%`, or
  swapping foreground/background-derived colors, is often the real defect.
- For flex/grid migrations, do not stop at the primary browser path. Check old
  prefixed syntax, no-JS markup, and children that relied on floats, auto widths,
  or text-overflow before becoming flex items.
- For CLI commands, trace the command framework entry point, the command method
  return contract, direct exit helpers, test-launch behavior, production
  hard-exit behavior, and changed tests' exit-code assertions.
- For changed tests, compare the test name/docstring to the actual assertion and
  timing path; report mismatches only when they weaken the behavioral signal.
- If a suspected issue is contradicted by source, reject it explicitly under
  Non-defects checked instead of forcing a defect.
- Prefer behavioral defects with concrete user impact over low-value style nits.

For each defect include:
- title and severity
- exact source refs with line numbers
- caller/callee contract trace
- concrete failing scenario
- whether tests/types would catch it

Output sections:
1. Defects
2. Non-defects checked
3. Residual risks / source gaps
```
