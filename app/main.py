from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_db_and_tables
from app.exceptions import BusinessRuleError, CapacityExceededError
from app.models import Booking, Cruise, Customer
from app.schemas import (
    BookingCreate,
    CustomerCreate,
    PromotionValidateRequest,
    QuoteRequest,
)
from app.seed import seed_data
from app.services.booking import BookingService
from app.services.promotion import PromotionService

app = FastAPI(title="Cruise Booking System")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _json_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_decimal(item) for item in value]
    return value


@app.exception_handler(BusinessRuleError)
async def business_rule_exception_handler(request, exc: BusinessRuleError):
    status_code = 409 if isinstance(exc, CapacityExceededError) else 400
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.on_event("startup")
def startup_event():
    create_db_and_tables()
    seed_data()


@app.get("/health")
def health_check():
    return {"status": "ok"}


def serialize_cruise(cruise: Cruise):
    return {
        "id": cruise.id,
        "ship_name": cruise.ship_name,
        "destination": cruise.destination,
        "nights": cruise.nights,
        "adult_fare": _json_decimal(cruise.adult_fare),
        "capacity_left": cruise.capacity_left,
    }


def serialize_customer(customer: Customer):
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
    }


def serialize_booking(booking: Booking):
    cruise = booking.cruise
    passengers = [
        {
            "id": passenger.id,
            "first_name": passenger.first_name,
            "last_name": passenger.last_name,
            "age": passenger.age,
            "passenger_type": passenger.passenger_type,
            "unit_price": _json_decimal(passenger.unit_price),
        }
        for passenger in booking.passengers
    ]
    services = [
        {
            "id": service.id,
            "service_type": service.service_type,
            "quantity": service.quantity,
            "unit_price": _json_decimal(service.unit_price),
            "total_price": _json_decimal(service.total_price),
        }
        for service in booking.services
    ]
    return {
        "id": booking.id,
        "booking_reference": booking.booking_reference,
        "customer_id": booking.customer_id,
        "cruise_id": booking.cruise_id,
        "status": booking.status,
        "cruise": serialize_cruise(cruise) if cruise else None,
        "passengers": passengers,
        "services": services,
        "price_breakdown": {
            "cruise_fare_subtotal": _json_decimal(booking.cruise_fare_subtotal),
            "group_discount_rate": _json_decimal(booking.group_discount_rate),
            "group_discount_amount": _json_decimal(booking.group_discount_amount),
            "cruise_fare_after_group_discount": _json_decimal(booking.cruise_fare_after_group_discount),
            "service_total": _json_decimal(booking.service_total),
            "promotion_discount": _json_decimal(booking.promotion_discount),
            "taxable_amount": _json_decimal(booking.taxable_amount),
            "tax_rate": _json_decimal(booking.tax_rate),
            "tax_amount": _json_decimal(booking.tax_amount),
            "final_total": _json_decimal(booking.final_total),
            "currency": "USD",
        },
        "promotion": {
            "code": booking.promotion_code,
            "type": booking.promotion_type,
            "value": _json_decimal(booking.promotion_value) if booking.promotion_value is not None else None,
            "discount_amount": _json_decimal(booking.promotion_discount),
        }
        if booking.promotion_code
        else None,
        "total": _json_decimal(booking.final_total),
    }


@app.get("/api/cruises")
def list_cruises(db: Session = Depends(get_db)):
    cruises = db.query(Cruise).order_by(Cruise.id).all()
    return [serialize_cruise(cruise) for cruise in cruises]


@app.get("/api/cruises/{cruise_id}")
def get_cruise(cruise_id: int, db: Session = Depends(get_db)):
    cruise = db.query(Cruise).filter(Cruise.id == cruise_id).first()
    if cruise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cruise not found.")
    return serialize_cruise(cruise)


@app.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(name=payload.name, email=payload.email)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return serialize_customer(customer)


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return serialize_customer(customer)


@app.post("/api/bookings/quote")
def quote_booking(payload: QuoteRequest, db: Session = Depends(get_db)):
    passengers = [
        SimpleNamespace(
            first_name=passenger.first_name,
            last_name=passenger.last_name,
            age=passenger.age,
        )
        for passenger in payload.passengers
    ]
    services = [
        SimpleNamespace(service_type=item.service_type, quantity=item.quantity)
        for item in payload.services
    ]
    quote = BookingService.quote(
        db,
        payload.customer_id,
        payload.cruise_id,
        passengers,
        services=services,
        promotion_code=payload.promotion_code,
    )
    return _json_decimal(quote)


@app.post("/api/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    passengers = [
        SimpleNamespace(
            first_name=passenger.first_name,
            last_name=passenger.last_name,
            age=passenger.age,
        )
        for passenger in payload.passengers
    ]
    services = [
        SimpleNamespace(service_type=item.service_type, quantity=item.quantity)
        for item in payload.services
    ]
    booking = BookingService.create_booking(
        db,
        payload.customer_id,
        payload.cruise_id,
        passengers,
        services=services,
        promotion_code=payload.promotion_code,
    )
    db.refresh(booking)
    return serialize_booking(booking)


@app.get("/api/bookings/{booking_reference}")
def get_booking(booking_reference: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.booking_reference == booking_reference).first()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    db.refresh(booking)
    return serialize_booking(booking)


@app.post("/api/promotions/validate")
def validate_promotion(payload: PromotionValidateRequest, db: Session = Depends(get_db)):
    promotion = PromotionService.validate_promotion(
        db,
        payload.customer_id,
        payload.code,
        payload.booking_total,
    )
    discount_amount = PromotionService.calculate_discount(promotion, payload.booking_total)
    return {
        "valid": True,
        "code": promotion.code,
        "message": f"Promotion code {promotion.code} is valid.",
        "discount_amount": _json_decimal(discount_amount),
        "discount_type": promotion.promo_type,
        "minimum_spend": _json_decimal(promotion.minimum_spend) if promotion.minimum_spend is not None else None,
    }
