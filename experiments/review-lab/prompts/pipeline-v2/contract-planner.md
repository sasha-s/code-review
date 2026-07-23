# pipeline-v2 contract planner

You are planning a blind source check for case `{{CASE_ID}}`.

Hard isolation rules:
- Do not read evaluator directories, benchmark goldens, judge outputs, packaged
  benchmark result files, the review-lab learning repository, or the internet.
- Do not use named skills or skill workflows.
- Do not read any path under `/Users/sasha/code-review/skills` or
  `/Users/sasha/.agents/skills`.

Start from exactly this review input README:

`{{INPUT_README}}`

Read the patch, context pack, source excerpts, and symbol pack listed there when
present. Treat `.review-lab-inputs/` as harness data, not product source.

Task: create a persistent contract ledger. Do not write final findings yet.

Planning discipline:
- Split a changed hunk into multiple contract cards when it contains multiple
  semantic operations. Prefer several precise cards over one broad card.
- For API calls, create separate cards for producer argument grammar and consumer
  validation when both sides changed or must agree. Examples of API classes are
  browser APIs, framework render helpers, ORM calls, external tools, file/network
  opens, serializers, and jobs.
- When a known API is used, write the semantic contract for each important
  argument from general API knowledge. If you do not know the API grammar, write
  `API grammar unknown` as a proof dimension instead of skipping it.
- For browser/server security surfaces such as frame headers, CSP, CORS, cookie
  attributes, redirects, origin/referrer checks, and auth/session gates, create a
  card that compares browser-enforced protection with any replacement server-side
  guard. Treat spoofable request fields and nil/malformed fallback behavior as
  proof dimensions.
- For changed templates, script blocks, generated code, or rendered strings,
  create a renderability/syntax contract card even when the template looks
  visually plausible. If the changed grammar contains unusual or unfamiliar
  control-flow delimiters, seed a renderability candidate unless a local syntax
  check already proves it valid.
- For external sinks such as URL/file/network open, shell, SQL, HTML, browser
  APIs, serialization, or trusted render, create a sink-local contract card that
  names the exact sink expression and every direct runtime caller to inspect.
- For string mutation/interpolation, create separate cards for receiver nil/type
  safety and for each interpolated value's escaping/encoding/trust boundary.
- For normalized or canonical values, create separate cards for writer shape,
  storage shape, and lookup/query parameter shape when they can disagree.
- For new or changed CRUD/action handlers, create cards for valid-record and
  missing-record behavior when a lookup result is dereferenced.

Output a stable ledger with these sections:

1. Contract Cards
   - Use stable ids `C-001`, `C-002`, ...
   - For each changed runtime operation, include:
     - changed source ref
     - operation type, expressed from the code, not from a checklist
     - producer/source endpoint
     - consumer/sink/reader endpoint that must agree
     - invariant in one sentence
     - proof dimensions that must be closed: reachability, old-vs-new,
       nil/type, normalization, trust boundary, renderability, auth/routing,
       persistence, state/cache, tests, or other dimensions generated from the
       operation itself
     - suggested reviewer focus: browser/render, remote/import, state/API, or
       multiple

2. Candidate Seeds
   - Use stable ids `K-001`, `K-002`, ...
   - Hypotheses are allowed, but each must point to at least one contract card.
   - Seed at least one candidate for every contract where the changed code has
     no obvious local guard/proof yet. The seed can later be rejected.
   - Include the source fact that would reject the hypothesis.

3. Coverage Map
   - Every changed runtime hunk mapped to one or more contract cards.
   - Non-runtime hunks marked as tests, locale, style, migration-only,
     dependency-only, or docs.

4. Immediate Evidence Needs
   - Source files, symbols, templates, commands, or graph gaps needed to close
     each contract.

Do not use benchmark terms. The value of this stage is coverage and stable ids.
