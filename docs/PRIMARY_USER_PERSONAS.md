# Primary User Personas — Agent Skills

> El usuario principal representa el **80% del uso humano** del framework.
> Se divide en dos perfiles según su comportamiento social.

---

## Perfil base: **El Integrador Pragmático**

**Quién es:** Desarrollador backend o fullstack (25–40 años) que construye
productos o automatizaciones con componentes de IA. No es investigador ML ni
DevOps puro — es el que **conecta piezas** para entregar funcionalidad.

**Contexto laboral:** Trabaja en equipo pequeño (2–8 personas) o como IC
(individual contributor) en empresa mediana. Tiene deadline. El framework es un
**medio**, no un fin — necesita que las cosas funcionen sin ceremonias.

**Nivel técnico:**
- Python intermedio-avanzado (lee decorators, entiende async, no escribe metaclasses)
- Familiaridad con YAML/JSON como formato de configuración
- Ha usado al menos un framework de orquestación (LangChain, Airflow, Prefect, o similar)
- Sabe qué es una API REST, ha consumido OpenAPI specs, puede debuggear con curl

**Motivación central:** Reducir el tiempo entre "tengo una idea" y "está corriendo
en producción". Busca **composabilidad sin lock-in** — quiere combinar capabilities
como bloques LEGO sin casarse con un vendor.

**Modelo mental:**
```
"Si defino el contrato (capability), el runtime resuelve cómo ejecutarlo.
Yo solo digo QUÉ quiero, no CÓMO se hace."
```

**Herramientas diarias:** VS Code, terminal, Git, pip/uv, pytest. Algunos usan
Docker. Pocos usan CI propio — confían en GitHub Actions.

**Tolerancia al dolor:**
- ❌ No tolera: documentación incompleta, errores crípticos, setup de más de 5 min
- ⚠️ Tolera con quejas: YAMLs verbose, convenciones no obvias, CLI con muchos subcomandos
- ✅ Acepta bien: convenciones claras una vez aprendidas, pipelines declarativos, test fixtures

---

## Perfil A: **El Solitario Productivo** (~55% del 80%)

> Representación: `44% del total de usuarios humanos`

### Identidad

| Atributo | Valor |
|----------|-------|
| **Nombre arquetipo** | *Santi* |
| **Rol** | Backend developer / IC senior |
| **Equipo** | Trabaja solo o en equipo donde es el único usando agent-skills |
| **Comunicación** | Consume docs, no genera contenido público |
| **Adopción** | Encontró el proyecto vía búsqueda, README, o recomendación directa |

### Comportamiento

**Sesión típica:**
```
git clone → pip install -e ".[all]" → agent-skills doctor
→ agent-skills run text.summarize-plain-input --input '{...}'
→ (funciona) → cierra terminal, vuelve en 3 días cuando necesita otra skill
```

**Patrón de uso del CLI:**

| Frecuencia | Comandos |
|------------|----------|
| **Diario** | `run`, `ask`, `list` |
| **Semanal** | `scaffold`, `test`, `validate`, `dev` |
| **Mensual** | `describe --mermaid`, `check-wiring`, `benchmark-lab` |
| **Nunca** | `contribute`, `report`, `rate`, `package-pr` |

**Cómo resuelve problemas:**
1. Lee el error en terminal
2. Busca en `README.md` o `docs/` con grep/Ctrl+F
3. Si no encuentra → lee el código fuente directamente (`cli/main.py`, `runtime/`)
4. Si sigue bloqueado → abandona esa ruta y prueba otra
5. **No abre issues. No pregunta en discussions. No da feedback.**

**Lo que valora:**
- `agent-skills doctor` — verificación inmediata de que todo está bien
- Ejemplos que copiar-pegar (`examples/simple_text_skill.yaml`)
- Mensajes de error que le digan **qué hacer**, no solo qué falló
- `--json` en todos los comandos — parsea output programáticamente
- `sdk/embedded.py` — evita levantar servidor HTTP para uso local

**Lo que ignora:**
- CONTRIBUTING.md (nunca lo abre)
- Discussion templates
- El contributor ladder
- Governance, admission policies, RFC process
- CHANGELOG.md (no hace upgrade frecuente)

**Riesgo para el proyecto:**
- **Churn silencioso**: si algo no funciona, desaparece sin decir nada
- **Deuda de percepción**: puede tener una mala experiencia y nunca lo sabremos
- **Zero feedback loop**: no genera señales que nos permitan mejorar

**Señales de retención:**
- `pip install` repetido (upgrade) en >30 días
- Uso de `scaffold` (está creando skills propias → invested)
- Uso de `compose` (está orquestando → power user silencioso)
- Uso de `embedded.py` imports (integró en su app → high retention)

### Diseño para Santi

| Principio | Implementación |
|-----------|---------------|
| **Zero-config happy path** | `doctor` + `run` deben funcionar sin vars de entorno |
| **Error messages = docs** | Cada error incluye el comando para resolverlo |
| **Copy-paste examples** | Cada feature tiene un ejemplo autocontenido en README |
| **Offline-first** | Baselines determinísticos sin API keys |
| **Progressive disclosure** | `list` → `run` → `scaffold` → `compose` (complejidad gradual) |
| **Silent telemetry hooks** | Opt-in anonymous usage metrics para detectar friction points |

---

## Perfil B: **El Evangelista Técnico** (~45% del 80%)

> Representación: `36% del total de usuarios humanos`

### Identidad

| Atributo | Valor |
|----------|-------|
| **Nombre arquetipo** | *Mara* |
| **Rol** | Tech lead / Senior dev / DevRel-adjacent |
| **Equipo** | Lidera o influye en adopción dentro de su equipo |
| **Comunicación** | Escribe blog posts, responde en Discussions, abre issues |
| **Adopción** | Evaluó el proyecto, lo adoptó, y ahora lo promueve internamente |

