from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(text|voice)$")
    category_id: UUID | None = None
    
class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    topic: str | None = Field(None, max_length=1024)
    
class ChannelResponse(BaseModel): 
    id: UUID
    name: str
    type: str
    position: int
    topic: str | None = None

    model_config = ConfigDict(from_attributes=True)