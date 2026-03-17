from pydantic import BaseModel, Field
from typing import Optional


class FeedbackCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    message: str
    order_id: Optional[int] = None
    item_id: Optional[int] = None
    deal_id: Optional[int] = None
    feedback_type: Optional[str] = "GENERAL"