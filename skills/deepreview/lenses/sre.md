# SRE Lens

Review code for operational safety, observability, and production resilience.
Applied broadly to any code running in production — not just infra changes.
Be proactive: suggest telemetry, logging, and monitoring improvements even
when no bugs exist. The goal is to make the system more debuggable and
operable, not just correct.

## Deployability

- Can this change be deployed independently, or does it require coordination?
- Is it backward-compatible with the previous version running in parallel?
- Does it need a feature flag, gradual rollout, or migration step?
- Can it be rolled back safely if something goes wrong?
- Database migrations: are they additive-only? Do they lock tables?

## Observability (proactive)

- Does this change break or degrade existing logging, metrics, or tracing?
- Can you debug a production failure with the information this code emits?
- Are new code paths instrumented? (errors logged, metrics emitted)
- Are log messages structured and actionable, not just "error occurred"?
- Are there new failure modes that would be invisible without monitoring?
- **Suggest** telemetry that should be added: timing for slow paths,
  counters for key operations, error rate tracking, queue depth metrics
- Would structured logging help here? (JSON with correlation IDs vs printf)

## Resource pressure

- Does this add unbounded queries, loops, or allocations?
- Are there missing timeouts on network calls, DB queries, or external APIs?
- Connection pool exhaustion: are connections released on all code paths?
- Does this create retry storms under failure? (missing backoff, jitter)
- Memory: does this buffer unbounded data in memory?

## Failure modes

- What happens when the external dependency is down?
- What happens under 10x normal load?
- Does this create a new on-call page-worthy failure mode?
- Are there circuit breakers or graceful degradation paths?
- Does partial failure leave the system in an inconsistent state?

## Cron and background jobs

- Does this change cron timing, frequency, or concurrency?
- Can the job safely overlap with itself? (idempotency, locking)
- What happens if the job takes longer than its interval?
- Are there orphaned resources if the job crashes mid-execution?

## Data safety

- Does this change write paths for persistent data?
- Could a bug here corrupt data silently (no validation, no checksums)?
- Is there an audit trail for mutations?
- Does this respect rate limits and quotas on external services?

## Investigation method

- Check for missing timeouts on `fetch`, DB queries, RPC calls
- Look for retry logic without backoff/jitter
- Verify error handling includes enough context for debugging
- Check cron/scheduler changes for overlap and idempotency
- Look at migration files for table locks and backward compatibility
- Search for `console.log` that should be structured logging

## Severity guide

- 🔴 **Critical**: Will cause outage, data loss, or unrecoverable state in production
- 🟡 **Caution**: Creates operational risk under specific conditions (load, timing, failure)
- 🟢 **Good**: Improves operational safety (better logging, circuit breakers, graceful degradation)
- ⚪ **Neutral**: Observational, no operational risk
