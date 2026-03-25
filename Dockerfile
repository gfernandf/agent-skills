FROM python:3.13-slim AS base

WORKDIR /app

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

RUN pip install --no-cache-dir .

EXPOSE 8080

ENV AGENT_SKILLS_HOST=0.0.0.0
ENV AGENT_SKILLS_PORT=8080

ENTRYPOINT ["agent-skills"]
CMD ["serve"]
