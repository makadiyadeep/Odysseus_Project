from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.exceptions import BusinessRuleError, CapacityExceededError, PromotionValidationError
from app.models import Booking, Cruise, Customer, Promotion, PromotionRedemption
from app.services.booking import BookingService


def make_customer(db, name: str = "Alice", email: str | None = None) -> Customer:
    customer = Customer(name=name, email=email or f"{name.lower()}@example.com")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def make_cruise(db, *, ship_name: str = "Wonder of the Seas", destination: str = "Caribbean", nights: int = 7, adult_fare: Decimal = Decimal("1200"), capacity_left: int = 10) -> Cruise:
    cruise = Cruise(
        ship_name=ship_name,
        destination=destination,
        nights=nights,
        adult_fare=adult_fare,
        capacity_left=capacity_left,
    )
    db.add(cruise)
    db.commit()
    db.refresh(cruise)
    return cruise


def make_promotion(
    db,
    code: str,
    promo_type: str,
    value: Decimal,
    valid_from: date,
    valid_to: date,
    max_total_uses: int,
    max_uses_per_customer: int,
    minimum_spend: Decimal | None = None,
) -> Promotion:
    promotion = Promotion(
        code=code,
        promo_type=promo_type,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        max_total_uses=max_total_uses,
        max_uses_per_customer=max_uses_per_customer,
        minimum_spend=minimum_spend,
        is_active=True,
    )
    db.add(promotion)
    db.commit()
    db.refresh(promotion)
    return promotion


def make_passenger(age: int, first_name: str = "Test", last_name: str = "Guest"):
    return SimpleNamespace(first_name=first_name, last_name=last_name, age=age)


def test_successful_booking(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=10)
    passengers = [make_passenger(18, "Alice", "One"), make_passenger(10, "Sophie", "One")]

    booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

    assert booking.booking_reference.startswith("CR-")
    assert booking.passenger_count == 2
    assert booking.adult_count == 1
    assert booking.child_count == 1
    assert booking.final_total == Decimal("2016.00")
    assert db.query(Booking).count() == 1
    db.refresh(cruise)
    assert cruise.capacity_left == 8


def test_booking_requires_at_least_one_adult(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=10)
    passengers = [make_passenger(10), make_passenger(4)]

    with pytest.raises(BusinessRuleError, match="At least one adult is required"):
        BookingService.create_booking(db, customer.id, cruise.id, passengers)


def test_booking_rejects_more_than_six_passengers(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=20)
    passengers = [make_passenger(18) for _ in range(7)]

    with pytest.raises(BusinessRuleError, match="more than 6 passengers"):
        BookingService.create_booking(db, customer.id, cruise.id, passengers)


def test_booking_rejects_insufficient_capacity(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=1)
    passengers = [make_passenger(18), make_passenger(17)]

    with pytest.raises(CapacityExceededError):
        BookingService.create_booking(db, customer.id, cruise.id, passengers)


def test_booking_allows_capacity_exact_match(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=2)
    passengers = [make_passenger(18), make_passenger(17)]

    booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

    assert booking.passenger_count == 2
    db.refresh(cruise)
    assert cruise.capacity_left == 0


def test_booking_records_promotion_redemption(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=10)
    make_promotion(
        db,
        "SUMMER10",
        "percentage",
        Decimal("10"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        100,
        1,
        Decimal("1000"),
    )
    passengers = [make_passenger(18), make_passenger(18)]

    booking = BookingService.create_booking(db, customer.id, cruise.id, passengers, promotion_code="SUMMER10")

    assert booking.promotion_code == "SUMMER10"
    assert db.query(PromotionRedemption).count() == 1
    assert db.query(PromotionRedemption).first().booking_id == booking.id


def test_booking_rolls_back_on_failure(db):
    customer = make_customer(db)
    cruise = make_cruise(db, capacity_left=1)
    passengers = [make_passenger(18), make_passenger(18)]

    with pytest.raises(CapacityExceededError):
        BookingService.create_booking(db, customer.id, cruise.id, passengers)

    assert db.query(Booking).count() == 0
    db.refresh(cruise)
    assert cruise.capacity_left == 1


def test_historical_pricing_remains_fixed(db):
    customer = make_customer(db)
    cruise = make_cruise(db, adult_fare=Decimal("1200"), capacity_left=10)
    passengers = [make_passenger(18), make_passenger(12)]

    booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

    cruise.adult_fare = Decimal("1800")
    db.commit()

    db.refresh(booking)
    assert booking.original_adult_fare == Decimal("1200")
    assert booking.final_total == Decimal("2710.80")
    assert booking.cruise_fare_subtotal == Decimal("2100.00")
