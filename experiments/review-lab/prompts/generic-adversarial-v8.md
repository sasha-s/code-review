# Generic Adversarial Source Check Prompt v8

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

This v8 is a narrow derivative of v7. It adds operation-triggered checks for
the remaining generic miss families: remote fetch/SSRF semantics, distinct
trusted-string failure modes, legacy CSS/browser contracts, lazy mutable state,
and external command argument grammar.

```text
You are doing a blind adversarial source check for a code change using only this
workspace and the referenced repository checkout. Do not read evaluator or
benchmark-golden files. Do not read the review-lab learning repository. Do not
use the internet.
Do not use any named skills or skill workflows. Do not read any path under
`/Users/sasha/code-review/skills` or `/Users/sasha/.agents/skills`.

Start from `.review-lab-inputs/generic-adversarial/README.md` when present. If
that path is absent and exactly one `.review-lab-inputs/*/README.md` exists,
start from that README instead. Otherwise start from repository `README.md`.
Then read the listed inputs: snapshot.json, patch.diff, reviewer-context.md,
source-excerpts.md when present, and graphify-symbol-pack.md when present.

Task: identify source-backed defects introduced by the changed code. This is
not a checklist exercise. Generate the review plan from the changed code itself.

Protocol:

1. Patch inventory first.
   - List every changed runtime file.
   - For each file, list each changed hunk by behavior, not line count.
   - Mark non-runtime hunks explicitly as tests, locale, style, migration-only,
     dependency-only, or documentation.
   - Do not call a runtime hunk inspected until its changed operations have a
     source-backed contract check or a stated deferral.

2. Micro-contract ledger for each runtime hunk.
   Extract the changed operations from the hunk itself. Use only categories that
   appear in the change:
   - public names and exports: component/function/class names, file names,
     imports, API fields, enum values, route names
   - user-visible or diagnostic text: error keys, log messages, labels,
     migration defaults, config names
   - comparisons and transformations: normalization, case, whitespace,
     separators, parsing, indexing, ordering, slicing, counting, arithmetic
   - external and trust boundaries: request fields, URLs, network fetches,
     files, shell, SQL, HTML/template rendering, postMessage, serialization
   - state and cache operations: writer/reader/delete/invalidate parity,
     uniqueness, one-time semantics, concurrency, migration compatibility
   - framework/language mechanics: template syntax, helper signatures,
     route lifecycle, provider/session state, callback phase
   - tests covering the changed contract: whether tests exercise the bad state
     or only the happy path

3. Mandatory source/guard proof for changed external sinks.
   If the change adds or changes a sink that can leave or enter the process
   boundary, perform this proof before triage:
   - Name the exact sink expression and the value it consumes.
   - List the direct runtime callers you can find for the function containing
     the sink. Include routes, jobs, tasks, templates, callbacks, and command
     entry points when they are runtime paths.
   - For each caller, identify the source of the value and the guard that
     normalizes, restricts, escapes, or authorizes it before the sink.
   - Do not accept a guard from one caller as proof for all callers.
   - Do not accept a host/string check as proof for a URL, origin, HTML, SQL,
     shell, file, or postMessage sink unless it validates the same semantic
     object that the sink consumes.
   - If any real caller reaches the sink without a matching guard, create a
     candidate.

4. Remote-fetch proof when a changed path opens, downloads, or parses a URL.
   Trigger this only when the changed code adds or changes URL fetch/parsing.
   Check:
   - scheme allowlist
   - host allowlist and whether it applies at the fetch sink, not only one caller
   - DNS/private/internal-network reachability and redirects when the library may
     follow redirects
   - timeout, size limit, and partial-download behavior
   - whether input is admin-configured, user-controlled, feed-controlled, task
     input, or migrated data
   If a URL reaches the fetch sink without source-backed protection for the same
   threat model, report a finding or boundary concern. Do not reject SSRF solely
   because the URL starts with `http` or because one caller has a host check.

5. Trusted-string and HTML mutation proof.
   If the change builds, appends, or mutates a string that is later treated as
   HTML, script, SQL, shell, URL, security text, log text, or browser API input:
   - List every dynamic/interpolated value in that string.
   - For each value, prove nil/non-string handling, escaping/encoding,
     normalization, and trust boundary before it enters the string.
   - Verify the receiver object for append/mutation operations.
   - Preserve distinct failure modes: a broad raw-HTML finding does not cover a
     nil receiver crash, and a broad sanitizer bypass does not cover unescaped
     interpolation into generated trusted HTML unless those exact values are
     named.

6. Browser, CSS, and legacy-render path proof.
   Trigger this when the change modifies iframe/postMessage/referer/origin/CSP/
   X-Frame-Options/CORS/cookie/redirect behavior, or when it changes CSS/layout
   mechanics such as flexbox, floats, prefixes, media-specific rules, or theme
   color transforms.
   - State the browser or layout invariant before and after the change.
   - Check full-URL-vs-origin, missing/malformed values, spoofed request headers,
     and explicit security-header weakening for browser security changes.
   - For CSS/layout changes, inspect all rendered paths that use the selector,
     including no-JS/server-rendered/legacy paths when present.
   - For prefixed or legacy browser CSS, verify the actual property names emitted
     by local mixins/helpers rather than assuming modern property names map.
   - Treat explicit weakening or replacement of platform protection as a
     candidate unless equivalent source-backed protection is shown.

7. Lazy state and concurrency proof.
   Trigger this when the change adds or changes lazy caches, loaded-state sets,
   memoized globals, class variables, module variables, shared maps/arrays, or
   state updated from request and background-job paths.
   - Check initialization races, read/write synchronization, duplicate identity
     forms such as string vs symbol, mutation during iteration, and worker/thread
     boundaries.
   - Do not reject a concurrency issue only because another lower-level function
     uses a lock if the new guard state is outside that lock.

8. External command/tool argument proof.
   Trigger this when changed values become command-line arguments or external
   tool flags.
   - Identify the command/tool and changed argument grammar.
   - Check each runtime caller shape separately; animated/static or file-type
     branches may use different tools.
   - Verify whether the tool accepts the changed form, such as percentages,
     `WxH`, paths, flags, or empty values. If local source/tests document the
     grammar, cite them; otherwise report uncertainty as a boundary concern when
     impact is plausible.

9. Mandatory renderability proof.
   If the change adds or changes a rendered template, script block, generated
   code string, or server-rendered HTML/JS boundary:
   - Check that the language/template block structure is syntactically valid.
   - Check that dynamic values are escaped or intentionally trusted at the
     render sink.
   - When cheap and read-only, run a language-native syntax check. If not run,
     quote the exact constructs whose syntax you verified manually.
   - If a new template cannot render under the framework grammar, create a
     candidate even if the surrounding controller/model logic looks correct.

10. Finder and adversarial pass.
   - Inspect the changed location and the other endpoint in actual source.
   - Create a candidate only when both ends disagree, a boundary guard is
     missing, a language/framework contract is violated, or the only coverage is
     a happy-path test that bypasses the changed bad state.
   - For each candidate, try to reject it: introduced by this change, reachable
     entry point, upstream guard/type/framework/db/syntax protection,
     pre-existing behavior, intentional behavior, concrete impact, and source
     evidence that would falsify the claim.

11. Triage policy.
   - Findings: concrete source-backed impact.
   - Source-backed boundary concerns: real invariant/trust/render/compatibility
     weakening with limited or partially proven impact.
   - Rejected: contradicted, unreachable, pre-existing, intended, or unproven.
   - Keep severity proportional.

Output sections:
1. Patch inventory and proof ledger
2. Findings
3. Source-backed boundary concerns
4. Candidates rejected by adversarial check
5. Coverage gaps / residual risks

For each Finding or Source-backed boundary concern include title/severity,
changed source ref, other-end source ref, invariant mismatch, scenario,
adversarial verdict, tests/types, and confidence.
```
