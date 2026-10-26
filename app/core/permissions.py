from enum import IntFlag


class Permission(IntFlag):
    """Mirror with bit_positions in alembic, if a permission is added, 
    it also has to be added in a new row in the migration."""
    VIEW_CHANNELS = 1 << 0
    MANAGE_CHANNELS = 1 << 1
    MANAGE_ROLES = 1 << 2
    MANAGE_SERVER = 1 << 3
    KICK_MEMBERS = 1 << 4
    BAN_MEMBERS = 1 << 5
    CREATE_INVITE = 1 << 6
    CHANGE_NICKNAME = 1 << 7
    MANAGE_NICKNAMES = 1 << 8
    SEND_MESSAGES = 1 << 9
    MANAGE_MESSAGES = 1 << 10
    EMBED_LINKS = 1 << 11
    ATTACH_FILES = 1 << 12
    ADD_REACTIONS = 1 << 13
    MENTION_EVERYONE = 1 << 14
    CONNECT = 1 << 15
    SPEAK = 1 << 16
    MUTE_MEMBERS = 1 << 17
    DEAFEN_MEMBERS = 1 << 18
    MOVE_MEMBERS = 1 << 19
    ADMINISTRATOR = 1 << 20


DEFAULT_ROLE_PERMISSIONS = (
    Permission.VIEW_CHANNELS
    | Permission.CREATE_INVITE
    | Permission.CHANGE_NICKNAME
    | Permission.SEND_MESSAGES
    | Permission.EMBED_LINKS
    | Permission.ATTACH_FILES
    | Permission.ADD_REACTIONS
    | Permission.CONNECT
    | Permission.SPEAK
)

# El dueño y ADMINISTRATOR tienen todos los permisos, sin importar roles ni overrides
ALL_PERMISSIONS = 0
for _permission in Permission:
    ALL_PERMISSIONS |= _permission.value


def effective_channel_permissions(
    *,
    role_bitmasks: list[int],
    role_overrides: list[tuple[int, int]],
    member_overrides: list[tuple[int, int]],
) -> int:
    """Permisos de un miembro (que no es el dueño) en un canal.

    `role_bitmasks`: permisos de cada rol del miembro. `role_overrides` / `member_overrides`: pares
    (allow, deny) de las reglas del canal para sus roles y para él. Primero se aplican las de rol y
    después las del miembro, que pisan a las de rol. ADMINISTRATOR tiene todo. El dueño también
    (ALL_PERMISSIONS), pero eso lo resuelve quien llama, sin consultar roles.
    """
    base = 0
    for bitmask in role_bitmasks:
        base |= bitmask
    if base & Permission.ADMINISTRATOR.value:
        return ALL_PERMISSIONS

    role_allow = role_deny = member_allow = member_deny = 0
    for allow, deny in role_overrides:
        role_allow |= allow
        role_deny |= deny
    for allow, deny in member_overrides:
        member_allow |= allow
        member_deny |= deny

    effective = (base & ~role_deny) | role_allow
    return (effective & ~member_deny) | member_allow