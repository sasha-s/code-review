# Generic Adversarial Source Check Prompt v7

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

This v7 is a narrow derivative of v5. It keeps the hunk-level ledger plus
external-sink/renderability proofs, adds a focused browser frame/security-header
proof, and tightens trusted-HTML interpolation proof without the heavier v6
caller-evidence language that caused over-rejection.

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

   For each extracted operation, name the other endpoint that must agree with
   it: caller, callee, reader, writer, parser, serializer, renderer, template,
   config, migration, auth predicate, route phase, external sink/source, or test.

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

4. Mandatory trusted-HTML/string interpolation proof.
   If the change builds a string that is later treated as HTML, script, SQL,
   shell, URL, security text, log text, or browser API input:
   - List every dynamic/interpolated value in that string.
   - For each value, prove nil/non-string handling, escaping/encoding,
     normalization, and trust boundary before it enters the string.
   - If the string is appended or mutated before a trusted render sink, verify
     both the receiver object and each interpolated value.
   - Report distinct failure modes separately when they affect different runtime
     states, even if a broader finding also covers the same changed pipeline.

5. Mandatory browser frame/security proof.
   If the change adds or changes iframe, postMessage, referer/origin, CSP,
   X-Frame-Options, CORS, redirect, cookie, or browser auth/session behavior:
   - State the browser security invariant before and after the change.
   - Check full-URL-vs-origin, missing/malformed values, spoofed request headers,
     and explicit security-header weakening.
   - Treat explicit weakening or replacement of a platform security header as a
     candidate unless an equivalent source-backed protection is shown for the
     same browser threat model.

6. Mandatory renderability proof.
   If the change adds or changes a rendered template, script block, generated
   code string, or server-rendered HTML/JS boundary:
   - Check that the language/template block structure is syntactically valid.
   - Check that dynamic values are escaped or intentionally trusted at the
     render sink.
   - When cheap and read-only, run a language-native syntax check. If not run,
     quote the exact constructs whose syntax you verified manually.
   - If a new template cannot render under the framework grammar, create a
     candidate even if the surrounding controller/model logic looks correct.

7. Finder pass.
   - Inspect the changed location and the other endpoint in actual source.
   - Create a candidate only when both ends disagree, a boundary guard is
     missing, a language/framework contract is violated, or the only coverage is
     a happy-path test that bypasses the changed bad state.
   - Prefer correctness, security, data integrity, authorization, runtime
     failure, and externally visible contract defects over style.
   - Do not stop after finding one strong defect. Continue until every runtime
     hunk has a micro-contract status.

8. Adversarial pass.
   For each candidate, try to reject it:
   - Is it actually introduced by this change?
   - Is the bad state reachable from a real runtime entry point?
   - Is there an upstream guard, type constraint, framework contract, database
     constraint, existing normalization, caller-specific guard, or syntax rule
     that prevents it?
   - Does old behavior already have the same issue?
   - Is the behavior intentional or documented?
   - Is the claimed impact concrete, limited, or speculative?
   - What exact source evidence would make the claim false?

9. Triage policy.
   - Put a candidate in Findings only when it has concrete source-backed impact.
   - Put a candidate in Source-backed boundary concerns when the changed code
     breaks or weakens a real invariant, trust boundary, render contract,
     compatibility contract, or user-visible contract, but impact is limited or
     not fully proven.
   - Put a candidate in Rejected only when it is contradicted by source,
     unreachable, pre-existing, intended, or unproven.
   - Do not promote boundary concerns into high-severity findings. Keep severity
     proportional.

10. Final coverage pass.
   - Include the patch inventory, micro-contract ledger, sink proofs, browser
     frame/security proofs, trusted-string proofs, and renderability proofs in
     the final output.
   - List any changed runtime hunks whose contracts you did not inspect.
   - List any source or graph gaps that limit confidence.
   - Do not invent findings to cover gaps.

For each Finding or Source-backed boundary concern include:
- title and severity
- changed source ref with line number
- other-end source ref with line number
- exact invariant mismatch
- concrete scenario or limited-impact scenario
- adversarial verdict: why it was not rejected
- whether tests/types would catch it
- confidence

Output sections:
1. Patch inventory and proof ledger
2. Findings
3. Source-backed boundary concerns
4. Candidates rejected by adversarial check
5. Coverage gaps / residual risks
```
