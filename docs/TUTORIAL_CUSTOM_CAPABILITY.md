# Creating a Custom Capability

End-to-end guide: define a new capability, wire a binding, test it, and optionally promote it to the registry.

---

## 1. Define the capability contract

Create a YAML file in the registry:

```yaml
# agent-skill-registry/capabilities/text.sentiment.analyze.yaml
id: text.sentiment.analyze
version: 1.0.0
description: Analyze the sentiment of a text passage.

inputs:
  text:
    type: string
    required: true
    description: Text to analyze.

outputs:
  sentiment:
    type: string
    required: true
    description: "Detected sentiment: positive, negative, or neutral."
  confidence:
    type: number
    required: false
    description: Confidence score between 0 and 1.

properties:
  deterministic: false
  side_effects: false
  idempotent: true

cognitive_hints:
  role: evaluate
  consumes:
    - Context
  produces:
    sentiment:
      type: Entity
    confidence:
      type: Score

metadata:
  status: experimental
  tags: [text, nlp, sentiment]
  examples:
    - summary: "Positive sentiment"
      inputs:
        text: "I love this product! It's amazing."
      outputs:
        sentiment: positive
        confidence: 0.95
```

### Key fields

| Field | Purpose |
|-------|---------|
| `id` | Dot-separated identifier: `<domain>.<entity>.<verb>` |
| `inputs` / `outputs` | Typed contract — the runtime validates against this |
| `properties` | Execution semantics (deterministic, side_effects, idempotent) |
| `cognitive_hints` | CoALA-aligned metadata for reasoning engines |
| `metadata.status` | Lifecycle: `experimental` → `stable` → `deprecated` |

---

## 2. Create the Python baseline

Every capability needs a deterministic fallback that works without API keys.

```python
# agent-skills/official_services/text_sentiment_analyze.py
"""Baseline implementation for text.sentiment.analyze."""

# Simple keyword-based sentiment (no ML, no API key required)
_POSITIVE = {"love", "great", "amazing", "excellent", "wonderful", "fantastic", "good", "happy", "best"}
_NEGATIVE = {"hate", "terrible", "awful", "horrible", "bad", "worst", "poor", "ugly", "sad"}


def analyze_sentiment(text: str, **kwargs) -> dict:
    """Baseline sentiment analysis using keyword matching."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    total = pos + neg or 1

    if pos > neg:
        sentiment, confidence = "positive", pos / total
    elif neg > pos:
        sentiment, confidence = "negative", neg / total
    else:
        sentiment, confidence = "neutral", 0.5

    return {"sentiment": sentiment, "confidence": round(confidence, 2)}
```

---

## 3. Create the binding

Wire the capability to your baseline (and optionally to an LLM):

```yaml
# agent-skills/bindings/official/text_sentiment_analyze_baseline.yaml
id: pythoncall_text_sentiment_analyze_baseline
capability_id: text.sentiment.analyze
service_id: text_sentiment_analyze_service
protocol: pythoncall
conformance_profile: standard

request_template:
  text: "input.text"

response_map:
  sentiment: "sentiment"
  confidence: "confidence"
```

And the service descriptor:

```yaml
# agent-skills/services/official/text_sentiment_analyze_service.yaml
id: text_sentiment_analyze_service
kind: pythoncall
module: official_services.text_sentiment_analyze
function: analyze_sentiment
```

---

## 4. Register the default

Add to `bindings/official/defaults.yaml`:

```yaml
text.sentiment.analyze: pythoncall_text_sentiment_analyze_baseline
```

---

## 5. Test it

```bash
# Verify the capability loads
python skills.py capabilities --search sentiment

# Verify the binding resolves
python skills.py explain-capability text.sentiment.analyze

# Execute via CLI
python skills.py run <a-skill-that-uses-it> --input '{"text": "I love this!"}'

# Run system checks
python skills.py doctor
```

---

## 6. Use it in a skill

```yaml
# agent-skill-registry/skills/official/text/sentiment-summary/skill.yaml
id: text.sentiment-summary
version: 0.1.0
name: Sentiment Summary
description: Detect sentiment then summarize with sentiment context.

inputs:
  text:
    type: string
    required: true

outputs:
  sentiment:
    type: string
    required: true
  summary:
    type: string
    required: true

steps:
  - id: analyze
    uses: text.sentiment.analyze
    input:
      text: inputs.text
    output:
      sentiment: outputs.sentiment

  - id: summarize
    uses: text.content.summarize
    config:
      depends_on: [analyze]
    input:
      text: inputs.text
    output:
      summary: outputs.summary

metadata:
  classification:
    role: procedure
    invocation: direct
    effect_mode: enrich
  tags: [text, sentiment, summarization]
```

---

## 7. Promote to the registry (optional)

```bash
# Package for promotion
python skills.py package-prepare --skill-id text.sentiment-summary --target-channel experimental

# Validate
python skills.py package-validate artifacts/promotion_packages/<package> --print-pr-command

# Create the PR
python skills.py package-pr artifacts/promotion_packages/<package>
```

---

## Checklist

- [ ] Capability YAML follows `<domain>.<entity>.<verb>` naming
- [ ] `inputs` and `outputs` have types and required flags
- [ ] Python baseline works without API keys
- [ ] Binding + service descriptor created
- [ ] Default registered in `defaults.yaml`
- [ ] `doctor` passes without new warnings
- [ ] Deep validation passes: `python tooling/validate_skills_deep.py`
- [ ] (Optional) Skill YAML created to compose the capability
