from __future__ import annotations

from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, ConfigDict, field_validator


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class CruiseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ship_name: str
    destination: str
    nights: int
    adult_fare: Decimal
    capacity_left: int


class PassengerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(
        ..., min_length=1, validation_alias=AliasChoices("first_name", "firstName")
    )
    last_name: str = Field(
        ..., min_length=1, validation_alias=AliasChoices("last_name", "lastName")
    )
    age: int = Field(..., ge=0)

    @field_validator("age")
    @classmethod
    def validate_age(cls, value: int) -> int:
        if value > 120:
            raise ValueError("Age cannot exceed 120")
        return value


class ServiceSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    service_type: Literal["insurance", "wifi", "shore_excursion"] = Field(
        ..., validation_alias=AliasChoices("service_type", "serviceType")
    )
    quantity: int = Field(default=1, ge=1)


class QuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cruise_id: int = Field(..., validation_alias=AliasChoices("cruise_id", "cruiseId"))
    customer_id: int = Field(..., validation_alias=AliasChoices("customer_id", "customerId"))
    passengers: List[PassengerRequest] = Field(..., min_length=1, max_length=6)
    services: List[ServiceSelection] = Field(default_factory=list)
    promotion_code: Optional[str] = Field(default=None, validation_alias=AliasChoices("promotion_code", "promotionCode"))

    @field_validator("passengers")
    @classmethod
    def validate_passenger_total(cls, value: List[PassengerRequest]) -> List[PassengerRequest]:
        if len(value) == 0:
            raise ValueError("At least one passenger is required")
        adult_count = sum(1 for p in value if p.age >= 18)
        if adult_count < 1:
            raise ValueError("At least one adult is required")
        return value


class QuotePassengerBreakdown(BaseModel):
    first_name: str
    last_name: str
    age: int
    passenger_type: str
    unit_price: Decimal


class QuoteServiceBreakdown(BaseModel):
    service_type: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class QuoteSummary(BaseModel):
    cruise_fare_subtotal: Decimal
    group_discount_rate: Decimal
    group_discount_amount: Decimal
    cruise_fare_after_group_discount: Decimal
    service_total: Decimal
    promotion_discount: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    final_total: Decimal
    currency: str = "USD"


class QuoteResponse(BaseModel):
    cruise_id: int
    customer_id: int
    passenger_count: int
    adults: int
    children: int
    quote_summary: QuoteSummary
    passengers: List[QuotePassengerBreakdown]
    services: List[QuoteServiceBreakdown]
    promotion_code: Optional[str] = None


class BookingCreate(QuoteRequest):
    pass


class BookingPassengerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    age: int
    passenger_type: str
    unit_price: Decimal


class BookingServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_type: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_reference: str
    customer_id: int
    cruise_id: int
    status: str
    passenger_count: int
    adult_count: int
    child_count: int
    cruise_fare_subtotal: Decimal
    group_discount_rate: Decimal
    group_discount_amount: Decimal
    cruise_fare_after_group_discount: Decimal
    service_total: Decimal
    promotion_code: Optional[str]
    promotion_type: Optional[str]
    promotion_value: Optional[Decimal]
    promotion_discount: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    final_total: Decimal
    original_adult_fare: Decimal
    passengers: List[BookingPassengerRead]
    services: List[BookingServiceRead]
    created_at: str


class PromotionValidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    customer_id: int = Field(..., validation_alias=AliasChoices("customer_id", "customerId"))
    cruise_id: int = Field(..., validation_alias=AliasChoices("cruise_id", "cruiseId"))
    code: str = Field(..., validation_alias=AliasChoices("code", "promoCode"))
    booking_total: Decimal = Field(..., ge=Decimal("0"), validation_alias=AliasChoices("booking_total", "bookingTotal"))


class PromotionValidateResponse(BaseModel):
    valid: bool
    code: str
    message: str
    discount_amount: Decimal = Decimal("0")
    discount_type: Optional[str] = None
    minimum_spend: Optional[Decimal] = None
