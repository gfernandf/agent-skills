# SDK Generation

This directory contains tooling and generated SDK clients for `agent-skills`.

## TypeScript / JavaScript Client

### Prerequisites

```bash
npm install -g @openapitools/openapi-generator-cli
# or use Docker:
# docker run --rm -v ${PWD}:/local openapitools/openapi-generator-cli generate ...
```

### Generate

```bash
cd sdk/
./generate_ts.sh
```

### Publish

```bash
cd typescript/
npm publish --access public
```

## Python Client (thin wrapper)

See `sdk/python/` for a lightweight `requests`-based client.

## Adding a New Language

1. Add a generation script: `sdk/generate_<lang>.sh`
2. Add output directory: `sdk/<lang>/`
3. Update this README
