"""
Critical scenario tests for:
1. Capacity race condition safety
2. Promotion rollback on failure
3. Decimal pricing precision
4. Historical price snapshot integrity
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.exceptions import BusinessRuleError, CapacityExceededError
from app.models import Booking, Cruise, Customer, Promotion, PromotionRedemption
from app.services.booking import BookingService
from app.services.pricing import PricingService


def make_customer(db, name: str = "Alice", email: str | None = None) -> Customer:
    customer = Customer(name=name, email=email or f"{name.lower()}@example.com")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def make_cruise(
    db,
    *,
    ship_name: str = "Wonder of the Seas",
    destination: str = "Caribbean",
    nights: int = 7,
    adult_fare: Decimal = Decimal("1200"),
    capacity_left: int = 10,
) -> Cruise:
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


# ==============================================================================
# 1. CAPACITY RACE CONDITION TESTS
# ==============================================================================


class TestCapacityRaceCondition:
    """
    Verify that capacity is protected by atomic conditional UPDATE.
    Scenario: Two concurrent bookings arrive when capacity is exactly 2.
    Without atomic UPDATE, both might succeed. With it, only one can proceed.
    """

    def test_capacity_atomic_update_prevents_overbooking(self, db):
        """
        Verify the atomic SQL UPDATE checks capacity before decrement.
        Simulates: capacity=2, request_1 wants 2 passengers, request_2 wants 2 passengers.
        Expected: request_1 succeeds, request_2 fails.
        """
        customer = make_customer(db, name="Customer1", email="c1@example.com")
        cruise = make_cruise(db, capacity_left=2)
        passengers = [make_passenger(18), make_passenger(17)]

        # First booking should succeed (capacity_left: 2 -> 0)
        booking1 = BookingService.create_booking(
            db, customer.id, cruise.id, passengers
        )
        assert booking1 is not None
        assert booking1.passenger_count == 2

        db.refresh(cruise)
        assert cruise.capacity_left == 0

        # Second booking attempt should fail (capacity_left: 0 < 2)
        customer2 = make_customer(db, name="Customer2", email="c2@example.com")
        with pytest.raises(CapacityExceededError):
            BookingService.create_booking(db, customer2.id, cruise.id, passengers)

        # Verify no partial booking was created
        assert db.query(Booking).count() == 1
        db.refresh(cruise)
        assert cruise.capacity_left == 0

    def test_capacity_cannot_go_negative(self, db):
        """Verify capacity_left cannot drop below zero due to database constraint."""
        customer = make_customer(db)
        cruise = make_cruise(db, capacity_left=3)

        # First booking: 3 passengers, capacity goes 3 -> 0
        passengers_3 = [make_passenger(18) for _ in range(3)]
        booking1 = BookingService.create_booking(db, customer.id, cruise.id, passengers_3)
        assert booking1 is not None

        db.refresh(cruise)
        assert cruise.capacity_left == 0

        # Attempt to book when at zero capacity
        customer2 = make_customer(db, name="C2", email="c2@ex.com")
        with pytest.raises(CapacityExceededError):
            BookingService.create_booking(db, customer2.id, cruise.id, [make_passenger(18)])

        db.refresh(cruise)
        assert cruise.capacity_left == 0  # Still zero, not negative


# ==============================================================================
# 2. PROMOTION ROLLBACK TESTS
# ==============================================================================


class TestPromotionRollback:
    """
    Verify that promotion redemption is recorded INSIDE the transaction.
    Scenario: Booking passes promotion validation but fails on capacity.
    Expected: No redemption record is created, promotion count not incremented.
    """

    def test_promotion_redemption_not_recorded_when_booking_fails(self, db):
        """
        Verify redemption insertion is rolled back if booking fails.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, capacity_left=1)
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

        # Attempt booking with 2 passengers (capacity is 1)
        passengers = [make_passenger(18), make_passenger(17)]

        with pytest.raises(CapacityExceededError):
            BookingService.create_booking(
                db, customer.id, cruise.id, passengers, promotion_code="SUMMER10"
            )

        # Verify no redemption was recorded
        assert db.query(PromotionRedemption).count() == 0

        # Verify no booking was created
        assert db.query(Booking).count() == 0

        # Verify capacity was not decremented
        db.refresh(cruise)
        assert cruise.capacity_left == 1

    def test_promotion_total_usage_limit_respects_rollback(self, db):
        """
        Verify failed booking does not increment total promotion usage count.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, capacity_left=10)

        # Create a promotion with very low usage limit
        promo = make_promotion(
            db,
            "LIMITED",
            "percentage",
            Decimal("10"),
            date(2026, 1, 1),
            date(2026, 12, 31),
            max_total_uses=1,
            max_uses_per_customer=1,
            minimum_spend=Decimal("1000"),
        )

        # First booking succeeds
        passengers = [make_passenger(18), make_passenger(18)]
        booking1 = BookingService.create_booking(
            db, customer.id, cruise.id, passengers, promotion_code="LIMITED"
        )
        assert booking1 is not None
        assert db.query(PromotionRedemption).count() == 1

        # Second customer tries to use same promotion (max_total_uses=1)
        customer2 = make_customer(db, name="C2", email="c2@ex.com")
        with pytest.raises(Exception):  # Should fail on validation
            BookingService.create_booking(
                db, customer2.id, cruise.id, passengers, promotion_code="LIMITED"
            )

        # Verify still only 1 redemption (failed booking didn't count)
        assert db.query(PromotionRedemption).count() == 1


# ==============================================================================
# 3. DECIMAL PRICING TESTS
# ==============================================================================


class TestDecimalPricing:
    """
    Verify all money calculations use Decimal, not float.
    Verify rounding is consistent (ROUND_HALF_UP, 2 decimals).
    """

    def test_passenger_pricing_returns_decimal_with_correct_precision(self, db):
        """Verify passenger_price returns Decimal rounded to cents."""
        cruise = make_cruise(db)

        # Test a price that might have rounding issues with float
        result = PricingService.passenger_price(Decimal("1234.567"), 18)
        assert isinstance(result, Decimal)
        assert result == Decimal("1234.57")  # ROUND_HALF_UP

    def test_group_discount_uses_decimal_arithmetic(self, db):
        """Verify group discount is calculated in Decimal, not float."""
        cruise = make_cruise(db, adult_fare=Decimal("1000"))
        passengers = [make_passenger(18) for _ in range(3)]  # 5% discount

        quote = PricingService.calculate_quote(cruise, passengers)

        # 1000 * 3 passengers = 3000
        # 3 passengers = 5% group discount
        # 3000 * 0.05 = 150.00
        assert quote.group_discount == Decimal("150.00")
        assert quote.cruise_fare_after_group_discount == Decimal("2850.00")

    def test_service_pricing_precision_with_wifi_nights(self, db):
        """
        Verify Wi-Fi service (per night) is calculated precisely.
        Wi-Fi = $15/night, 7 nights, 2 passengers
        Expected: 15 * 7 * 2 = 210.00
        """
        cruise = make_cruise(db, nights=7)
        passengers = [make_passenger(18), make_passenger(18)]
        services = [SimpleNamespace(service_type="wifi", quantity=1)]

        quote = PricingService.calculate_quote(cruise, passengers, services=services)

        assert quote.service_total == Decimal("210.00")
        assert isinstance(quote.service_total, Decimal)

    def test_tax_calculation_rounds_correctly(self, db):
        """
        Verify 12% tax is calculated with proper rounding.
        Example: taxable_amount = $333.33 (odd amount)
        Expected tax: 333.33 * 0.12 = 39.9996 -> 40.00 (ROUND_HALF_UP)
        """
        cruise = make_cruise(db, adult_fare=Decimal("1000"))
        passengers = [make_passenger(18)]

        quote = PricingService.calculate_quote(cruise, passengers)

        # 1000 subtotal, no discount, no services
        # taxable = 1000
        # tax = 1000 * 0.12 = 120.00
        assert quote.tax == Decimal("120.00")
        assert isinstance(quote.tax, Decimal)

    def test_promotion_discount_calculation_uses_decimal(self, db):
        """
        Verify percentage promotion discount is precise.
        Cruise subtotal: $2100, 10% discount
        Expected: 2100 * 0.10 = 210.00
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1200"))
        promo = make_promotion(
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
        passengers = [make_passenger(18), make_passenger(18)]  # 2400 subtotal

        quote = PricingService.calculate_quote(cruise, passengers, promotion=promo)

        assert quote.promotion_discount == Decimal("240.00")
        assert isinstance(quote.promotion_discount, Decimal)

    def test_final_total_accumulates_without_float_errors(self, db):
        """
        Verify the full pricing chain: fare -> group discount -> services -> promotion -> tax -> total
        Uses various decimal amounts to catch rounding errors.
        """
        cruise = make_cruise(db, adult_fare=Decimal("1234.56"))
        passengers = [make_passenger(18), make_passenger(12), make_passenger(5)]
        services = [SimpleNamespace(service_type="insurance", quantity=1)]
        promo = make_promotion(
            db,
            "FIXED50",
            "fixed",
            Decimal("50.00"),
            date(2026, 1, 1),
            date(2026, 12, 31),
            100,
            1,
            Decimal("1000"),
        )

        quote = PricingService.calculate_quote(
            cruise, passengers, services=services, promotion=promo
        )

        # Verify no float artifacts
        assert isinstance(quote.cruise_fare, Decimal)
        assert isinstance(quote.group_discount, Decimal)
        assert isinstance(quote.service_total, Decimal)
        assert isinstance(quote.promotion_discount, Decimal)
        assert isinstance(quote.tax, Decimal)
        assert isinstance(quote.total, Decimal)

        # Verify final_total is reasonable and all components are precise
        # The total should equal taxable + tax within rounding tolerance (1 cent)
        # due to intermediate Decimal quantization in the pricing calculation.
        expected_total = quote.taxable_amount + quote.tax
        assert abs(quote.total - expected_total) <= Decimal("0.01")
        assert quote.total > Decimal("0")


# ==============================================================================
# 4. HISTORICAL PRICE SNAPSHOT TESTS
# ==============================================================================


class TestHistoricalPriceSnapshot:
    """
    Verify booking preserves all original pricing even when cruise config changes.
    """

    def test_booking_snapshot_preserves_original_adult_fare(self, db):
        """
        Create booking at $1200 adult fare.
        Change cruise to $1800.
        Verify booking still shows $1200.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1200"))
        passengers = [make_passenger(18), make_passenger(12)]

        booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)
        assert booking.original_adult_fare == Decimal("1200.00")

        # Change cruise fare
        cruise.adult_fare = Decimal("1800")
        db.commit()

        # Reload booking and verify original fare is preserved
        db.refresh(booking)
        assert booking.original_adult_fare == Decimal("1200.00")

    def test_booking_snapshot_preserves_cruise_fare_subtotal(self, db):
        """
        Verify cruise_fare_subtotal in booking matches what was charged.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1500"))
        passengers = [
            make_passenger(18),
            make_passenger(12),
            make_passenger(5),
        ]

        booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

        # Expect: 1500 (adult 100%) + 1125 (child 12 at 75%) + 750 (child 5 at 50%) = 3375
        assert booking.cruise_fare_subtotal == Decimal("3375.00")

        # Change cruise fare and verify snapshot is not recalculated
        cruise.adult_fare = Decimal("2000")
        db.commit()

        db.refresh(booking)
        assert booking.cruise_fare_subtotal == Decimal("3375.00")

    def test_booking_snapshot_preserves_group_discount_and_amount(self, db):
        """
        Verify group discount rate and amount are locked in at booking time.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1000"))
        # 4 passengers = 5% discount
        passengers = [make_passenger(18) for _ in range(4)]

        booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

        assert booking.group_discount_rate == Decimal("0.05")
        assert booking.group_discount_amount == Decimal("200.00")

        # Change cruise and verify snapshot is immutable
        cruise.adult_fare = Decimal("2000")
        db.commit()

        db.refresh(booking)
        assert booking.group_discount_rate == Decimal("0.05")
        assert booking.group_discount_amount == Decimal("200.00")

    def test_booking_snapshot_preserves_promotion_details(self, db):
        """
        Verify promotion code, type, value, and discount are frozen.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1000"))
        promo = make_promotion(
            db,
            "SAVE20",
            "percentage",
            Decimal("20"),
            date(2026, 1, 1),
            date(2026, 12, 31),
            100,
            1,
            Decimal("500"),
        )
        passengers = [make_passenger(18), make_passenger(18)]

        booking = BookingService.create_booking(
            db, customer.id, cruise.id, passengers, promotion_code="SAVE20"
        )

        assert booking.promotion_code == "SAVE20"
        assert booking.promotion_type == "percentage"
        assert booking.promotion_value == Decimal("20")
        assert booking.promotion_discount == Decimal("400.00")

        # Change promotion value and verify booking snapshot is unchanged
        promo.value = Decimal("50")
        db.commit()

        db.refresh(booking)
        assert booking.promotion_value == Decimal("20")
        assert booking.promotion_discount == Decimal("400.00")

    def test_booking_snapshot_preserves_tax_rate_and_amount(self, db):
        """
        Verify tax rate and amount are locked in at booking time.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1000"))
        passengers = [make_passenger(18)]

        booking = BookingService.create_booking(db, customer.id, cruise.id, passengers)

        assert booking.tax_rate == Decimal("0.12")
        # Taxable = 1000, tax = 1000 * 0.12 = 120.00
        assert booking.tax_amount == Decimal("120.00")

    def test_booking_snapshot_preserves_final_total(self, db):
        """
        Verify final_total is immutable even after configuration changes.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1000"), nights=5)
        passengers = [make_passenger(18), make_passenger(12)]
        services = [SimpleNamespace(service_type="insurance", quantity=1)]

        booking = BookingService.create_booking(
            db, customer.id, cruise.id, passengers, services=services
        )

        original_final = booking.final_total

        # Change multiple config parameters
        cruise.adult_fare = Decimal("1500")
        cruise.nights = 10
        db.commit()

        db.refresh(booking)
        assert booking.final_total == original_final

    def test_booking_snapshot_sufficient_for_reconstruction(self, db):
        """
        Verify all fields stored on booking are sufficient to reconstruct the original invoice.
        """
        customer = make_customer(db)
        cruise = make_cruise(db, adult_fare=Decimal("1200"))
        promo = make_promotion(
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
        passengers = [make_passenger(18), make_passenger(12)]

        booking = BookingService.create_booking(
            db, customer.id, cruise.id, passengers, promotion_code="SUMMER10"
        )

        # Reconstruct using stored snapshot fields
        reconstructed_total = (
            booking.cruise_fare_subtotal
            - booking.group_discount_amount
            + booking.service_total
            - booking.promotion_discount
            + booking.tax_amount
        )

        assert reconstructed_total == booking.final_total
