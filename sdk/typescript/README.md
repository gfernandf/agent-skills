# @agent-skills/client

TypeScript/JavaScript client SDK for the **agent-skills** runtime API.

## Installation

```bash
npm install @agent-skills/client
```

## Quick Start

```typescript
import { AgentSkillsClient } from '@agent-skills/client';

const client = new AgentSkillsClient({
  baseUrl: 'http://localhost:8080',
  apiKey: 'your-api-key', // optional
});

// Execute a skill
const result = await client.executeSkill('text.content.summarize', {
  text: 'Long article to summarize...',
  max_length: 200,
});
console.log(result.outputs.summary);

// Discover skills
const skills = await client.discoverSkills('summarize a document');

// Execute a capability directly
const capResult = await client.executeCapability('text.content.generate', {
  prompt: 'Hello world',
});

// Async execution with polling
const run = await client.executeSkillAsync('text.content.summarize', {
  text: 'Very long document...',
});
const completed = await client.waitForRun(run.run_id, { timeoutMs: 30000 });

// SSE streaming
const stream = client.executeSkillStream('text.content.summarize', {
  text: 'Another document...',
});
for await (const event of stream) {
  console.log(event.type, event.data);
}
```

## API Reference

### `AgentSkillsClient`

| Method | Description |
|--------|-------------|
| `health()` | Basic health check |
| `listSkills(options?)` | List skills with pagination and filters |
| `describeSkill(skillId)` | Describe a skill's contract |
| `executeSkill(skillId, inputs, options?)` | Execute a skill synchronously |
| `executeSkillAsync(skillId, inputs)` | Execute asynchronously (returns run_id) |
| `executeSkillStream(skillId, inputs)` | Execute with SSE streaming |
| `executeCapability(capId, inputs)` | Execute a capability directly |
| `discoverSkills(intent, options?)` | Discover matching skills for an intent |
| `getRun(runId)` | Get async run status |
| `waitForRun(runId, options?)` | Poll until run completes |

### Configuration

```typescript
interface ClientConfig {
  baseUrl: string;       // Default: 'http://localhost:8080'
  apiKey?: string;       // Authorization: Bearer <apiKey>
  timeout?: number;      // Request timeout in ms (default: 60000)
}
```

## Development

```bash
# Generate from OpenAPI spec
npm run generate

# Build
npm run build
```

## License

Apache-2.0
