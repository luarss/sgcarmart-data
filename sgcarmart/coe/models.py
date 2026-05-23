from typing import Any

from pydantic import BaseModel, field_validator


class COERecord(BaseModel):
    month: str
    bidding_no: int
    vehicle_class: str
    quota: int
    bids_success: int
    bids_received: int
    premium: int

    @field_validator("bidding_no", "quota", "bids_success", "bids_received", "premium", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            return int(v)
        return v
