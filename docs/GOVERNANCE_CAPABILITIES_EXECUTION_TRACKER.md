# Governance Capabilities Execution Tracker

Este archivo es el registro operativo vivo para ejecutar el plan de mejora de governance capabilities sin perder continuidad.

## Regla De Operacion

1. Mantener este tracker actualizado en cada cambio de slice.
2. Registrar solo hechos verificables (cambios aplicados, verificaciones ejecutadas, deuda pendiente).
3. No cerrar items sin evidencia local o CI.

## Estado Actual

1. Slice MCP governance completo integrado en runtime y smoke.
2. Verificador dedicado `tooling/verify_mcp_governance_slices.py` activo en smoke.
3. Gap abierto relevante para tenancy governance: capacidades governance side-effecting sin `same_tenant` suficiente.

## Registro De Ejecucion

### Paso 1 - En Ejecucion

Hecho:

1. Inventario de governance capabilities en registry local ejecutado.
2. Resultado de inventario:
   - governance_caps: 19
   - with_same_tenant: 0
   - side_effects_true: 1
   - side_effects_true_missing_same_tenant: 1 (`identity.role.assign`)
3. Se agrego `allowed_targets: [same_tenant]` en `identity.role.assign` (registry).
4. Se amplio `tooling/verify_tenant_isolation_matrix.py` para exigir `identity.role.assign.yaml` en el cohort requerido.
5. Validacion tenant matrix ejecutada con enforcement (`--enforce-registry-capabilities`): 26/26 pass.
6. Secuencia CI-equivalente del registry ejecutada en local y en verde:
   - `tools/validate_registry.py`
   - `tools/governance_guardrails.py --fail-on-high-risk-overlap-channels community,official`
   - `tools/capability_governance_guardrails.py`
   - `tools/enforce_capability_sunset.py`
   - `tools/generate_catalog.py`
   - `tools/registry_stats.py`
7. Adoption threshold actualizado: `same_tenant adopted=9/9` en tenant matrix.

Pendiente inmediato:

1. Preparar commit separado por repo:
   - repo runtime (`agent-skills`): verificador + tracker.
   - repo registry (`agent-skill-registry`): capability contract + catalog regenerado.
2. Definir y ejecutar el siguiente cohort governance para same_tenant (capabilities de mayor riesgo/exposure).
3. Mantener este tracker como bitacora de avance por iteracion (hecho/falta/evidencia).

## Backlog Priorizado (Sin Fechas)

1. Expandir same_tenant en governance capabilities adicionales segun riesgo y exposure.
2. Endurecer rollout de SLO governance (de baseline a enforcement progresivo).
3. Mantener evidencia de cierre externa de branch/ruleset en release bundle.
4. Consolidar profundidad de arquitectura pendiente (durability/lineage/policy depth).

## Criterio De Cierre Del Tracker

1. Sin gaps abiertos de tenancy para capacidades governance side-effecting.
2. Verificadores de smoke/tenant/governance en verde de forma consistente.
3. Evidencia de release y gobernanza completa segun `docs/PRODUCT_100_EXECUTION_PLAN.md`.
