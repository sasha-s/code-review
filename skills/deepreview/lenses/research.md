# Research Lens

The actor-critic of the review. The other lenses are the actor — they
review whether the code is correct, safe, and operable. This lens is
the critic — it reviews whether the code should exist at all.

Don't accept the PR's framing at face value. The PR says "here's what I
built." You ask "should you have built it?" The best research review
raises questions the author hasn't asked themselves.

## Core question

**Is this PR solving the right problem, with the right approach?**

Not "is the code correct?" — that's the dev lens. Not "is it safe?" —
that's security. This lens asks whether the entire direction of effort
is justified.

## Problem framing

- What problem does this PR claim to solve?
- Is that the actual problem, or a symptom of a deeper issue?
- Does the PR description explain _why_ this approach, or just _what_ it does?
- Who asked for this? Is the original request the right request?
- What would happen if we did nothing? Is the status quo actually broken?

## The sunk cost test (MANDATORY — must produce an explicit answer)

> "Would someone with no sunk cost in the current approach do this
> differently?"

Do not skip this question. Do not answer "probably not" without evidence.
Actually think about what a newcomer would build given only the requirements
(not the existing code). If the answer is structurally different from the
PR, that's a finding — potentially 🔴 Critical.

When a structural finding is made (the newcomer would do it differently):
- State the structural difference explicitly
- State whether it is addressed, deferred (with a linked ticket), or ignored
- Do not use "out of scope" to close the finding. If it is out of scope,
  the verdict must be `🟡 Caution` or `🔴 Critical` with a clear explanation
  of the deferred risk.

Common sunk-cost signals:
- Adding features to a system whose foundation is wrong
- Building tooling around a workflow that shouldn't exist
- Treating inherited design decisions as constraints rather than choices
- "We already have X, so let's extend X" when Y would be simpler
- Interpolating/transforming data to fit an existing pipeline when the
  data could be consumed directly

## Data flow audit (MANDATORY for any code that processes data)

Trace the full path from input to output. At every transformation step, ask:

1. **What goes in?** (count: N events/records/points)
2. **What comes out?** (count: M steps/iterations/records)
3. **What's the ratio?** If M >> N, why?

Name the ratio explicitly: "14 odds points → 60K window iterations,
ratio 4300:1." A high ratio means the code is manufacturing work that
doesn't exist in the input. Sometimes that's correct (upsampling for
signal processing). Often it means the architecture is solving a
different problem than the data presents.

**The natural loop count for an event-driven system is the number of
events in the input, not a function of wall-clock duration or grid
resolution.**

## Alternative approaches

- What would you build if you started from scratch with no constraints?
- If the answer is radically different from the PR, the PR may be
  optimizing within the wrong constraints.
- Are there simpler approaches that were not considered?
- Is this adding sophistication to an approach that should be replaced?
- Could a different team/system/service own this better?
- Is there an off-the-shelf solution that makes this custom code unnecessary?

## Existing infrastructure check (MANDATORY when PR adds new error-handling or state-tracking)

When a PR introduces new rollback logic, retry logic, state-tracking fields, or
compensating transactions, grep the codebase for how the same class of problem
is solved elsewhere before concluding the approach is necessary.

Ask explicitly: **"Does this pattern already exist in the codebase?"**

Steps:
1. Name the problem class (e.g. "write-after-confirm", "idempotent retry",
   "distributed lock", "optimistic update + rollback")
2. Search for existing implementations of that pattern
3. If one exists: flag the inconsistency — the PR should use it, or justify why not
4. If none exists: note it, but the approach may still be correct

**Difficulty is not a reason to omit this finding.** If the root cause is hard
to fix, say so — but still name it. Knowing "this PR fixes a symptom; the root
cause is X and would require Y" is valuable even if Y is a large refactor.
A reviewer who knows the root cause can make an informed merge decision.
Suppressing the finding because the fix is hard deprives the team of that context.

## Proportionality

- Is the solution proportional to the problem?
- Is this polishing something that should be discarded?
- Does the effort make sense given the alternatives?
- Are we adding statistical rigor to a simulation that shouldn't exist?
  Adding type safety to code that should be deleted? Building abstractions
  for a pattern that should be eliminated?

## Structural foreclosure

- Does this change make it harder to adopt a better approach later?
- Does it cement a temporary solution into a permanent one?
- Are abstractions being added that encode assumptions that may be wrong?
- Will future developers see this and assume the approach is settled?

## The #418 / #419 test

Ask: **"Is there a PR that would make this one obsolete?"**

Concrete patterns to watch for:

- Adding rigor to a process that should be eliminated (PR #418 added
  t-distributions to a simulation running at minutes-per-eval; PR #419
  replaced the substrate entirely, enabling 10K evals in seconds)
- Optimizing performance of code that solves the wrong problem
- Making a wrong answer more precise
- Building tooling around a workflow that should not exist
- Improving the developer experience of a system that should be replaced

If the answer to any of these is "maybe", say so. The reviewer's job is
not to prove it — it's to raise the question.

## Context investigation

Do not review in isolation. Look for signals:

- **PR description and linked issues**: What was the original ask? Does
  the implementation match the intent?
- **git log on affected files**: How often have these files changed?
  High churn suggests the area is unsettled — another sign the approach
  may be wrong.
- **Nearby TODOs/FIXMEs/HACKs**: Known problems the PR doesn't address
- **Related docs or experiments**: Search for design docs, ADRs, or
  alternative implementations in the repo
- **Deleted or reverted code**: Has something similar been tried and
  abandoned before?
- **The actual data**: If the code processes data files, look at them.
  How many records? What's the structure? Does the processing pipeline
  match what the data actually looks like?

## Calibration

This lens flags at the _approach_ level, not the _implementation_ level.
Well-written code that solves the wrong problem is still the wrong code.

The verdict must stand on its own. Do not append:
- "but it's probably fine to merge"
- "out of scope for this PR"
- "deserves a follow-up design review"
- "the PR should proceed"

These escape hatches undermine the lens. If the finding is real, the reviewer
is telling the team: **this decision needs to be made before merging**, not
after. The team can decide to proceed anyway, but they should do so consciously
and with the finding on record.

When a structural issue is real but would require significant rework to fix:
name it explicitly, explain the trade-off being made, and let the verdict
reflect that trade-off honestly. E.g., "🟡 Caution — The gate logic belongs
at the routing layer; keeping it in the page component cements an architecture
that will make future auth changes harder. The fix is correct but leaves a
structural debt that should be tracked." Do not say "out of scope" and let
the verdict read as unconditional approval.
