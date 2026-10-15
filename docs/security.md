# Seguridad y protección de datos

## Controles implementados

| Área | Control |
| --- | --- |
| Entradas | Validación con Pydantic (longitudes, rangos, enumeraciones, formatos de fecha y URL). Errores 422 uniformes. |
| Base de datos | Solo ORM/consultas parametrizadas (SQLAlchemy). Restricciones `CHECK`, FKs e índices únicos. |
| Secretos | La IA (Claude Code) corre solo en el backend con la sesión de su CLI; no recibe los secretos del backend en su entorno. El token de JIRA se cifra con Fernet (`SECRETS_ENCRYPTION_KEY`) y nunca se devuelve por la API. Sin clave de cifrado, no se guardan tokens. |
| Registros | La auditoría filtra claves sensibles (`token`, `password`, `secret`, `api_key`…). Las trazas de IA (`ai_interactions`) guardan operación, modelo, estado y duración, no prompts ni claves. |
| Archivos y agente | Los documentos se adjuntan sin transformar (Word .docx, PDF —también escaneado— y texto plano; hasta `MAX_DOCUMENT_BYTES`, 10 MB). Se rechazan binarios, `.doc`, `.docm`, documentos con macros y PDF cifrados. El agente (Claude Code) recibe el archivo en una carpeta temporal aislada con **solo** la herramienta de lectura habilitada; en modo no interactivo la CLI rechaza leer fuera de esa carpeta (verificado). Un .docx no se puede leer como archivo: el agente recibe su texto y el original queda adjunto. Lo que extrae queda como requisitos «sugeridos» que el usuario confirma o rechaza. |
| Prompt injection | Los requisitos y documentos van delimitados como datos (`<<<DATOS>>>`) y el prompt de sistema ordena ignorar instrucciones contenidas en ellos. Las respuestas de la IA se validan contra esquemas; ninguna respuesta de IA dispara acciones externas o destructivas. |
| Acciones externas | JIRA: desactivado por defecto, prohibido en modo autónomo (403), requiere conexión validada, vista previa con huella vigente y confirmación escribiendo la clave del proyecto. |
| Operaciones destructivas | Eliminar proyecto exige `confirm=true` (y en la interfaz, escribir el nombre). Versiones de plan y escenarios aplicados no se pueden eliminar ni modificar. |
| Límites | Límite en memoria por IP para endpoints de IA (`AI_RATE_LIMIT_PER_MINUTE`). |
| HTTP | Cabeceras `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; CORS restringido a `CORS_ORIGINS`; descargas de PDF con `Cache-Control: no-store`. |

## Pendiente antes de un despliegue público

- Autenticación (SSO/OAuth) y autorización por proyecto o espacio de trabajo. Hoy la aplicación es de un solo espacio y el responsable se declara por cabecera `X-PM-User` (sanitizada); debe desplegarse solo en redes de confianza.
- Límite de solicitudes distribuido (el actual es por proceso).
- Rotación de `SECRETS_ENCRYPTION_KEY` (Fernet admite `MultiFernet` para rotación; no implementado).
- OAuth 2.0 (3LO) para JIRA con permisos mínimos (`read:jira-work`, `write:jira-work`) en lugar de API token.

## Política de retención de datos (propuesta)

- **Proyectos, requisitos, backlog, versiones y escenarios**: se conservan mientras el proyecto exista. Archivar un proyecto lo oculta sin borrar historial; eliminarlo borra todos sus datos en cascada.
- **PDF generados** (`exports`): se guardan en la base de datos para descarga posterior. Recomendado: purgar exportaciones con más de 180 días.
- **Auditoría** (`audit_log`) y **trazas de IA** (`ai_interactions`): recomendado 12 meses.
- **Secretos** (`stored_secrets`): se reemplazan al actualizar el token; se eliminan al borrar el proyecto (la referencia queda en `NULL`; conviene una tarea de limpieza de secretos huérfanos).
- **Datos enviados a Claude**: requisitos, análisis y métricas del plan se envían a Claude (Anthropic) mediante la CLI de Claude Code para las funciones de IA; revisá la política de datos de la cuenta u organización con la que se inició sesión antes de cargar información confidencial.
