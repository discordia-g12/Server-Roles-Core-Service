# ADR 001: Modelo de permisos como bitmask (estilo Discord)

## Contexto del problema

El ADR 0003 (a nivel monorepo) define para `server_db` una tabla `roles` y
una tabla `permissions` separadas, sin especificar cómo se relacionan. Al
configurar Alembic para `Server-Roles-Core-Service` (issue #5) había que
resolver esa ambigüedad: ¿cómo se determina si un rol tiene un permiso dado,
y cómo se resuelven excepciones puntuales a nivel canal (ej. "este rol no
puede escribir en este canal en particular")?

Se necesitaba un modelo que:

- Permita chequear "¿este usuario puede hacer X en este canal?" de forma
  barata, porque ese chequeo se ejecuta en (potencialmente) cada request de
  la API y cada mensaje/acción en tiempo real.
- Soporte excepciones por canal (overrides), tanto a nivel rol como a nivel
  miembro puntual — el mismo patrón que Discord real.

## Decisión tomada

Cada permiso atómico (`SEND_MESSAGES`, `KICK_MEMBERS`, `MANAGE_CHANNELS`,
etc.) se representa como **un bit** dentro de un entero `BIGINT` (64 bits
disponibles, hoy se usan 21).

- **`roles.permissions_bitmask`** (`BIGINT`): los permisos base que ese rol
  otorga a nivel servidor. Un usuario con varios roles obtiene la unión
  (`OR` bit a bit) de los bitmasks de todos sus roles.
- **`permissions`**: tabla catálogo, **no se joinea en el chequeo de
  permisos**. Solo documenta qué significa cada bit (`bit_position`,
  `name`, `description`) y sirve para que el frontend/backoffice puedan
  listar los permisos disponibles por nombre en vez de por número mágico.
  Se siembra una única vez vía migración de datos
  (`..._seed_permissions_catalog.py`), no se modifica en runtime.
- **`channel_permission_overrides.allow_bitmask` /
  `deny_bitmask`**: excepciones puntuales a nivel canal, atadas a un
  `role_id` **o** a un `server_member_id` (nunca ambos — impuesto con un
  `CheckConstraint` XOR). El chequeo final de permisos en un canal es:

  ```
  efectivo = (permisos_base_del_usuario & ~deny_bitmask) | allow_bitmask
  ```

  es decir: el `deny` de un override de canal apaga el bit aunque el rol lo
  tenga, y el `allow` lo prende aunque el rol no lo tenga — el override de
  canal siempre gana por sobre el permiso base del rol.

Un chequeo de permiso completo es entonces una operación bitwise en memoria
(`bitmask & PERMISSION_BIT`), sin necesidad de JOINs contra la tabla
`permissions` ni de recorrer filas por cada permiso individual.

## Alternativas descartadas

- **Modelo relacional puro (una fila por permiso otorgado)**: una tabla
  `role_permissions` (many-to-many entre `roles` y `permissions`), con una
  fila por cada permiso que un rol tiene. Descartada porque:
  - Cada chequeo de "¿tiene este permiso?" requiere un JOIN o un `EXISTS`
    contra esa tabla, en vez de una comparación bitwise en memoria — más
    costoso bajo el volumen de chequeos que implica una plataforma de chat
    en tiempo real.
  - Con ~20 permisos por rol, cada servidor con varios roles termina con
    cientos de filas solo para representar qué-tiene-qué, sin beneficio
    real sobre el bitmask (los permisos de este dominio son un conjunto
    fijo y conocido de antemano, no datos abiertos que necesiten
    normalización).
  - Es, de todos modos, el modelo real y probado que usa Discord — la
    referencia directa de este TP — así que replicarlo reduce el riesgo de
    diseño.

- **Permisos como columnas booleanas individuales en `roles`** (`can_kick`,
  `can_ban`, `can_manage_channels`, ...): descartada. Cada permiso nuevo
  exigiría una migración de esquema (`ALTER TABLE ADD COLUMN`), contra
  simplemente agregar una fila al catálogo `permissions` con el bitmask.

## Consecuencias esperadas

- **Límite de 64 permisos** por el ancho de un `BIGINT`. Hoy se usan 21 bits
  (ver seed en `alembic/versions/..._seed_permissions_catalog.py`), con
  margen amplio para crecer. Si se llegara a necesitar más de 64, la
  migración natural es un segundo bitmask (`permissions_bitmask_2`) o pasar
  a `NUMERIC`/arreglo de bits — no es un problema previsto para el alcance
  de este TP.
- **La tabla `permissions` puede desincronizarse del código** si alguien
  agrega un bit nuevo en la lógica de la aplicación sin agregar la fila
  correspondiente al catálogo. Mitigación: los nombres de permisos deberían
  vivir como constantes compartidas (ej. un `Enum` de Python) usadas tanto
  para armar el bitmask en código como para la migración de seed, en vez de
  hardcodear el número de bit en dos lugares distintos.
- **Los permisos no son legibles directamente en SQL** sin decodificar el
  bitmask (ej. `SELECT * FROM roles WHERE permissions_bitmask & 4 != 0`
  requiere saber que el bit 2 es `MANAGE_ROLES`). Se acepta este costo a
  cambio de la velocidad de chequeo; el catálogo `permissions` existe
  justamente para no tener que memorizar los números.
