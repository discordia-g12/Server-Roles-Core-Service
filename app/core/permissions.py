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