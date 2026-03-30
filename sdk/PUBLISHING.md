# SDK Publishing Guide

## TypeScript SDK (@agent-skills/client)

### Generate from OpenAPI spec
```bash
cd sdk/
bash generate_ts.sh
```

### Build & Publish
```bash
cd sdk/typescript/
npm install
npm run build
npm publish --access public
```

### Usage
```typescript
import { AgentSkillsClient } from '@agent-skills/client';

const client = new AgentSkillsClient({
  baseUrl: 'http://localhost:8080',
  apiKey: 'your-api-key',
});

// Execute a skill
const result = await client.executeSkill('text.content.summarize', {
  inputs: { text: 'Long document text...' },
});

// Discover skills by intent
const skills = await client.discover('summarize a document');
```

## Go SDK (github.com/gfernandf/agent-skills/sdk/go)

### Generate from OpenAPI spec
```bash
cd sdk/
bash generate_go.sh
```

### Usage
```go
import "github.com/gfernandf/agent-skills/sdk/go"

client := agentskills.NewClient("http://localhost:8080", "your-api-key")
result, err := client.ExecuteSkill("text.content.summarize", map[string]any{
    "text": "Long document text...",
})
```

## Python SDK

Already available via `pip install orca-agent-skills`:

```python
from sdk.python.client import AgentSkillsClient

client = AgentSkillsClient(base_url="http://localhost:8080", api_key="your-key")
result = client.execute_skill("text.content.summarize", inputs={"text": "..."})
```

## CI/CD Integration

Add to your GitHub Actions workflow:
```yaml
- name: Generate & Publish TypeScript SDK
  run: |
    cd sdk/
    bash generate_ts.sh
    cd typescript/
    npm publish --access public
  env:
    NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```
