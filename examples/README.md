# Examples

End-to-end examples showing how to use agent-skills.

| Example | Description |
|---------|------------|
| [simple_text_skill.yaml](simple_text_skill.yaml) | Single-step skill that generates text |
| [multi_step_pipeline.yaml](multi_step_pipeline.yaml) | Multi-step pipeline with data flow between steps |
| [router_skill.yaml](router_skill.yaml) | Dynamic routing based on input classification |
| [scatter_gather.yaml](scatter_gather.yaml) | Parallel fan-out with merge |
| [client_usage.py](client_usage.py) | Python client SDK usage (sync, async, streaming) |

## Running Examples

```bash
# Install agent-skills
pip install -e ".[all]"

# Execute a skill
agent-skills run my.custom.skill --input '{"text": "Hello world"}'

# Or use the Python client
python examples/client_usage.py
```
