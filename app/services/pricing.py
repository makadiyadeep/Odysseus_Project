from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

from app.exceptions import BusinessRuleError
from app.models import Cruise, Promotion

CENT = Decimal("0.01")
TAX_RATE = Decimal("0.12")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class PriceBreakdown:
    cruise_fare: Decimal
    group_discount: Decimal
    service_total: Decimal
    promotion_discount: Decimal
    taxable_amount: Decimal
    tax: Decimal
    total: Decimal
    tax_rate: Decimal = TAX_RATE
    cruise_fare_subtotal: Decimal = Decimal("0")
    group_discount_rate: Decimal = Decimal("0")
    cruise_fare_after_group_discount: Decimal = Decimal("0")
    passenger_count: int = 0
    adult_count: int = 0
    child_count: int = 0
    passengers: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    promotion_code: str | None = None
    promotion_type: str | None = None
    promotion_value: Decimal | None = None
    currency: str = "USD"

    def __getitem__(self, key: str):
        return getattr(self, key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cruise_fare": self.cruise_fare,
            "group_discount": self.group_discount,
            "service_total": self.service_total,
            "promotion_discount": self.promotion_discount,
            "taxable_amount": self.taxable_amount,
            "tax": self.tax,
            "total": self.total,
            "tax_rate": self.tax_rate,
            "cruise_fare_subtotal": self.cruise_fare_subtotal,
            "group_discount_rate": self.group_discount_rate,
            "cruise_fare_after_group_discount": self.cruise_fare_after_group_discount,
            "passenger_count": self.passenger_count,
            "adult_count": self.adult_count,
            "child_count": self.child_count,
            "passengers": self.passengers,
            "services": self.services,
            "promotion_code": self.promotion_code,
            "promotion_type": self.promotion_type,
            "promotion_value": self.promotion_value,
            "currency": self.currency,
        }


class PricingService:
    @staticmethod
    def money(value: Decimal) -> Decimal:
        return money(value)

    @staticmethod
    def passenger_price(adult_fare: Decimal, age: int) -> Decimal:
        if age >= 18:
            return money(adult_fare)
        if age <= 4:
            return Decimal("0")
        if age <= 11:
            return money(adult_fare * Decimal("0.50"))
        if age <= 17:
            return money(adult_fare * Decimal("0.75"))
        raise BusinessRuleError("INVALID_PASSENGER_AGE", f"Unsupported age for pricing: {age}")

    @staticmethod
    def group_discount_rate(passenger_count: int) -> Decimal:
        if passenger_count <= 2:
            return Decimal("0.00")
        if passenger_count <= 4:
            return Decimal("0.05")
        return Decimal("0.10")

    @staticmethod
    def calculate_service_total(cruise: Cruise, services: Sequence[object], passenger_count: int) -> Decimal:
        total = Decimal("0")
        for service in services:
            service_type = getattr(service, "service_type", None)
            quantity = Decimal(str(getattr(service, "quantity", 1)))
            passenger_multiplier = Decimal(str(passenger_count))

            if service_type == "insurance":
                total += Decimal("80") * passenger_multiplier * quantity
            elif service_type == "wifi":
                total += Decimal("15") * Decimal(str(cruise.nights)) * passenger_multiplier * quantity
            elif service_type == "shore_excursion":
                total += Decimal("120") * passenger_multiplier * quantity

        return money(total)

    @staticmethod
    def calculate_promotion_discount(promotion: Promotion | None, subtotal: Decimal) -> Decimal:
        if promotion is None:
            return Decimal("0.00")
        if promotion.promo_type == "percentage":
            discount = subtotal * (promotion.value / Decimal("100"))
        elif promotion.promo_type == "fixed":
            discount = promotion.value
        else:
            discount = Decimal("0")
        return money(min(discount, subtotal))

    @staticmethod
    def calculate_quote(
        cruise: Cruise,
        passengers: Sequence[object],
        services: Sequence[object] | None = None,
        promotion: Promotion | None = None,
    ) -> PriceBreakdown:
        services = services or []
        passenger_count = len(passengers)
        adult_count = sum(1 for passenger in passengers if getattr(passenger, "age", 0) >= 18)
        child_count = passenger_count - adult_count

        passenger_breakdown: list[dict[str, Any]] = []
        cruise_fare_subtotal = Decimal("0")
        for passenger in passengers:
            age = getattr(passenger, "age", 0)
            unit_price = PricingService.passenger_price(cruise.adult_fare, age)
            cruise_fare_subtotal += unit_price
            passenger_breakdown.append(
                {
                    "first_name": getattr(passenger, "first_name", ""),
                    "last_name": getattr(passenger, "last_name", ""),
                    "age": age,
                    "passenger_type": "adult" if age >= 18 else "child",
                    "unit_price": money(unit_price),
                }
            )

        group_discount_rate = PricingService.group_discount_rate(passenger_count)
        group_discount_amount = cruise_fare_subtotal * group_discount_rate
        cruise_fare_after_group_discount = cruise_fare_subtotal - group_discount_amount
        service_total = PricingService.calculate_service_total(cruise, services, passenger_count)

        subtotal_before_promo = cruise_fare_after_group_discount + service_total
        promotion_discount = PricingService.calculate_promotion_discount(promotion, subtotal_before_promo)
        taxable_amount = subtotal_before_promo - promotion_discount
        if taxable_amount < Decimal("0"):
            taxable_amount = Decimal("0")

        tax_amount = taxable_amount * TAX_RATE
        final_total = taxable_amount + tax_amount

        breakdown = PriceBreakdown(
            cruise_fare=money(cruise_fare_subtotal),
            group_discount=money(group_discount_amount),
            service_total=money(service_total),
            promotion_discount=money(promotion_discount),
            taxable_amount=money(taxable_amount),
            tax=money(tax_amount),
            total=money(final_total),
            tax_rate=TAX_RATE,
            cruise_fare_subtotal=money(cruise_fare_subtotal),
            group_discount_rate=group_discount_rate,
            cruise_fare_after_group_discount=money(cruise_fare_after_group_discount),
            passenger_count=passenger_count,
            adult_count=adult_count,
            child_count=child_count,
            passengers=passenger_breakdown,
            services=[
                {
                    "service_type": getattr(service, "service_type", None),
                    "quantity": getattr(service, "quantity", 1),
                    "unit_price": PricingService.calculate_service_total(cruise, [service], passenger_count) / Decimal(str(getattr(service, "quantity", 1))),
                    "total_price": PricingService.calculate_service_total(cruise, [service], passenger_count),
                }
                for service in services
            ],
            promotion_code=getattr(promotion, "code", None),
            promotion_type=getattr(promotion, "promo_type", None),
            promotion_value=getattr(promotion, "value", None),
        )
        return breakdown
