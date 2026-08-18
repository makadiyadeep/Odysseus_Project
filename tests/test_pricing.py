from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import Cruise, Promotion
from app.services.pricing import PricingService


def make_cruise(adult_fare: Decimal = Decimal("1200"), nights: int = 7, capacity_left: int = 10):
    return Cruise(
        id=1,
        ship_name="Wonder of the Seas",
        destination="Caribbean",
        nights=nights,
        adult_fare=adult_fare,
        capacity_left=capacity_left,
    )


def make_promotion(
    code: str,
    promo_type: str,
    value: Decimal,
    valid_from: date,
    valid_to: date,
    minimum_spend: Decimal | None = None,
):
    return Promotion(
        id=1,
        code=code,
        promo_type=promo_type,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        max_total_uses=100,
        max_uses_per_customer=1,
        minimum_spend=minimum_spend,
        is_active=True,
    )


def make_passenger(age: int, first_name: str = "Test", last_name: str = "Guest"):
    return SimpleNamespace(first_name=first_name, last_name=last_name, age=age)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, Decimal("0.00")),
        (4, Decimal("0.00")),
        (5, Decimal("600.00")),
        (11, Decimal("600.00")),
        (12, Decimal("900.00")),
        (17, Decimal("900.00")),
        (18, Decimal("1200.00")),
    ],
)
def test_passenger_pricing_by_age(age, expected):
    cruise = make_cruise()
    result = PricingService.passenger_price(cruise.adult_fare, age)
    assert result == expected


def test_mixed_passengers_total():
    cruise = make_cruise(adult_fare=Decimal("1200"))
    passengers = [make_passenger(18), make_passenger(12), make_passenger(5)]

    result = PricingService.calculate_quote(cruise, passengers)

    assert result.cruise_fare == Decimal("2700.00")
    assert result.group_discount == Decimal("135.00")
    assert result.cruise_fare_after_group_discount == Decimal("2565.00")


def test_group_discount_rates_and_boundaries():
    assert PricingService.group_discount_rate(1) == Decimal("0.00")
    assert PricingService.group_discount_rate(2) == Decimal("0.00")
    assert PricingService.group_discount_rate(3) == Decimal("0.05")
    assert PricingService.group_discount_rate(4) == Decimal("0.05")
    assert PricingService.group_discount_rate(5) == Decimal("0.10")
    assert PricingService.group_discount_rate(6) == Decimal("0.10")


def test_services_total():
    cruise = make_cruise(adult_fare=Decimal("1200"), nights=4)
    passengers = [make_passenger(18), make_passenger(18)]
    services = [
        SimpleNamespace(service_type="insurance", quantity=1),
        SimpleNamespace(service_type="wifi", quantity=1),
        SimpleNamespace(service_type="shore_excursion", quantity=1),
    ]

    result = PricingService.calculate_quote(cruise, passengers, services=services)

    assert result.service_total == Decimal("520.00")
    assert result.cruise_fare == Decimal("2400.00")


def test_tax_calculation_sequence():
    cruise = make_cruise(adult_fare=Decimal("1000"), nights=3)
    passengers = [make_passenger(18), make_passenger(12)]
    services = [SimpleNamespace(service_type="wifi", quantity=1)]
    promotion = make_promotion(
        "SUMMER10",
        "percentage",
        Decimal("10"),
        date(2026, 6, 1),
        date(2026, 8, 31),
        Decimal("600"),
    )

    result = PricingService.calculate_quote(cruise, passengers, services=services, promotion=promotion)

    assert result.cruise_fare == Decimal("1750.00")
    assert result.group_discount == Decimal("0.00")
    assert result.service_total == Decimal("90.00")
    assert result.promotion_discount == Decimal("184.00")
    assert result.taxable_amount == Decimal("1656.00")
    assert result.tax == Decimal("198.72")
    assert result.total == Decimal("1854.72")


def test_promotion_discount_is_applied_after_services_and_before_tax():
    cruise = make_cruise(adult_fare=Decimal("2000"), nights=5)
    passengers = [make_passenger(18)]
    services = [SimpleNamespace(service_type="insurance", quantity=1)]
    promotion = make_promotion(
        "FIRST150",
        "fixed",
        Decimal("150"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        Decimal("1500"),
    )

    result = PricingService.calculate_quote(cruise, passengers, services=services, promotion=promotion)

    assert result.cruise_fare == Decimal("2000.00")
    assert result.service_total == Decimal("80.00")
    assert result.promotion_discount == Decimal("150.00")
    assert result.taxable_amount == Decimal("1930.00")
    assert result.tax == Decimal("231.60")
    assert result.total == Decimal("2161.60")
