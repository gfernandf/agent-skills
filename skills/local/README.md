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
| Do NOT commit this directory to the shared registry. Promotion is done by packaging the skill into a registry PR. | Keeps instance-local work private and avoids leaking local overrides. |

## Lifecycle

1. **Draft** — author the skill here, run it locally.
2. **Promote to `experimental/`** — package the skill and open a PR on `agent-skill-registry` when you want early shared review with lighter gates.
3. **Promote to `community/`** — move to `skills/community/<domain>/<slug>/` once the admission checklist is complete and peer review is appropriate.
4. **Promote to `official/`** — maintainers may later move a proven community skill into `skills/official/`.

Typical CLI flow from this directory:

```powershell
python skills.py package-prepare --skill-id <domain.slug> --target-channel experimental
python skills.py package-validate "<package_path>" --print-pr-command
python skills.py package-pr "<package_path>"
```

## Gitignore

`skills/local/` is gitignored in this repo by default.
Only `.gitkeep` and this README are tracked.
