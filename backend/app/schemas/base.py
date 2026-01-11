from __future__ import annotations

from pydantic import BaseModel
from pydantic.config import ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
