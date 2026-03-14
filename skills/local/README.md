# Local Skills

This directory is the **user-defined skills root** for this `agent-skills` instance.

Skills placed here are executed locally and are **not** part of the official
`agent-skill-registry`.  They take **resolution priority** over skills with the
same id in the shared registry.

## Directory Layout

```
skills/local/<domain>/<slug>/skill.yaml
```

Same structure as the registry:

```
skills/local/
  crm/
    enrich-contact/
      skill.yaml
  finance/
    invoice-approval/
      skill.yaml
```

The runtime auto-detects this directory; no configuration is needed.

## Rules for local skills

| Rule | Rationale |
|------|-----------|
| Steps must reference **official or experimental capabilities** only (no custom capability ids). | Guarantees that each step maps to a real, tested execution binding. |
| IDs must not conflict with existing `official/` skills unless the intent is to **override** that skill. | Avoids silent shadowing. |
| A `metadata.channel: local` field is strongly recommended. | Makes it clear in governance reports that the skill is not registry-controlled. |
| Do NOT commit this directory to a shared repository unless the skill is being promoted to `community/` or `official/`. | Keeps instance-local work private. |

## Lifecycle

1. **Draft** — author the skill here, run it locally.
2. **Promote to `community/`** — open a PR on `agent-skill-registry`, placing the skill under `skills/community/<domain>/<slug>/`.  The PR template will guide you through the admission checklist.
3. **Promote to `official/`** — after community validation, maintainers move the skill to `skills/official/`.

## Gitignore

`skills/local/` is gitignored in this repo by default.
Only `.gitkeep` and this README are tracked.
