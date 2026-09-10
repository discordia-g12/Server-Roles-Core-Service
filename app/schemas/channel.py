from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

class ChannelResponse(BaseModel): 
    id: UUID
    name: str
    type: str
    position: int

    model_config = ConfigDict(from_attributes=True)