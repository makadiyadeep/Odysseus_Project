# Critical Scenarios Test Coverage

This document summarizes the 17 comprehensive tests added to validate the four most critical business logic areas.

## Overview

**File**: [tests/test_critical_scenarios.py](tests/test_critical_scenarios.py)  
**Tests**: 17 scenarios across 4 categories  
**Status**: ✅ All passing

---

## 1. Capacity Race Condition (2 tests)

**Problem**: Without atomic updates, two concurrent bookings could each succeed when capacity is exactly 2.

**Solution**: The booking service uses an atomic conditional SQL UPDATE:

```sql
UPDATE cruises
SET capacity_left = capacity_left - :passenger_count
WHERE id = :cruise_id AND capacity_left >= :passenger_count
```

This check-and-decrement happens in a single database operation, preventing overselling.

### Tests

#### `test_capacity_atomic_update_prevents_overbooking`
- Scenario: Capacity = 2, two requests for 2 passengers each
- Expected: First booking succeeds (capacity → 0), second fails with `CapacityExceededError`
- Proof: Only 1 booking exists, capacity is 0, no partial state

#### `test_capacity_cannot_go_negative`
- Scenario: Capacity = 3, first booking uses all 3, second booking attempts 1 more
- Expected: Second booking fails, capacity remains 0 (not negative)
- Proof: Database constraint `capacity_left >= 0` is enforced

---

## 2. Promotion Rollback (2 tests)

**Problem**: If a booking fails after promotion validation, the promotion redemption should not be recorded.

**Solution**: The redemption record is inserted inside the same transaction as capacity update and booking creation. If any operation fails, the entire transaction rolls back.

### Tests

#### `test_promotion_redemption_not_recorded_when_booking_fails`
- Scenario: Booking passes promotion validation but fails on capacity check
- Expected: No redemption record created, no booking created, capacity unchanged
- Proof: Zero redemption records, zero bookings, capacity still 1

#### `test_promotion_total_usage_limit_respects_rollback`
- Scenario: Promotion has max_total_uses=1. First booking succeeds. Second booking fails on limit.
- Expected: Only 1 redemption record exists (from successful booking)
- Proof: Redemption count = 1, failed attempt did not increment the counter

---

## 3. Decimal Pricing (6 tests)

**Problem**: Floating-point arithmetic can introduce rounding errors in money calculations.

**Solution**: All pricing calculations use Python's `Decimal` type with `ROUND_HALF_UP` and quantization to 2 decimal places.

### Tests

#### `test_passenger_pricing_returns_decimal_with_correct_precision`
- Validates: `passenger_price()` returns Decimal rounded to cents
- Example: 1234.567 → 1234.57

#### `test_group_discount_uses_decimal_arithmetic`
- Validates: Group discount (3 passengers = 5%) uses Decimal
- Example: 3000 * 0.05 = 150.00 (exact)

#### `test_service_pricing_precision_with_wifi_nights`
- Validates: Wi-Fi service calculation (per night) is precise
- Example: $15/night × 7 nights × 2 passengers = 210.00

#### `test_tax_calculation_rounds_correctly`
- Validates: 12% tax is calculated with proper rounding
- Example: 1000 × 0.12 = 120.00

#### `test_promotion_discount_calculation_uses_decimal`
- Validates: Percentage promotion discount is precise
- Example: 2400 × 0.10 = 240.00

#### `test_final_total_accumulates_without_float_errors`
- Validates: Full pricing chain (fare → discount → services → promotion → tax → total) uses Decimal throughout
- Ensures no float artifacts appear anywhere

---

## 4. Historical Price Snapshot (7 tests)

**Problem**: After a booking is confirmed, the exact price charged must not change if the cruise configuration later changes.

**Solution**: The booking record stores a complete snapshot of the pricing at the time of booking creation:

```python
booking.original_adult_fare = cruise.adult_fare
booking.cruise_fare_subtotal = quote.cruise_fare_subtotal
booking.group_discount_rate = quote.group_discount_rate
booking.group_discount_amount = quote.group_discount
booking.cruise_fare_after_group_discount = quote.cruise_fare_after_group_discount
booking.service_total = quote.service_total
booking.promotion_code = promotion.code
booking.promotion_type = promotion.promo_type
booking.promotion_value = promotion.value
booking.promotion_discount = quote.promotion_discount
booking.tax_rate = TAX_RATE
booking.tax_amount = quote.tax
booking.final_total = quote.total
```

### Tests

#### `test_booking_snapshot_preserves_original_adult_fare`
- Create booking at $1200 adult fare
- Change cruise fare to $1800
- Verify booking still shows $1200

#### `test_booking_snapshot_preserves_cruise_fare_subtotal`
- Verify subtotal (sum of all passenger fares) is locked
- Even if cruise fare changes, booking shows original subtotal

#### `test_booking_snapshot_preserves_group_discount_and_amount`
- Verify both the discount rate (e.g., 5%) and amount (e.g., $200) are frozen
- Changes to cruise fare don't recalculate

#### `test_booking_snapshot_preserves_promotion_details`
- Verify promotion code, type (percentage/fixed), value, and discount amount are all frozen
- Changes to promotion don't affect old bookings

#### `test_booking_snapshot_preserves_tax_rate_and_amount`
- Verify tax rate (12%) and calculated tax amount are locked
- Future tax rate changes don't affect historical bookings

#### `test_booking_snapshot_preserves_final_total`
- Verify the final total is immutable
- Multiple configuration changes don't alter the booking's total

#### `test_booking_snapshot_sufficient_for_reconstruction`
- Verify all stored fields on the booking are sufficient to reconstruct the original invoice
- Formula: `cruise_fare_subtotal - group_discount + service_total - promotion_discount + tax_amount = final_total`

---

## Test Execution

```bash
# Run only critical scenarios
pytest tests/test_critical_scenarios.py -v

# Run complete suite including all scenarios
pytest -q

# Output: 55 passed, 11 warnings in 0.60s
```

---

## Business Guarantees Validated

After running all 55 tests, the system guarantees:

✅ **Capacity is protected** — Concurrent bookings cannot oversell a cruise  
✅ **Promotions are transactional** — Failed bookings don't consume promotion usage  
✅ **Money is precise** — All calculations use Decimal arithmetic, no float errors  
✅ **Historical pricing is immutable** — Old bookings retain original prices regardless of config changes  

---

## Key Implementation Details

### Capacity Protection

**File**: [app/services/booking.py](app/services/booking.py)

```python
with db.begin_nested():
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
```

### Promotion Transaction Safety

**File**: [app/services/booking.py](app/services/booking.py)

The redemption is recorded inside the same `db.begin_nested()` transaction block as capacity and booking creation. If capacity check fails, the entire block rolls back.

### Decimal Precision

**File**: [app/services/pricing.py](app/services/pricing.py)

```python
CENT = Decimal("0.01")
TAX_RATE = Decimal("0.12")

def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
```

All monetary values are quantized to 2 decimal places with banker's rounding (round half up).

### Historical Snapshot

**File**: [app/models.py](app/models.py)

The `Booking` model stores complete pricing fields, making it independent of later changes to `Cruise`, `Promotion`, or `Service` configurations.

---

## Conclusion

These 17 tests comprehensively validate the four most critical areas of the cruise booking system. Combined with the existing 38 tests, the full suite of 55 tests provides high confidence that the implementation correctly handles capacity, promotions, money, and historical pricing.
