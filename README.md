# Flock Planner

Plataforma web que convierte requisitos de negocio en planes de desarrollo de software estructurados, estimados, calendarizados y optimizados.

**Funciona completa sin JIRA.** La integración con JIRA Cloud es opcional, está desactivada por defecto y nunca publica sin vista previa y confirmación explícita.

| Capa | Tecnología |
| --- | --- |
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Recharts · Lucide |
| Backend | Python · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 |
| Persistencia | PostgreSQL (producción) · SQLite solo para desarrollo/pruebas |
| IA en ejecución | Claude Code (CLI en modo headless, sin herramientas; modelo configurable con `CLAUDE_CODE_MODEL`) |
| PDF | ReportLab, generado en el backend |
| Diseño | Tokens del sistema de diseño Flock IT (violeta noche, violeta de marca, naranja de acento, formas pill) |

## Estado actual (v0.1.0)

Implementado y verificado:

- Flujo autónomo completo: proyecto → requisitos → análisis con IA → backlog (épicas, historias, criterios Given/When/Then, subtareas) → estimación por perfil → planificación con motor determinista → línea base inmutable → escenarios de equipo → aplicar escenario (versión nueva) → PDF.
- Observaciones de la generación del backlog: los supuestos y advertencias del agente quedan guardados; cada uno se acepta o se corrige (con enlace al requisito o a las preguntas de aclaración) y, al regenerar, las correcciones y los supuestos aceptados se envían al agente como información confirmada.
- Motor de planificación propio: dependencias entre tareas e historias, QA después del desarrollo, capacidad por persona (horas productivas × dedicación × disponibilidad × coordinación), seniority SR/SSR/JR en perfiles de desarrollo y QA (ajuste porcentual configurable del tiempo de cada tarea; por defecto SR −15 %, SSR 0 %, JR +30 %), calendario laboral, feriados, ausencias, camino crítico con restricciones de recursos, cuellos de botella, hitos, costes.
- Pronóstico probabilístico (Monte Carlo): cada tarea tiene un rango optimista–estimado–pesimista (propuesto por el agente, editable en Estimaciones o derivado de la confianza de la historia). El motor recalcula el plan 500 veces con distribución triangular y correlación 0,3 entre tareas (semilla fija, reproducible) y reporta P50/P80/P90, la probabilidad de cumplir la fecha del plan y la fecha objetivo, y la reserva por imprevistos necesaria para 80 % de confianza. Se muestra en Planificación, Optimización y en el PDF.
- Optimización: escenarios manuales y sugeridos, comparación contra la línea base, perfiles que no mejoran el plazo, recomendación determinista, explicación con IA (solo explica cifras del motor).
- Versionado y auditoría: versiones inmutables (protección a nivel ORM e índice único de línea base), restauración como versión nueva, historial de cambios por requisito y auditoría por proyecto sin secretos.
- Tres informes PDF (completo, ejecutivo, optimización) con portada, encabezados, pies, numeración, metadatos y caracteres en español.
- Integración JIRA Cloud opcional (API token cifrado con Fernet, vista previa con huella, confirmación escribiendo la clave del proyecto, prevención de duplicados, registro de errores parciales).
- Modo demostración (`AI_PROVIDER=demo`) sin IA: todos sus resultados se marcan como **simulados** en la interfaz, en la base y en los PDF.

