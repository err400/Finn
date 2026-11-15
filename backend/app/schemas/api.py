import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    exchange: str
    name: str
    sector: str
    research_demo: bool

class ResearchRequest(BaseModel):
    workflow: Literal["snapshot", "trajectory", "guidance_vs_actual"] = "snapshot"
    ticker: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str):
        from app.services.normalization import normalize_symbol
        exchange, symbol = normalize_symbol(value)
        return symbol if exchange == "NSE" else symbol + ".BO"

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Question must contain at least three characters")
        return value
