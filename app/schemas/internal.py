from pydantic import BaseModel, ConfigDict, Field


class ChannelAccessResponse(BaseModel):
    server_id: str
    # SEND_MESSAGES y sin mute vigente
    can_send: bool
    # ISO 8601 en UTC con "Z". Solo si el mute es lo único que le impide escribir; si no, null
    muted_until: str | None = None
    # MENTION_EVERYONE en el canal: sin esto, @everyone y las menciones de rol quedan como texto plano
    can_mention_everyone: bool = False
    # Roles del servidor que se pueden mencionar (todos menos el por defecto, que es @everyone)
    mentionable_role_ids: list[str] = []
    # MANAGE_MESSAGES en el canal: autoriza a moderadores a borrar mensajes de otros
    can_manage_messages: bool = False
    # ADD_REACTIONS en el canal: autoriza a agregar reacciones
    can_add_reactions: bool = False


class VisibleChannelsResponse(BaseModel):
    # Canales de texto con VIEW_CHANNELS, de todos los servidores donde es miembro
    channel_ids: list[str]
    # Roles del usuario en esos servidores, sin el por defecto: Chat cuenta con esto las menciones de rol
    role_ids: list[str] = []


class CanSendResponse(BaseModel):
    can_send: bool = True
    server_id: str


class CanConnectResponse(BaseModel):
    can_connect: bool = True
    server_id: str
    # Qué puede publicar en la llamada: Voice lo pasa al token de LiveKit
    # SPEAK y sin mute vigente
    can_speak: bool
    can_video: bool
    can_screen_share: bool


class ServerPermissionsResponse(BaseModel):
    server_id: str
    user_id: str
    is_owner: bool
    can_moderate: bool
    permissions_bitmask: int


class ServerMemberIdsResponse(BaseModel):
    server_id: str
    # Ids de usuario de todos los miembros, incluido el dueño
    user_ids: list[str]


class ServersCreatedMetricsResponse(BaseModel):
    """Notification-Audit-Metrics: servidores creados en [from, to), para las métricas del backoffice."""

    model_config = ConfigDict(populate_by_name=True)

    # ISO 8601 en UTC con "Z", el mismo período que se pidió
    from_: str = Field(alias="from")
    to: str
    # Incluye los suspendidos. Los borrados no: el borrado es físico
    servers_created: int = Field(alias="serversCreated")
