from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field, field_validator
from datetime import date


class Variant(BaseModel):
    variant_name: str = Field(..., description="e.g., '1.6 STANDARD', '2.5 PREMIUM HYBRID', 'Long'")
    engine_size: Optional[str] = Field(None, description="e.g., '1.6', '2.0', '3.0L'")
    list_price: Optional[float] = Field(None, description="List price without COE")

    @field_validator('list_price', mode='before')
    @classmethod
    def parse_price(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            return float(v.replace(',', ''))
        return v


class CarModel(BaseModel):
    brand: str = Field(..., description="e.g., 'Toyota', 'Mercedes-Benz', 'BYD'")
    model_name: str = Field(..., description="e.g., 'COROLLA ALTIS', 'Vito 114 CDI Van', 'eT3'")
    category: Optional[str] = Field(None, description="e.g., 'SEDAN', 'SUV', 'MPV', 'SPORTS', 'Commercial'")
    vehicle_type: Optional[Literal["ICE", "Hybrid", "Electric"]] = Field(None, description="Powertrain type")
    variants: List[Variant] = Field(default_factory=list, description="Different trim levels or configurations")


class PriceListDocument(BaseModel):
    valid_from: Optional[date] = Field(None, description="Start date of price validity")
    valid_to: Optional[date] = Field(None, description="End date of price validity")
    models: List[CarModel] = Field(..., description="All car models in this pricelist")


class APIUsageStats(BaseModel):
    model_name: str = Field(..., description="Gemini model used (e.g., gemini-2.0-flash-exp)")
    input_tokens: int = Field(..., description="Number of input tokens used")
    output_tokens: int = Field(..., description="Number of output tokens generated")
    total_tokens: int = Field(..., description="Total tokens (input + output)")
    input_cost_usd: float = Field(..., description="Cost for input tokens in USD")
    output_cost_usd: float = Field(..., description="Cost for output tokens in USD")
    total_cost_usd: float = Field(..., description="Total cost in USD")
    is_free_tier: bool = Field(False, description="Whether this used free tier quota")


class ExtractionMetadata(BaseModel):
    source_filename: str
    extraction_date: date
    dealer_id: str = Field(..., description="From filename pattern dealer_XX")
    pdf_date: date = Field(..., description="From filename pattern YYYY-MM-DD")
    brand_folder: str = Field(..., description="From folder structure")
    year_folder: int = Field(..., description="From folder structure")
    pdf_size_kb: Optional[float] = None
    api_usage: Optional[APIUsageStats] = Field(None, description="API usage and cost tracking")


class SGCarMartPriceListExtraction(BaseModel):
    metadata: ExtractionMetadata
    pricelist: PriceListDocument
    extraction_confidence: Optional[Literal["high", "medium", "low"]] = Field(
        None,
        description="Confidence level of extraction accuracy"
    )
    extraction_notes: List[str] = Field(
        default_factory=list,
        description="Any issues or special notes during extraction"
    )
