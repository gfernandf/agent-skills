# Custom Service Example

This directory demonstrates creating a complete custom service
(capability → service → binding → skill) that can run locally
without any external API keys.

## Files

| File | Purpose |
|------|---------|
| `capability.yaml` | Capability contract for `text.sentiment.analyze` |
| `service.py` | Pure-Python sentiment analysis implementation |
| `service_descriptor.yaml` | Service descriptor pointing to the module |
| `binding.yaml` | Binding wiring capability ↔ service |
| `skill.yaml` | Skill that invokes the capability |

## Running

```bash
cd <agent-skills-root>
python -m cli.main --skill examples/custom_service/skill.yaml \
    --input '{"text": "I absolutely love this product!"}'
```
