"""用途：分页等公共模型。"""
from pydantic import BaseModel, Field


class Page(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
