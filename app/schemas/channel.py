from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(text|voice)$")
    category_id: UUID | None = None
    
class ChannelResponse(BaseModel): 
    id: UUID
    name: str
    type: str
    position: int

    model_config = ConfigDict(from_attributes=True)