### Comportamiento

**Sesión típica:**
```
agent-skills discover "extract entities from legal docs"
→ no encuentra la skill que quiere
→ agent-skills scaffold "extract named entities from legal text"
→ edita el YAML, prueba con `dev`, valida con `check-wiring`
→ agent-skills contribute legal.entity-extract
→ abre PR, escribe un blog post "How I built a legal entity extractor in 20 min"
```

**Patrón de uso del CLI:**

| Frecuencia | Comandos |
|------------|----------|
| **Diario** | `run`, `ask`, `dev`, `test` |
| **Semanal** | `scaffold`, `describe --mermaid`, `compose`, `benchmark-lab` |
| **Mensual** | `contribute`, `rate`, `export`, `triggers` |
| **Ocasional** | `report`, `discover --similar`, `package-pr` |

**Cómo resuelve problemas:**
1. Lee el error → busca en docs
2. Si no encuentra → **abre un Issue** con reproducción exacta
3. Si encuentra una solución → **la documenta** (Discussion, blog, PR a docs)
4. Si descubre un patrón → propone mejora (feature_request o RFC)
5. **Siempre deja rastro público de su experiencia**

**Lo que valora:**
- `contribute` — pipeline de contribución integrado
- `describe --mermaid` — visualización para compartir con el equipo
- `benchmark-lab` — datos para justificar decisiones técnicas ante stakeholders
- `rate` + `report` — canales para expresar opinión
- `compose` DSL — puede mostrar al equipo que en 5 líneas se arma un pipeline
- Discussion templates — lugar para proponer ideas
- CHANGELOG.md — lo lee en cada release para saber qué cambió

**Lo que ignora:**
- Nada. Lee prácticamente todo. Incluso `docs/SKILL_GOVERNANCE_MANIFESTO.md`.

**Riesgo para el proyecto:**
- **Amplificación negativa**: si tiene una mala experiencia, la publica
- **Expectation gap**: espera roadmap, release cadence, respuesta rápida a issues
- **Governance friction**: quiere contribuir pero si el proceso es lento, se frustra
- **Platform dependency**: si construye tooling sobre agent-skills y hay breaking changes, se siente traicionado

**Señales de retención:**
- PRs abiertos (contribuyendo activamente)
- Issues con label `enhancement` (invirtiendo en el futuro del proyecto)
- Star + Watch en GitHub (señal social)
- Menciones externas (blog posts, tweets, talks)
- Uso de `export` → `import` (distribuyendo skills a otros)

### Diseño para Mara

| Principio | Implementación |
|-----------|---------------|
| **Contribution = first-class UX** | `contribute` pipeline fluido, <5 min del skill al PR |
| **Shareable artifacts** | Mermaid, JSON export, `.skill-bundle.tar.gz` — todo shareable |
| **Transparent governance** | Admission policy, RFC process, contributor ladder visibles |
| **Fast feedback loops** | Issue triage <3 días, review <5 días (CONTRIBUTING.md SLAs) |
| **Breaking change discipline** | Semver, deprecation notices, migration guides |
| **Community recognition** | Contributor ladder, AUTHORS file, release notes con credits |

---

## Matriz comparativa

| Dimensión | Santi (Solitario) | Mara (Evangelista) |
|-----------|--------------------|--------------------|
| **% del total** | 44% | 36% |
| **Motivación** | Resolver MI problema | Resolver problemas + compartir |
| **Tiempo en docs** | Solo cuando está bloqueado | Proactivamente, para aprender |
| **Feedback** | Cero. Silencio total. | Issues, PRs, Discussions, blogs |
| **Decisión de adopción** | Individual | Influye en equipo/org |
| **Riesgo de churn** | Alto (invisible) | Bajo (señales tempranas) |
| **Valor por usuario** | 1x (uso directo) | 5-10x (multiplicador social) |
| **Comandos favoritos** | `run`, `ask`, `list` | `scaffold`, `contribute`, `dev` |
| **Feature killer** | Embedded runtime (K2) | Compose DSL (K6) + `contribute` |
| **Se retiene con** | Zero-friction, works first try | Roadmap visible, fast PR reviews |
| **Se pierde con** | Error sin solución clara | Issue sin respuesta en 7 días |

---

## Implicaciones de diseño

### Para retener a Santi (el invisible):
1. **Instrumentar sin molestar** — usage metrics opt-in anónimos para detectar dónde se atascan
2. **Error UX superlativa** — cada excepción incluye `hint:` con el comando que resuelve
3. **"Did you mean?" en CLI** — typo correction y sugerencias para comandos cercanos
4. **Smoke test en install** — `pip install` → auto-`doctor` → primer skill funciona
5. **Embedded by default** — el path `from sdk.embedded import execute` debe ser tan fácil como `requests.get()`

### Para potenciar a Mara (la multiplicadora):
1. **Contribution funnel sin fricción** — `contribute` → PR → review → merge en <7 días
2. **Shareable visuals** — Mermaid SVG export, benchmark tables, compose DSL snippets
3. **Public recognition** — `AUTHORS.md`, release credits, contributor badges
4. **Office hours / Discussions activas** — respuesta en <48h
5. **Roadmap público** — `ROADMAP.md` actualizado, milestones en GitHub Projects

### Para ambos:
1. **Progressive complexity** — `run` (0 config) → `scaffold` (guiado) → `compose` (power) → `triggers` (event-driven)
2. **Baseline-first** — siempre funciona sin API keys, LLM es upgrade opcional
3. **`ask` como puerta de entrada** — NL autopilot reduce la barrera cognitiva de "¿qué skill necesito?"
4. **`dev` watch mode** — feedback loop instantáneo = retención
