# API Versioning Changelog

Per-endpoint changelog tracking additions, changes, deprecations, and removals.

---

## v1 — Current

### POST /v1/skills/{id}/execute
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-06-01 | Initial release |
| v1.1    | 2024-09-15 | Added `required_conformance_profile` parameter |
| v1.2    | 2024-11-20 | Added `audit_mode` parameter |
| v1.3    | 2025-01-10 | Added `include_trace` parameter |
| v1.4    | 2025-03-25 | Security headers added to all responses |

### POST /v1/skills/{id}/execute/stream
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-08-01 | SSE streaming endpoint added |
| v1.1    | 2024-09-15 | Added `required_conformance_profile` parameter |
| v1.2    | 2024-11-20 | Added `audit_mode` parameter |
| v1.3    | 2025-03-25 | Added W3C traceparent propagation |

### POST /v1/skills/{id}/execute/async
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-10-01 | Async execution with run tracking |
| v1.1    | 2024-11-20 | Added `audit_mode` parameter |

### GET /v1/skills/{id}/describe
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-06-01 | Initial release |
| v1.1    | 2025-01-10 | Added deprecation/replacement metadata |

### GET /v1/skills/list
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-06-01 | Initial release with domain/role/status/invocation filters |

### POST /v1/skills/discover
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-08-01 | Intent-based skill discovery |
| v1.1    | 2024-12-01 | Added domain/role filters |

### POST /v1/skills/{id}/attach
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-10-15 | Gateway-based skill attachment |
| v1.1    | 2024-11-20 | Added `audit_mode` parameter |

### POST /v1/capabilities/{id}/execute
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-06-01 | Direct capability execution |
| v1.1    | 2024-09-15 | Added `required_conformance_profile` parameter |

### POST /v1/capabilities/{id}/explain
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-08-01 | Binding resolution explanation |

### GET /v1/health
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-06-01 | Basic health check |
| v1.1    | 2025-02-01 | Added `?deep=true` for extended health with subsystem checks |

### GET /v1/metrics
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-08-01 | JSON metrics snapshot |

### GET /v1/metrics/prometheus
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2025-02-01 | Prometheus text exposition format |

### CRUD /v1/webhooks
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-10-15 | POST/GET/DELETE for webhook subscriptions |
| v1.1    | 2025-03-25 | Dead letter queue for failed deliveries |

### GET /v1/runs, GET /v1/runs/{id}
| Version | Date       | Change |
|---------|------------|--------|
| v1.0    | 2024-10-01 | Async run tracking |

---

## Versioning Policy

- **PATCH** (v1.x → v1.x+1): New optional fields, metadata changes, bug fixes.
- **MINOR** (v1.x → v1.x+1): New endpoints, new optional parameters.
- **MAJOR** (v1 → v2): Breaking changes to request/response schemas — announced 90 days in advance with `Sunset` header.

All changes are backward-compatible within the same major version.
