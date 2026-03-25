# ── Stage 1: build ────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY cli/ cli/
COPY customer_facing/ customer_facing/
COPY customization/ customization/
COPY gateway/ gateway/
COPY runtime/ runtime/
COPY services/ services/
COPY skills/ skills/
COPY policies/ policies/
COPY official_mcp_servers/ official_mcp_servers/
COPY official_services/ official_services/
COPY tooling/ tooling/
COPY skills.py ./
COPY bindings/ bindings/

RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: runtime ──────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/gfernandf/agent-skills"
LABEL org.opencontainers.image.title="agent-skills"
LABEL org.opencontainers.image.description="Runtime for executing reusable AI agent skills"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
WORKDIR /app
COPY --from=builder /build/ .

# Create non-root user and writable directories
RUN groupadd -r agentskills && \
    useradd -r -g agentskills -d /app -s /sbin/nologin agentskills && \
    mkdir -p /app/artifacts /app/skills/local && \
    chown -R agentskills:agentskills /app/artifacts /app/skills/local

USER agentskills

EXPOSE 8080

ENV AGENT_SKILLS_HOST=0.0.0.0
ENV AGENT_SKILLS_PORT=8080

ENTRYPOINT ["agent-skills"]
CMD ["serve"]
