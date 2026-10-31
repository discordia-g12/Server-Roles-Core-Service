from pydantic import BaseModel


class ChannelAccessResponse(BaseModel):
    server_id: str
    # SEND_MESSAGES y sin mute vigente
    can_send: bool
    # ISO 8601 en UTC con "Z". Solo si el mute es lo único que le impide escribir; si no, null
    muted_until: str | None = None


class VisibleChannelsResponse(BaseModel):
    # Canales de texto con VIEW_CHANNELS, de todos los servidores donde es miembro
    channel_ids: list[str]


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
