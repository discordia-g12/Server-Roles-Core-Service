# Server-Roles-Core-Service

Servicio de servidores, canales, categorías, miembros, roles, invitaciones y moderación de Discordia
(Python 3.12, FastAPI, SQLAlchemy 2 async y PostgreSQL, con migraciones de Alembic). Calcula los permisos
efectivos de cada usuario y se los responde, por endpoints internos, a Chat-Engine y Voice-Signaling.
Publica sus eventos (`member.banned`, `role.permissions_updated`, ...) en RabbitMQ con un Transactional
Outbox.

Sigue el patrón *database per service*: esta base es solo suya. Los datos de otros dominios (por ejemplo,
los usuarios) llegan por API o por eventos, nunca por FK. `owner_id` y `user_id` son el `sub` de Auth0.

## Requisitos

- Python 3.12 (la versión de la imagen y del CI).
- Docker, para PostgreSQL y, si se usa el worker de outbox, RabbitMQ.

## Levantarlo en local

### Con Docker Compose (lo más rápido)

`docker-compose.yaml` levanta Postgres y la API con recarga en caliente (monta el repo en el contenedor y
aplica las migraciones al arrancar):

```bash
docker compose up -d
curl localhost:8080/readyz      # {"status":"ready"}
```

Swagger en `http://localhost:8080/docs`. Postgres queda en `localhost:5432` (`admin` / `password`, base `db`).
Bajarlo: `docker compose down` (con `-v` también borra los datos).

### Desde el host

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # runtime + test, lint y SAST

cp .env.example .env                        # apunta a Postgres en localhost:5432
docker compose up -d db                     # solo la base

alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

Probarlo. Sin Kong adelante, la identidad se manda a mano en `X-User-Id`:

```bash
curl -X POST localhost:8080/api/v1/servers -H 'X-User-Id: auth0|local-test' -F name="Mi servidor"
curl localhost:8080/api/v1/servers -H 'X-User-Id: auth0|local-test'
```

Crear un servidor también crea el rol por defecto y los canales "general" y "Voz General". El puerto
`8080` va directo al servicio: en producción solo se llega por Kong, porque cualquiera podría mandar un
`X-User-Id` falso.

### Worker de outbox (opcional)

Los cambios guardan su evento en `outbox_events` en la misma transacción. Un proceso aparte los publica en
RabbitMQ (exchange `server.events`). Sin el worker, la API funciona igual y los eventos esperan en la base.

```bash
docker run -d --name server-roles-rabbitmq -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=admin -e RABBITMQ_DEFAULT_PASS=admin rabbitmq:3-management-alpine

RABBITMQ_HOST=localhost python -m app.workers.outbox_publisher
# "Outbox publisher conectado a RabbitMQ, exchange=server.events"
```

### Con el resto del sistema

Para levantarlo junto con el Gateway y los demás servicios, usar el compose del orquestador
(`discordia-orchestrator/deploy/docker-compose.yml`, profile `local`). Ahí se llama `server-roles-service`
(con su worker `server-roles-outbox-worker`), usa la base `server_roles_db` y publica el 8002 para que
Chat y Voice lleguen a los endpoints internos.

## Variables de entorno

Se leen del entorno o de `.env` (el entorno tiene prioridad).

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | En `development`, SQLAlchemy loguea las consultas |
| `DATABASE_HOST` / `DATABASE_PORT` | — / `5432` | PostgreSQL (`DATABASE_HOST` es obligatoria) |
| `DATABASE_NAME` / `DATABASE_USER` / `DATABASE_PASSWORD` | — | Base y credenciales (obligatorias) |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | `rabbitmq` / `5672` | Broker del worker de outbox |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | `admin` / `admin` | Credenciales del broker |
| `RABBITMQ_EXCHANGE` | `server.events` | Exchange (topic) donde se publican los eventos |
| `AWS_REGION` | `us-east-1` | Región del bucket |
| `S3_BUCKET` | — | Bucket de íconos de servidor. Sin bucket o sin claves, la subida responde `503` y el resto funciona |
| `S3_PUBLIC_BASE_URL` | `https://<bucket>.s3.<region>.amazonaws.com` | Base de las URLs públicas que se guardan |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | — | Claves del usuario IAM del servicio, o de uno de desarrollo (pedirlas al equipo; no se commitean) |

## API

Todas las rutas públicas cuelgan de `/api/v1` y exigen `X-User-Id` (lo agrega Kong; `401` si falta). El
contrato completo lo genera FastAPI: `http://localhost:8080/docs` y `/openapi.json`.

