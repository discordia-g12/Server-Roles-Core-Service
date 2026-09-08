# Server-Roles-Core-Service

Servicio de dominio "Servidores, Canales, Miembros y Roles" de Discordia. Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16, migrado con Alembic. Sigue el patrón **Database-per-Service**: esta es la única base de datos que este servicio puede leer/escribir; cualquier dato de otro dominio (ej. usuarios) llega vía API o eventos, nunca por FK directa.

## Stack

| | |
|---|---|
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async, driver `asyncpg`) |
| Migraciones | Alembic (plantilla `async`) |
| Base de datos | PostgreSQL 16 |
| Config | pydantic-settings |

## Setup local

```bash
cp .env.example .env          # ajustar si hace falta
docker compose up -d db       # levanta solo Postgres, mapeado a localhost:5432

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

alembic upgrade head           # aplica todas las migraciones
uvicorn app.main:app --reload  # levanta la API
```

También se puede correr todo containerizado:

```bash
docker compose up -d db
docker compose run --rm app alembic upgrade head
docker compose up -d app
```

## Estructura

```
app/
  core/config.py     # Settings (pydantic-settings), arma la URL de conexión async
  db/base.py          # Base declarativa de SQLAlchemy + naming convention de constraints
  db/session.py        # engine async + AsyncSessionLocal + get_db() (dependency de FastAPI)
  models/              # un archivo por tabla (ver abajo)
  api/, schemas/, repositories/, services/   # placeholders, sin uso todavía

alembic/
  env.py                          # runner async de migraciones, importa app.models y settings
  versions/
    ..._initial_schema.py          # crea las 11 tablas
    ..._seed_permissions_catalog.py # siembra el catálogo de permisos (ver ADR-001)
```

## Modelo de datos (`server_db`)

| Tabla | Modelo | Descripción |
|---|---|---|
| `servers` | `Server` | Un servidor de Discordia. `owner_id` referencia `auth_db.users` sin FK (otra base). |
| `categories` | `Category` | Agrupador visual de canales dentro de un servidor. |
| `channels` | `Channel` | Canal de texto o voz (`type`), opcionalmente dentro de una `category`. |
| `server_members` | `ServerMember` | Membresía de un usuario (`user_id`, sin FK) en un servidor. |
| `server_bans` | `ServerBan` | Baneos de usuarios por servidor. |
| `server_mutes` | `ServerMute` | Mutes de usuarios por servidor, con `expires_at` opcional. |
| `roles` | `Role` | Rol de un servidor, con `permissions_bitmask` (ver ADR-001). |
| `permissions` | `Permission` | Catálogo de referencia de los bits de `permissions_bitmask`. No se joinea en runtime. |
| `role_assignments` | `RoleAssignment` | Join `server_members` ↔ `roles`: qué roles tiene cada miembro. |
| `channel_permission_overrides` | `ChannelPermissionOverride` | Excepciones de permisos a nivel canal, por rol o por miembro (ver ADR-001). |
| `outbox_events` | `OutboxEvent` | Transactional Outbox — eventos de negocio pendientes de publicar a RabbitMQ. |

Todas las PK son `UUID` (generadas en Python, no en la DB). Todas las FKs entre tablas de este mismo servicio usan `ON DELETE CASCADE` (o `SET NULL` en `channels.category_id`), para que borrar un servidor/canal no deje registros huérfanos.

Decisiones de arquitectura documentadas en `docs/`:
- [`ADR-001-Permissions-Bitmask.md`](docs/ADR-001-Permissions-Bitmask.md) — por qué los permisos son un bitmask y no un modelo relacional puro.

## Migraciones (Alembic)

```bash
# generar una migración a partir de cambios en app/models/
alembic revision --autogenerate -m "descripción del cambio"

# revisar el archivo generado en alembic/versions/ antes de aplicarlo —
# autogenerate no siempre detecta bien CheckConstraints o índices parciales

alembic upgrade head       # aplicar
alembic downgrade -1        # revertir la última
alembic check                # falla si el modelo y la última migración no coinciden
```

La URL de conexión no está hardcodeada en `alembic.ini`: `alembic/env.py` la arma en runtime desde `app.core.config.settings`, que lee las variables `DATABASE_*` del entorno (o de `.env` si se corre fuera de Docker).
