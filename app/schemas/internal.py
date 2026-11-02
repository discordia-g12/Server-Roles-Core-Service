from pydantic import BaseModel


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