| Recurso | Rutas |
|---|---|
| Servidores | `POST /servers` (form: `name` y un `icon` opcional), `GET /servers` (los del usuario, con canales, categorías y `my_permissions`), `GET /servers/mutual/{user_id}` (los que comparte con otro usuario, para el perfil público), `DELETE /servers/{id}/leave` |
| Ícono | `PUT` y `DELETE /servers/{id}/icon` (JPEG, PNG o WebP hasta 5 MB; se guarda en S3 como WebP) |
| Canales y categorías | `POST`, `PATCH` y `DELETE` de `/servers/{id}/channels` y `/categories`; `PUT .../channels/order` y `.../categories/order` |
| Roles | `GET /servers/{id}/roles` (cualquier miembro: los usa la web para mostrar y mencionar roles); `POST /servers/{id}/roles`; `PATCH` (nombre y color), `PATCH .../permissions`, `PATCH .../default` y `DELETE` de `/roles/{role_id}`; `GET .../members`; `PUT` y `DELETE .../members/{user_id}` (asignar y quitar) |
| Miembros | `GET /servers/{id}/members` (paginado); `DELETE /servers/{id}/members/{user_id}` (expulsar) |
| Moderación | `POST`, `GET` y `DELETE /servers/{id}/bans`; `POST` y `DELETE /servers/{id}/mutes` |
| Invitaciones | `POST /servers/{id}/invites`, `DELETE /servers/{id}/invites/{code}`, `GET /invites/{code}` (vista previa), `POST /invites/{code}/join` |
| Transferir propiedad | `POST /servers/{id}/transfers`, `GET .../transfers/pending`, y aceptar, rechazar o cancelar |
| Backoffice (**solo staff**, `X-User-Role: staff`; si no, `403 staff-only`) | `POST /admin/servers/{id}/suspension` (`{"reason": ...}`; `404` si no existe, `409` si ya estaba suspendido), `DELETE /admin/servers/{id}/suspension` (levantarla), `GET /admin/servers/suspended` ([ADR-002](docs/ADR-002-Suspension-de-Servidores.md)) |
| Salud | `GET /livez` (sin I/O) y `GET /readyz` (verifica la base) |

**Servidores suspendidos** ([ADR-002](docs/ADR-002-Suspension-de-Servidores.md)): toda ruta `/servers/{id}/...`
responde `403` con `type` `https://discordia.app/problems/server-suspended`, para cualquier miembro, incluido el dueño.
Solo se puede salir (`DELETE /servers/{id}/leave`). `GET /servers` lo sigue listando, con `is_suspended: true` y sin
canales ni categorías. Unirse con una invitación también da `403`.

**Endpoints internos** (`/internal`, sin prefijo de versión). Los usan Chat y Voice y **no pasan por Kong**.
Hoy no tienen autenticación: solo se llega a ellos por la red entre nodos.

| Ruta | Quién la usa | Devuelve |
|---|---|---|
| `GET /internal/channels/{id}/access?user_id=` | Chat, al abrir el WebSocket, al pedir el historial y al enviar un mensaje con `@everyone` o una mención de rol | `403` si no puede ver el canal o el servidor está suspendido (`server-suspended`); si puede, `server_id`, `can_send`, `muted_until`, `can_mention_everyone` (MENTION_EVERYONE) y `mentionable_role_ids` (roles del servidor sin el por defecto; vacío sin ese permiso) |
| `GET /internal/users/{id}/visible-channels` | Chat, para los no leídos y las menciones (`GET /unread`) | `channel_ids`: canales de texto con VIEW_CHANNELS en todos sus servidores; `role_ids`: sus roles, sin los por defecto |
| `GET /internal/channels/{id}/can-connect?user_id=` | Voice, al unirse a una llamada | Si puede entrar y qué puede publicar (micrófono, cámara, pantalla) |
| `GET /internal/channels/{id}/can-send?user_id=` | Versiones viejas de Chat | Deprecado: reemplazado por `access` |

### Permisos

Los permisos de un rol son un bitmask (`roles.permissions_bitmask`), y el permiso efectivo en un canal se
calcula con una función pura (`app/core/permissions.py`): la unión de los roles del miembro y los overrides
del canal. El dueño del servidor tiene todos. El catálogo de bits está en la tabla `permissions` y en
[ADR-001](docs/ADR-001-Permissions-Bitmask.md).

### Eventos que publica

Exchange `server.events` (topic). La routing key es el tipo de evento:

- canales y categorías: `channel.created`, `channel.updated`, `channel.deleted`, `channels.reordered` y lo
  mismo para `category.*`;
- roles: `role.permissions_updated` y `role.deleted`;
- miembros: `member.role_assigned`, `member.role_removed`, `member.left`, `member.kicked`,
  `member.banned`, `member.unbanned`, `member.muted` y `member.unmuted`;
