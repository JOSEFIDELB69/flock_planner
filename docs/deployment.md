# Despliegue

> Estado: Flock Planner se ejecutó y verificó **solo en local**. No hay un despliegue cloud realizado.

## Componentes

| Componente | Imagen / build | Notas |
| --- | --- | --- |
| Base de datos | PostgreSQL 15+ administrado (RDS, Cloud SQL, Azure Database for PostgreSQL) | Backups automáticos y TLS. |
| Backend | `backend/Dockerfile` (Python 3.13 slim + fuente DejaVu para PDF) | Ejecuta `alembic upgrade head` y luego `uvicorn`. Escalable horizontalmente (sin estado en disco: los PDF van a la base). |
| Frontend | `frontend/Dockerfile` (Next.js `standalone`) | `API_BASE_URL` se fija en el **build** (rewrites de Next.js). |

## Pasos sugeridos

1. Crear la base PostgreSQL y un usuario con permisos sobre su esquema.
2. Cargar secretos en el gestor de la plataforma: `DATABASE_URL` y `SECRETS_ENCRYPTION_KEY` (si se usa JIRA). En el servidor del backend, instalar la CLI de Claude Code e iniciar sesión (`claude` → /login).
3. Construir y publicar las imágenes:
   ```bash
   docker build -t flock-planner-backend ./backend
   docker build -t flock-planner-frontend --build-arg API_BASE_URL=https://api.interna.ejemplo --build-arg NEXT_PUBLIC_APP_ENV=prod ./frontend
   ```
4. Desplegar el backend con `APP_ENV=production`, `CORS_ORIGINS=<url del frontend>` y sondas de salud en `/api/v1/health`.
5. Desplegar el frontend apuntando a la URL interna del backend.
6. Verificar `GET /api/v1/system/status` (base OK, IA disponible con Claude Code) y ejecutar el E2E contra staging:
   ```bash
   cd frontend && E2E_BASE_URL=https://staging.ejemplo npx playwright test
   ```

## Migraciones

```bash
cd backend
DATABASE_URL=postgresql+psycopg://... alembic upgrade head     # aplicar
alembic downgrade -1                                           # revertir la última
alembic revision --autogenerate -m "descripción"               # nueva migración tras cambiar models.py
alembic upgrade head --sql                                     # ver el SQL sin ejecutarlo
```

## Recomendaciones operativas

- Colocar el backend detrás del mismo dominio que el frontend (o red privada) y no exponerlo públicamente hasta incorporar autenticación.
- Timeouts del proxy ≥ 150 s para las operaciones de IA (generación del backlog).
- Monitorear la tabla `ai_interactions` (errores y latencia de Claude Code).
