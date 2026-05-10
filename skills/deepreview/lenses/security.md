# Security Lens

Review code for vulnerabilities, attack surface, and data exposure risk.

## Attack surface

- Does this change introduce new inputs? (HTTP endpoints, CLI args,
  environment variables, file reads, deserialization, WebSocket messages)
- Are new inputs validated, sanitized, and bounded?
- Are there new parsing paths that could be exploited?
- Does input validation happen at the system boundary, not deep inside?

## Injection vectors

- SQL injection: parameterized queries vs string interpolation?
- Command injection: shell exec with user-controlled strings?
- Path traversal: file operations with user-controlled paths?
- XSS: user content rendered without sanitization?
- Template injection: user input in template strings?

## Blast radius

- If this code fails or is exploited, what is the worst case?
- Can damage be contained? (timeouts, rate limits, resource caps)
- Does failure expose internal state or stack traces?
- Are there circuit breakers or fallbacks?

## Data exposure

- Does this change handle secrets, tokens, PII, or credentials?
- Are they logged, serialized, or included in error messages?
- Are they stored securely? (not plaintext, not in URLs, not in
  query strings, not in client-accessible storage)
- Are they transmitted over secure channels?
- Do error responses leak sensitive information?

## Authentication and authorization

- Does this bypass or weaken any auth checks?
- Are new endpoints/routes properly gated?
- Is there RBAC/permission checking for new operations?
- Are session tokens handled securely?
- Is there CSRF protection where needed?

## Dependency risk

- Are new dependencies introduced? What is their maintenance status?
- Are existing dependencies used in new, potentially unsafe ways?
- Are dependency versions pinned?
- Are there known CVEs in added or updated packages?

## Investigation method

- Trace data flow from input to output — follow user-controlled data
- Check for hardcoded secrets or credentials (grep for patterns)
- Verify TLS, CORS, CSP headers on new endpoints
- Look at error handlers — what do they expose?
- Check if tests exercise auth/authz boundaries

## Severity guide

- 🔴 **Critical**: Exploitable vulnerability or data exposure in production
- 🟡 **Caution**: Potential vulnerability requiring specific conditions
- 🟢 **Good**: Security-positive changes (hardening, validation, least privilege)
- ⚪ **Neutral**: Low-risk observation