- servidor: `server.suspended` (con `server_id`, `voice_channel_ids`, `reason`, `suspended_by`, `suspended_at`) y
  `server.unsuspended`.

Chat-Engine consume `member.*` (cierra sesiones, habilita o bloquea el envío) y `server.suspended` (cierra las
sesiones del servidor). Voice-Signaling consume `member.banned`, `member.kicked` y `member.left` (saca de la llamada) y
`server.suspended` / `server.unsuspended`.

## Tests, lint y seguridad

Los mismos comandos que corre el CI:

```bash
ruff check .                # lint (configuración en ruff.toml)
bandit -r app -ll           # SAST
pytest --cov=app            # tests + cobertura (el CI exige 70 %)
```

**Los tests necesitan un PostgreSQL**: usan las variables `DATABASE_*` para conectarse y crean (y borran)
una base aparte, `<DATABASE_NAME>_test`. Con `docker compose up -d db` y el `.env` del ejemplo alcanza. No
necesitan RabbitMQ ni S3 (los simulan).

### Migraciones

```bash
alembic upgrade head                                     # aplicar
alembic revision --autogenerate -m "describe el cambio"  # crear una a partir de app/models/
alembic downgrade -1                                     # deshacer la última
alembic check                                            # falla si los modelos y las migraciones no coinciden
```

Revisar siempre el archivo generado: `autogenerate` no detecta bien los `CheckConstraint` ni los índices
parciales. La URL no está en `alembic.ini`: `alembic/env.py` la arma desde `app.core.config.settings`.

## Modelo de datos

| Tabla | Descripción |
|---|---|
| `servers` | Servidor. `owner_id` es el usuario de Auth0, sin FK (otra base). `icon_url` apunta a S3 |
| `categories` | Agrupa canales dentro de un servidor, con `position` |
| `channels` | Canal de texto o voz, opcionalmente dentro de una categoría, con `position` |
| `server_members` | Membresía de un usuario en un servidor |
| `server_bans` / `server_mutes` | Baneos y silencios por servidor (el silencio puede vencer: `expires_at`) |
| `roles` | Rol de un servidor, con `permissions_bitmask`, color y si es el rol por defecto |
| `role_assignments` | Qué roles tiene cada miembro |
| `permissions` | Catálogo de los bits del bitmask (referencia, no se consulta en runtime) |
| `channel_permission_overrides` | Excepciones de permisos por canal, por rol o por miembro |
| `server_invites` | Códigos de invitación, con límite de usos y vencimiento |
| `server_ownership_transfers` | Transferencias de propiedad pendientes |
| `outbox_events` | Eventos pendientes de publicar en RabbitMQ |

Las PK son UUID generados en Python. Las FK dentro del servicio usan `ON DELETE CASCADE` (o `SET NULL` en
`channels.category_id`), para no dejar registros huérfanos.

## Estructura

```text
app/
├── main.py           app de FastAPI, /livez y /readyz
├── api/              rutas: server.py, moderation.py, internal.py; deps.py (identidad)
├── services/         lógica de negocio, permisos efectivos y S3
├── repositories/     acceso a datos
├── models/           un archivo por tabla
├── schemas/          modelos de Pydantic
├── workers/          publicador del outbox
├── core/             configuración y cálculo de permisos (permissions.py)
└── db/               engine, sesión y base declarativa
alembic/              migraciones (incluye el catálogo de permisos)
tests/
```

## CI/CD

`.github/workflows/ci.yml`, en cada push y PR a `main` y `develop`:

1. `test`: ruff, bandit, migraciones y pytest con cobertura mínima de 70 %, contra un Postgres de servicio.
2. `docker`: construye la imagen; en push la publica como `ghcr.io/discordia-g12/server-roles-service:<sha>`.
3. `deploy`: en push a `main`, la despliega en el nodo **edge** (servicio y worker) con el workflow del
   orquestador. Si no queda sana, vuelve sola a la versión anterior.

La imagen arranca solo uvicorn (`CMD` del `Dockerfile`): las migraciones las corre el comando del compose
(`alembic upgrade head && uvicorn ...`), tanto el de este repo como el de producción.

## Decisiones de arquitectura

| ADR | Tema |
|-----|------|
| [ADR-001](docs/ADR-001-Permissions-Bitmask.md) | Permisos como bitmask y no como modelo relacional puro |
| [ADR-002](docs/ADR-002-Suspension-de-Servidores.md) | Suspensión de servidores por el staff: solo por id, bloqueo a nivel router, eventos y cartel "suspended" |
