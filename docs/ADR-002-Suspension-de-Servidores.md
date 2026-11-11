# ADR-002: Suspensión de servidores por el staff de la plataforma

- **Estado:** Aceptado
- **Fecha:** 2026-11-08
- **Alcance:** este servicio (modelo, endpoints de staff, bloqueo), Chat Engine y Voice Signaling (eventos), Gateway
  (ruta de staff) y Discordia-WebApp (backoffice, web y mobile)
- **Relacionado:** ADR-002 del Gateway (rol staff y reglas para los endpoints del backoffice), ADR-002 de
  Auth-User-Service (suspensión de usuarios, el mismo esquema aplicado a cuentas)

---

## 1. Contexto

La consigna pide "Suspender servidor completo": el staff bloquea la actividad de un servidor mientras investiga una
denuncia, **sin borrar su contenido** (CA 1), y después puede levantar la suspensión para que los miembros recuperen el
acceso normal (CA 2).

Un servidor se usa por tres caminos, y los tres tienen que quedar cerrados:

- la API REST de este servicio (canales, roles, miembros, invitaciones, moderación, transferencias): unas 40 rutas
  bajo `/api/v1/servers/{server_id}/...`;
- el chat (WebSocket e historial) y la voz, que consultan a este servicio por `/internal/channels/{id}/...`;
- las conexiones que ya están abiertas al momento de suspender.

## 2. Decisión

| # | Tema | Decisión |
|---|------|----------|
| 1 | **Identificación** | El servidor se suspende **solo por su id** (UUID). El nombre no es único: dos servidores pueden llamarse igual, y suspender "por nombre" podría tocar el servidor equivocado. El backoffice pide el id; cuando exista el listado de servidores, se va a suspender desde cada fila |
| 2 | Estado | Columnas `servers.suspended_at`, `suspended_by` y `suspension_reason` (motivo obligatorio). Suspendido = `suspended_at` no nulo. No se toca nada más: canales, mensajes, roles y miembros se conservan tal cual (CA 1) |
| 3 | Endpoints (solo staff) | `POST /api/v1/admin/servers/{id}/suspension` (`{"reason": ...}`), `DELETE /api/v1/admin/servers/{id}/suspension`, `GET /api/v1/admin/servers/suspended` y `GET /api/v1/admin/servers` (listado con búsqueda por nombre o id: es de donde el staff saca el id). Kong exige `validate("staff")` y este servicio vuelve a chequear `X-User-Role` (`require_staff`) |
| 4 | Bloqueo de la API | Una dependencia a nivel router (`app/api/guards.py`, `reject_suspended_server`) en los routers de servidores y de moderación: toda ruta con `{server_id}` responde **403** con `type` `https://discordia.app/problems/server-suspended`. Estar en un solo lugar evita que una ruta nueva se olvide del chequeo. Única excepción: **salir del servidor** (no es usarlo) |
| 5 | Bloqueo de chat y voz | `ChannelAccessService.resolve`, el cálculo común de acceso a canal, escritura y conexión a voz, responde el mismo 403. `visible-channels` deja afuera los canales de servidores suspendidos (no cuentan para no leídos). Unirse con una invitación también da 403 |
| 6 | Conexiones abiertas | Eventos `server.suspended` (con `voice_channel_ids`) y `server.unsuspended`, por el Outbox en `server.events`. Chat cierra las sesiones de los canales de ese servidor; Voz saca a todos de sus llamadas y marca el servidor para que el webhook de LiveKit saque a quien entre con un token anterior |
| 7 | Quién queda afuera | **Todos los miembros, incluido el dueño.** La suspensión es de la plataforma: el dueño no la puede saltear |
| 8 | Qué ve un miembro | El servidor **sigue en su lista** (`GET /api/v1/servers` con `is_suspended: true`), **sin canales ni categorías**, y los clientes lo muestran con un **cartel rojo "suspended"**. Al abrirlo ven que está suspendido en lugar del contenido. Al levantarse la suspensión, todo vuelve a aparecer como estaba |

### Por qué el servidor no desaparece de la lista

Si desapareciera, el miembro no podría distinguir una suspensión de una expulsión o de un servidor borrado, y al
levantarse la suspensión el servidor reaparecería sin explicación. Con el cartel entiende qué pasó y que es temporal.
Como la lista no trae canales ni categorías, no expone contenido.

## 3. Alternativas descartadas

- **Identificar por nombre** (o "id o nombre"): ambiguo con nombres repetidos; obliga a manejar el caso de varios
  resultados y abre la puerta a suspender el servidor equivocado.
- **Chequear la suspensión en cada servicio de dominio** (canales, roles, invitaciones...): muchas funciones que
  recordar, y una ruta nueva podría quedar abierta. El guard a nivel router lo cubre todo.
- **Bloquear en Kong**: Kong no sabe qué servidores están suspendidos sin consultar a este servicio en cada request, y
  el chat y la voz no pasan por Kong para chequear permisos (usan `/internal`).
- **Ocultar el servidor de la lista**: ver "Por qué el servidor no desaparece de la lista".
- **Borrar o archivar el contenido**: la consigna pide conservarlo; eliminar un servidor es otra historia.

## 4. Consecuencias

- Una consulta más por request en las rutas de un servidor (una columna, por clave primaria).
- El dueño de un servidor suspendido tampoco puede administrarlo; solo puede salir.
- Chat y Voz tienen que consumir `server.suspended` (y Voz también `server.unsuspended`).
- Los clientes tienen que reconocer `is_suspended` en la lista, el 403 `server-suspended` y el cierre de WebSocket de
  Chat por suspensión del servidor.

## 5. Estado de implementación

| Pieza | Estado |
|-------|--------|
| Columnas y migración `d5e6f7a8b9c0` | Implementado |
| Endpoints de staff (suspender, levantar, listar) | Implementado (con tests) |
| Guard de rutas, acceso interno, invitaciones y `visible-channels` | Implementado (con tests) |
| Lista del miembro con `is_suspended` y sin contenido | Implementado (con tests) |
| Eventos `server.suspended` / `server.unsuspended` | Publicados por el Outbox |
| Ruta de staff en Kong, consumidores en Chat y Voz, backoffice y clientes | En sus repos |
