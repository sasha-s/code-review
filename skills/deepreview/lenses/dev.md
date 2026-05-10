# Dev Lens

Review code for correctness, necessity, and quality.

## Correctness

- Does the code do what the PR description claims?
- Off-by-one errors, race conditions, null/undefined dereferences
- Error handling: are failure modes covered? Are errors swallowed silently?
- Type correctness: exhaustive pattern matching, proper narrowing
- Edge cases: empty inputs, boundary values, concurrent access

## Necessity

- Is every changed line necessary for the stated goal?
- Is dead code being added or left behind?
- Could the same result be achieved with less change?
- Are there changes that look auto-generated or cargo-culted?
- AI-specific: watch for hallucinated API usage, over-engineering,
  unnecessary abstractions, and "helpful" additions not in the spec

## Contract violations

- Does this break any API contracts (explicit or implicit)?
- Are callers of modified functions/types updated?
- Are database migrations backward-compatible?
- Do exports match what consumers expect?
- Are default values or optional fields changed in breaking ways?

## Test coverage

- Are changed code paths covered by tests?
- Do existing tests still pass with these changes?
- Are new edge cases tested?
- If tests were modified: do they still test the right thing, or were
  they weakened to pass?

## Style and consistency

- Does new code match the surrounding codebase's patterns?
- Naming conventions followed?
- Is complexity proportional to the problem being solved?
- Are comments accurate and necessary (not restating the code)?

## Investigation method

Do not review the diff in isolation. Use tools to examine context:

- **Read** files outside the diff that import/call modified code
- **Grep** for callers of changed functions or types
- **Glob** for test files covering the changed modules
- **git log** on affected files for history and churn patterns

When the PR adds new mechanisms for a problem (rollback, retry, state tracking,
locking), grep for how the same problem is solved in adjacent code:

- If two code paths handle the same operation differently (one uses the
  established pattern, one rolls its own), flag the inconsistency explicitly.
- The question is not just "does this code work?" but "does this code work
  the same way the rest of the codebase works?"

## Severity guide

- 🔴 **Critical**: Will cause bugs, data loss, or breakage in production
- 🟡 **Caution**: Likely to cause problems but not immediately dangerous
- 🟢 **Good**: Positive observation worth noting
- ⚪ **Neutral**: Stylistic or minor, not actionable