Pendiente o limitado (ver [Problemas conocidos](#problemas-conocidos-y-próximos-pasos)).

## Inicio rápido (desarrollo local)

Requisitos: Python 3.12+ (probado con 3.14), Node.js 22+ (probado con 24), y PostgreSQL 15+ **o** SQLite para una prueba local rápida.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt # Linux/macOS
```

Creá `backend/.env` a partir de [`.env.example`](.env.example). Para probar sin PostgreSQL:

```dotenv
DATABASE_URL=sqlite:///./pm_agent_dev.db
AI_PROVIDER=demo        # o claude_code (por defecto) si la CLI tiene sesión iniciada
SECRETS_ENCRYPTION_KEY=<clave Fernet, solo si vas a configurar JIRA>
```

Migraciones y arranque:

```bash
cd backend
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Documentación OpenAPI: <http://localhost:8000/api/docs> (Swagger) y <http://localhost:8000/api/redoc>.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abrí <http://localhost:3000>. El navegador solo habla con Next.js; las llamadas `/api/v1/*` se reenvían al backend (`API_BASE_URL`, por defecto `http://localhost:8000`). La IA (Claude Code) se ejecuta solo en el backend; el navegador nunca la invoca directamente.

### 3. Todo con Docker y PostgreSQL

```bash
cp .env.example .env    # completá SECRETS_ENCRYPTION_KEY si vas a usar JIRA
docker compose up --build
```

El contenedor del backend aplica `alembic upgrade head` antes de arrancar.

## Variables de entorno

| Variable | Modo autónomo | Con IA real | Con JIRA | Descripción |
| --- | --- | --- | --- | --- |
| `DATABASE_URL` | **Obligatoria** | **Obligatoria** | **Obligatoria** | PostgreSQL en producción (`postgresql+psycopg://…`). |
| `AI_PROVIDER` | Opcional | Opcional | — | `claude_code` (por defecto) o `demo` (resultados simulados, marcados como tales). |
| `CLAUDE_CODE_PATH`, `CLAUDE_CODE_MODEL`, `CLAUDE_CODE_TIMEOUT_SECONDS` | — | Opcionales | — | Ruta de la CLI si no está en el `PATH`, modelo (vacío = el de la CLI) y tiempo máximo por llamada. |
| `SECRETS_ENCRYPTION_KEY` | — | — | **Obligatoria** | Clave Fernet para cifrar el API token de JIRA. |
| `APP_ENV`, `APP_BASE_URL`, `API_BASE_URL`, `CORS_ORIGINS` | Opcionales | | | Ver `.env.example`. |
| `AI_RATE_LIMIT_PER_MINUTE`, `MAX_UPLOAD_BYTES` | Opcionales | | | Límites de uso. |

**Proveedor de IA: Claude Code.** El backend usa la CLI de Claude Code en modo headless (`claude -p`). Se ejecuta sin herramientas, sin MCP, sin persistir sesión, en un directorio temporal vacío y sin los secretos del backend en su entorno. Requiere haber iniciado sesión antes (`claude` → `/login`). Si la CLI no está en el `PATH`, se usa la incluida en la app de escritorio o la indicada en `CLAUDE_CODE_PATH`. Sus resultados son IA real (no se marcan como simulados).

Sin una sesión de Claude Code iniciada, todo lo demás funciona: carga manual de requisitos y backlog, estimación, planificación, escenarios, versiones y PDF.

## Pruebas

```bash
# Backend: unitarias del motor + integración de la API con migraciones reales (IA y JIRA simulados)
cd backend && .venv/Scripts/python -m pytest -q

# Frontend: tipos y utilidades
cd frontend && npm run typecheck && npm test

# E2E (requiere backend con AI_PROVIDER=demo o claude_code y frontend en ejecución; usa Edge/Chrome instalado)
cd frontend && npx playwright test
# otro navegador: E2E_BROWSER_CHANNEL=chrome npx playwright test
```

Resultados de la última ejecución (09/10/2026): backend **56/56**, frontend **6/6** + `tsc` y `next build` sin errores, E2E **1/1** (flujo completo por la interfaz con descarga de PDF).

Cobertura de la lista de pruebas obligatorias: creación de proyecto, requisitos, análisis con IA (simulada en pruebas), indisponibilidad de la IA sin pérdida de datos, backlog, subtareas, estimación por perfil, duración calendario, dependencias, línea base, cambios de desarrolladores y QA, varios escenarios, comparación, aplicación, preservación de la línea base, versiones, PDF válido y descargable, recuperación tras reinicio, funcionamiento sin JIRA, ausencia de publicaciones en modo autónomo, rechazo de publicaciones no autorizadas, controles de seguridad y consistencia de la fórmula de variación entre frontend y backend.

## Estructura

```
backend/
  app/
    main.py            FastAPI, CORS, cabeceras de seguridad, routers /api/v1
    config.py db.py    configuración (variables de entorno) y sesión SQLAlchemy
    models.py          modelo relacional + guardia de inmutabilidad de versiones
    schemas.py         validación de entradas/salidas (Pydantic)
    errors.py          respuestas de error uniformes {"error": {code, message, details}}
    planning/          motor determinista (engine.py), adaptadores y comparación de escenarios
    ai/                proveedor Claude Code (CLI), demostración y prompts
    services/          backlog, planes, escenarios, auditoría, cifrado, JIRA
    pdf/reports.py     informes PDF
    api/               endpoints REST
  alembic/             migraciones
  tests/               pytest
frontend/
  src/app/             páginas (dashboard, proyectos y 12 secciones por proyecto)
  src/components/      AppShell, UI, gráficos, Gantt, editores de backlog y equipo
  src/lib/             cliente API, tipos, formato AR
  e2e/                 Playwright
docs/                  arquitectura, seguridad y despliegue
```

Más detalle en [docs/architecture.md](docs/architecture.md), [docs/security.md](docs/security.md) y [docs/deployment.md](docs/deployment.md).

## Problemas conocidos y próximos pasos

- **PostgreSQL no se ejecutó en este entorno** (no había Docker ni PostgreSQL instalados). Las pruebas corren sobre SQLite con las migraciones reales, y el DDL de PostgreSQL se validó generando el SQL de la migración en modo offline (JSONB, índice parcial de línea base, FKs circulares diferidas). Primer paso recomendado: `docker compose up` y ejecutar la suite con `DATABASE_URL` apuntando a PostgreSQL.
- **IA con Claude Code verificada en vivo** (análisis de requisitos, 70–90 s por llamada). La generación del backlog, el resumen ejecutivo y la explicación de escenarios con Claude Code real aún no se probaron.
- **Sin autenticación multiusuario.** El responsable de los cambios se toma del nombre configurado en el navegador (cabecera `X-PM-User`). Antes de exponer la app en Internet: SSO/OAuth, autorización por proyecto y espacios de trabajo.
- **JIRA usa API token** (email + token). OAuth 2.0 (3LO) queda como evolución; la integración se probó con un transporte HTTP simulado, no contra un sitio real.
- La generación con IA es síncrona (hasta ~2 min). Si los backlogs crecen, conviene una cola de tareas.
- No se desplegó en la nube: solo se ejecutó localmente. Ver [docs/deployment.md](docs/deployment.md).

Próxima fase recomendada: validar con PostgreSQL real y completar las pruebas de IA con Claude Code, agregar autenticación y autorización por proyecto, y desplegar en un entorno de staging.
