# Generic Adversarial Source Check Prompt v6

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

This v6 keeps the generic v5 protocol and tightens the proof obligations that
v5 still let the reviewer hand-wave: repo-wide caller evidence for changed
external sinks, per-interpolation guard evidence for generated trusted strings,
and explicit browser/security-header boundary proof.

```text
You are doing a blind adversarial source check for a code change using only this
workspace and the referenced repository checkout. Do not read evaluator or
benchmark-golden files. Do not read the review-lab learning repository. Do not
use the internet.
Do not use any named skills or skill workflows. Do not read any path under
`/Users/sasha/code-review/skills` or `/Users/sasha/.agents/skills`.

Start from .review-lab-inputs/generic-adversarial/README.md when present,
otherwise start from README.md. Then read the listed inputs: snapshot.json,
patch.diff, reviewer-context.md, source-excerpts.md when present, and
graphify-symbol-pack.md when present.

Task: identify source-backed defects introduced by the changed code. Generate
the review plan from the changed code itself. Do not use a memorized concern
list. Do not stop after one strong finding.

Protocol:

1. Build a patch inventory and hunk ledger.
   - List every changed runtime file and each changed runtime hunk by behavior.
   - Mark tests, locale, style, migrations, dependencies, and docs separately.
   - For each runtime hunk, extract only the changed operations that appear in
     that hunk: names/exports, text/config, comparisons/transforms, external
     boundaries, state/cache writes, framework/language mechanics, and tests.
   - Each runtime hunk must end with inspected, rejected, deferred with reason,
     or candidate created.

2. External-sink source/guard proof with caller evidence.
   For any changed operation that performs network/file/shell/SQL/HTML/template
   rendering/postMessage/serialization/auth/session/header behavior:
   - Name the exact sink expression and consumed value.
   - Run or report a repo search for the containing function/method/class name
     and list the runtime callers found. Include routes, jobs, tasks, templates,
     callbacks, and command entry points when they are runtime paths.
   - For each caller, name the source of the consumed value and the guard that
     validates the same semantic object before the sink.
   - Do not let a guard on one caller prove another caller.
   - Do not let a host/string/prefix check prove URL, origin, HTML, SQL, shell,
     file, or postMessage safety unless it validates the actual object consumed.
   - If a runtime caller is unguarded or caller discovery is incomplete, create
     a candidate or a coverage gap. Do not silently mark it inspected.

3. Trusted-string interpolation proof.
   For any new or changed string that is sent to HTML, a template, SQL, shell, a
   URL, a log/security decision, or a browser API:
   - List each interpolated/dynamic value in the string.
   - For each value, prove type/presence, escaping/encoding, normalization, and
     trust boundary.
   - If the target is trusted HTML or cooked/rendered content, nil/non-string
     handling and escaping must be proven for every interpolated value.
   - If proof is missing, create a candidate or boundary concern.

4. Browser and security-header boundary proof.
   For changed iframe, postMessage, referer/origin, CSP, X-Frame-Options, cookie,
   redirect, CORS, or auth/session behavior:
   - State the browser/security invariant before and after the change.
   - Check missing, malformed, spoofed, cross-origin, and full-URL-vs-origin
     states when the changed code reads referer/origin/URL-like values.
   - Treat explicit weakening or replacement of a platform security header as a
     candidate unless an equivalent source-backed protection is shown for the
     same browser threat model.

5. Renderability proof.
   For changed rendered templates, script blocks, generated code strings, and
   server-rendered HTML/JS:
   - Check framework/language syntax and block structure.
   - When cheap and read-only, run a syntax/render check. If not run, quote the
     exact constructs manually verified.
   - A template that cannot render is a candidate even when the model/controller
     logic is otherwise correct.

6. Finder and adversarial pass.
   - Inspect the changed source and the other endpoint in actual source.
   - Create candidates only for source-backed disagreement, missing guard,
     language/framework violation, untested bad state, or real boundary
     weakening.
   - For each candidate, try to reject it: introduced by this change, reachable
     entry point, upstream guard/type/framework/db/syntax protection, preexisting
     behavior, intentional behavior, concrete impact, and source evidence that
     would falsify the claim.

7. Triage policy.
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
