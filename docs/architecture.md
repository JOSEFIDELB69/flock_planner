# Arquitectura de Flock Planner

## Visión general

```
Navegador ──► Next.js (frontend, :3000) ──/api/v1 proxy──► FastAPI (backend, :8000) ──► PostgreSQL
                                                              │
                                                              ├──► Claude Code CLI (solo backend, sin herramientas)
                                                              └──► JIRA Cloud (opcional, solo con confirmación)
```

- **Claude Code** fue el agente de desarrollo; la aplicación no depende de él en ejecución.
- **Claude Code** (CLI en modo headless) es el proveedor de IA en tiempo de ejecución (`backend/app/ai/claude_code.py`), seleccionado en `backend/app/ai/provider.py`.
- **La IA propone y explica; el motor calcula y valida.** Ninguna fecha, duración, porcentaje o capacidad sale de la IA.

## Backend

| Módulo | Responsabilidad |
| --- | --- |
| `app/api/*` | Endpoints REST versionados (`/api/v1`). OpenAPI en `/api/docs`. |
| `app/services/backlog.py` | Códigos correlativos, dependencias sin ciclos, aplicación del backlog generado, snapshots. |
| `app/services/plans.py` | Parámetros, cálculo con el motor, creación de versiones (la primera es línea base). |
| `app/services/scenarios.py` | Simulación, sugerencias, comparación y aplicación de escenarios. |
| `app/planning/engine.py` | Motor determinista de planificación (sin dependencias de base de datos). |
| `app/planning/compare.py` | Fórmulas de comparación, variantes sugeridas y criterio de recomendación. |
| `app/ai/*` | Proveedores Claude Code y demostración, prompts con delimitación de datos no confiables. |
| `app/pdf/reports.py` | Informes PDF a partir de la versión (snapshot) seleccionada. |
| `app/services/jira.py` | Cliente JIRA, vista previa, publicación autorizada, trazabilidad. |
| `app/services/audit.py` | Auditoría con filtrado de claves sensibles. |

Errores: todas las respuestas de error tienen la forma `{"error": {"code", "message", "details"}}` (`app/errors.py`). Los errores de IA devuelven 503 con mensaje comprensible; las operaciones solo confirman la transacción después de una respuesta válida, así que una falla de la IA no altera datos guardados.

## Motor de planificación

Entrada: subtareas (perfil, horas, dependencias), dependencias entre historias, equipo y parámetros.

1. **Grafo**: dependencias explícitas de tareas + dependencias entre historias (todas las tareas de la historia dependiente esperan a la historia previa) + QA de cada historia después de sus tareas de desarrollo. Se detectan ciclos.
2. **Esfuerzo efectivo**: tareas que no son de QA suman revisión (10 %) y retrabajo (10 %) por defecto.
3. **Capacidad**: por persona, `horas productivas × dedicación × disponibilidad × eficiencia`, donde la eficiencia baja un 5 % por cada persona adicional del mismo perfil (mínimo 60 %). Días no laborables, feriados y ausencias tienen capacidad 0.
4. **Asignación**: *list scheduling* por prioridad (camino más largo restante, luego prioridad de la historia) con inserción en huecos libres. Cada tarea la hace una sola persona; nadie trabaja en dos tareas a la vez. El tiempo se mide en días fraccionarios: durante el día *d* una persona avanza `capacidad(d)` horas.
5. **Resultados**: fechas por tarea, duración en días laborables del calendario del proyecto, utilización por perfil y persona, esperas, camino crítico (cadena de restricciones de dependencia o de recurso que determina el fin), cuellos de botella, hitos, costes y riesgos.

Costes: *coste por horas asignadas* = horas planificadas × tarifa (fórmula pedida); *coste de equipo* = horas pagadas durante la ventana del plan × tarifa (muestra el coste real de sumar gente que no reduce el plazo).

Comparación (backend y frontend usan la misma fórmula):

- Variación % = (duración escenario − duración línea base) / duración línea base × 100
- Ahorro = duración línea base − duración escenario

## Modelo de datos

Tablas principales (`backend/app/models.py`, migración `alembic/versions/0001_initial_schema.py`):

`projects`, `requirements`, `requirement_links`, `requirement_analyses`, `epics`, `user_stories`, `story_dependencies`, `tasks`, `task_dependencies`, `team_profiles`, `plan_versions`, `scenarios`, `exports`, `audit_log`, `ai_interactions`, `stored_secrets`, `integration_configurations`, `jira_publish_runs`, `jira_issue_links`.

Integridad:

- Claves foráneas con `ON DELETE CASCADE` desde el proyecto; `CHECK` para tipos, prioridades, estados, cantidades y dedicación.
- Índice único parcial: una sola línea base por proyecto.
- `plan_versions` es inmutable: un *listener* `before_update` rechaza cambios en el contenido; restaurar crea una versión nueva.
- Cada versión guarda un **snapshot** del backlog, el equipo y los parámetros: los PDF y comparaciones reflejan exactamente esa versión aunque el backlog cambie después.
- `jira_issue_links` es único por elemento local: reintentar una publicación no duplica incidencias.

## Frontend

- App Router de Next.js, componentes cliente con estados explícitos de carga, error, vacío y éxito (toasts).
- Proxy `/api/v1` → backend definido en `next.config.ts` (sin CORS en el navegador, sin secretos en el cliente).
- Tokens del sistema de diseño Flock IT en `src/app/globals.css` (tema claro y oscuro por `prefers-color-scheme`). Public Sans como respaldo de Tomato Grotesk; íconos Lucide.
- Accesibilidad: enlace "Saltar al contenido", foco visible naranja, diálogos con trampa de foco y `Escape`, etiquetas en todos los campos, estados con ícono + palabra, gráficos con `aria-label` descriptivo.
- Confirmación al abandonar formularios con cambios sin guardar (`useUnsavedChanges`).
