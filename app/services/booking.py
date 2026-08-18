from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.exceptions import BusinessRuleError, CapacityExceededError, PromotionValidationError
from app.models import Booking, Cruise, Customer, Passenger, PromotionRedemption, Service
from app.services.pricing import PricingService
from app.services.promotion import PromotionService


class BookingService:
    @staticmethod
    def validate_passengers(passengers: list[object]):
        if not passengers:
            raise BusinessRuleError("INVALID_BOOKING", "At least one passenger is required.")
        if len(passengers) > 6:
            raise BusinessRuleError("PASSENGER_LIMIT_EXCEEDED", "A booking cannot include more than 6 passengers.")

        for passenger in passengers:
            age = getattr(passenger, "age", None)
            if age is None or not isinstance(age, int) or age < 0 or age > 120:
                raise BusinessRuleError("INVALID_PASSENGER_AGE", "Passenger age must be between 0 and 120.")

        adult_count = sum(1 for passenger in passengers if getattr(passenger, "age", 0) >= 18)
        if adult_count < 1:
            raise BusinessRuleError("INVALID_BOOKING", "At least one adult is required.")

    @staticmethod
    def quote(db: Session, customer_id: int, cruise_id: int, passengers: list[object], services: list[object] | None = None, promotion_code: str | None = None):
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer is None:
            raise BusinessRuleError("CUSTOMER_NOT_FOUND", f"Customer {customer_id} was not found.")

        cruise = db.query(Cruise).filter(Cruise.id == cruise_id).first()
        if cruise is None:
            raise BusinessRuleError("CRUISE_NOT_FOUND", f"Cruise {cruise_id} was not found.")

        BookingService.validate_passengers(passengers)
        promotion = None
        if promotion_code:
            pre_tax_total = Decimal("0")
            # This pricing quote is using the same pricing engine as booking, excluding tax and promotion.
            passenger_fares = []
            for passenger in passengers:
                age = getattr(passenger, "age", 0)
                passenger_fares.append(PricingService.passenger_price(cruise.adult_fare, age))
            cruise_subtotal = sum(passenger_fares, Decimal("0"))
            group_discount_rate = PricingService.group_discount_rate(len(passengers))
            group_discount_amount = PricingService.money(cruise_subtotal * group_discount_rate)
            cruise_after_group = PricingService.money(cruise_subtotal - group_discount_amount)
            service_total = PricingService.calculate_service_total(cruise, services or [], len(passengers))
            pre_tax_total = cruise_after_group + service_total
            promotion = PromotionService.validate_promotion(db, customer_id, promotion_code, pre_tax_total)

        quote = PricingService.calculate_quote(cruise, passengers, services or [], promotion)
        return {
            "customer_id": customer_id,
            "cruise_id": cruise_id,
            "passenger_count": len(passengers),
            "adults": sum(1 for p in passengers if getattr(p, "age", 0) >= 18),
            "children": sum(1 for p in passengers if getattr(p, "age", 0) < 18),
            "quote_summary": {
                "cruise_fare_subtotal": quote["cruise_fare_subtotal"],
                "group_discount_rate": quote["group_discount_rate"],
                "group_discount_amount": quote["group_discount"],
                "cruise_fare_after_group_discount": quote["cruise_fare_after_group_discount"],
                "service_total": quote["service_total"],
                "promotion_discount": quote["promotion_discount"],
                "taxable_amount": quote["taxable_amount"],
                "tax_rate": quote["tax_rate"],
                "tax_amount": quote["tax"],
                "final_total": quote["total"],
                "currency": "USD",
            },
            "passengers": quote["passengers"],
            "services": [
                {
                    "service_type": service.service_type,
                    "quantity": service.quantity,
                    "unit_price": PricingService.calculate_service_total(
                        cruise,
                        [service],
                        len(passengers),
                    ) / Decimal(str(service.quantity)),
                    "total_price": PricingService.calculate_service_total(
                        cruise,
                        [service],
                        len(passengers),
                    ),
                }
                for service in (services or [])
            ],
            "promotion_code": promotion_code,
        }

    @staticmethod
    def create_booking(db: Session, customer_id: int, cruise_id: int, passengers: list[object], services: list[object] | None = None, promotion_code: str | None = None):
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer is None:
            raise BusinessRuleError("CUSTOMER_NOT_FOUND", f"Customer {customer_id} was not found.")

        cruise = db.query(Cruise).filter(Cruise.id == cruise_id).first()
        if cruise is None:
            raise BusinessRuleError("CRUISE_NOT_FOUND", f"Cruise {cruise_id} was not found.")

        BookingService.validate_passengers(passengers)

        services = services or []
        quote_total_before_promo = Decimal("0")
        passenger_prices = []
        for passenger in passengers:
            age = getattr(passenger, "age", 0)
            unit_price = PricingService.passenger_price(cruise.adult_fare, age)
            passenger_prices.append(unit_price)
        cruise_subtotal = sum(passenger_prices, Decimal("0"))
        group_discount_rate = PricingService.group_discount_rate(len(passengers))
        group_discount_amount = PricingService.money(cruise_subtotal * group_discount_rate)
        cruise_after_group = PricingService.money(cruise_subtotal - group_discount_amount)
        service_total = PricingService.calculate_service_total(cruise, services, len(passengers))
        quote_total_before_promo = cruise_after_group + service_total

        promotion = None
        if promotion_code:
            promotion = PromotionService.validate_promotion(db, customer_id, promotion_code, quote_total_before_promo)

        quote = PricingService.calculate_quote(cruise, passengers, services, promotion)

        with db.begin_nested():
            # FIX: Use an atomic conditional UPDATE so concurrent bookings
            # cannot both reserve the same remaining capacity. The database
            # ensures only one succeeds when capacity_left >= requested passengers.
            update_result = db.execute(
                text(
                    """
                    UPDATE cruises
                    SET capacity_left = capacity_left - :passenger_count
                    WHERE id = :cruise_id AND capacity_left >= :passenger_count
                    """
                ),
                {"passenger_count": len(passengers), "cruise_id": cruise_id},
            )
            if update_result.rowcount != 1:
                raise CapacityExceededError("Cruise capacity is insufficient for this booking.")

            booking_reference = f"CR-{uuid.uuid4().hex[:8].upper()}"
            # FIX: Store complete historical price snapshot at booking time.
            # All pricing components (fares, discounts, taxes, totals) are
            # captured from the quote and persisted with the booking. This
            # creates an immutable audit trail that survives future price changes.
            booking = Booking(
                booking_reference=booking_reference,
                customer_id=customer_id,
                cruise_id=cruise_id,
                status="confirmed",
                passenger_count=len(passengers),
                adult_count=sum(1 for p in passengers if getattr(p, "age", 0) >= 18),
                child_count=sum(1 for p in passengers if getattr(p, "age", 0) < 18),
                cruise_fare_subtotal=quote.cruise_fare_subtotal,
                group_discount_rate=quote.group_discount_rate,
                group_discount_amount=quote.group_discount,
                cruise_fare_after_group_discount=quote.cruise_fare_after_group_discount,
                service_total=quote.service_total,
                promotion_code=promotion.code if promotion else None,
                promotion_type=promotion.promo_type if promotion else None,
                promotion_value=promotion.value if promotion else None,
                promotion_discount=quote.promotion_discount,
                taxable_amount=quote.taxable_amount,
                tax_rate=quote.tax_rate,
                tax_amount=quote.tax,
                final_total=quote.total,
                original_adult_fare=cruise.adult_fare,
            )
            db.add(booking)
            db.flush()

            for passenger in passengers:
                age = getattr(passenger, "age", 0)
                passenger_record = Passenger(
                    booking_id=booking.id,
                    first_name=getattr(passenger, "first_name", ""),
                    last_name=getattr(passenger, "last_name", ""),
                    age=age,
                    passenger_type="adult" if age >= 18 else "child",
                    unit_price=PricingService.passenger_price(cruise.adult_fare, age),
                )
                db.add(passenger_record)

            for service in services:
                service_type = getattr(service, "service_type", None)
                quantity = getattr(service, "quantity", 1)
                unit_price = Decimal("0")
                if service_type == "insurance":
                    unit_price = Decimal("80")
                elif service_type == "wifi":
                    unit_price = Decimal("15") * Decimal(str(cruise.nights))
                elif service_type == "shore_excursion":
                    unit_price = Decimal("120")
                total_price = unit_price * Decimal(str(quantity))
                db.add(
                    Service(
                        booking_id=booking.id,
                        service_type=service_type,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total_price,
                    )
                )

            if promotion:
                # FIX: Redemption is created inside the booking transaction.
                # If the booking fails (e.g., capacity exhausted), the entire
                # transaction rolls back, leaving the promotion unused.
                db.add(
                    PromotionRedemption(
                        promotion_id=promotion.id,
                        customer_id=customer_id,
                        booking_id=booking.id,
                    )
                )

        return booking
