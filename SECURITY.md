# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it **privately**:

1. **Email**: [gfernandf+security@gmail.com](mailto:gfernandf+security@gmail.com)
2. **Subject**: `[SECURITY] agent-skills — <brief description>`
3. Include: affected version, reproduction steps, and potential impact.

**Do NOT open a public GitHub issue for security vulnerabilities.**

We will acknowledge receipt within **48 hours** and aim to provide a fix or mitigation within **7 business days** for critical issues.

## Security Documentation

For details on the runtime's security architecture, see:

- [docs/SECURITY.md](docs/SECURITY.md) — OWASP coverage, SSRF/LFI protections, credential handling
- [docs/AUTH.md](docs/AUTH.md) — Authentication, RBAC, JWT verification
- [docs/ADAPTER_AUTH_POLICY.md](docs/ADAPTER_AUTH_POLICY.md) — Adapter secret management
- [docs/OPENAPI_ERROR_SECURITY_BASELINE.md](docs/OPENAPI_ERROR_SECURITY_BASELINE.md) — API error security baseline

## Scope

This policy covers:
- The `agent-skills` runtime (this repository)
- The `agent-skill-registry` companion repository
- Official bindings and services shipped in this repository

Third-party plugins, community skills, and external service endpoints are outside scope.
