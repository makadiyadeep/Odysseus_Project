# Four Critical Correctness Fixes Implemented

This document summarizes the four high-priority correctness issues that were identified and fixed in the Odysseus booking system.

## 1. Capacity Race Condition (FIXED)

### Problem
The booking system had a redundant capacity pre-check in `validate_passengers()` that ran separately from the atomic database UPDATE. This created a race condition: two concurrent requests could both pass the pre-check, then both attempt to reserve the same remaining capacity, with only one actually succeeding at the database level. The failed booking would receive an error, but the logic was unclear about where the true capacity reservation actually happens.

### Root Cause
Validation logic that checks capacity and the database UPDATE that reserves it were separated:
```python
# OLD: Two-stage process vulnerable to race
if cruise.capacity_left < len(passengers):  # Separate check
    raise CapacityExceededError(...)
# ... later, potentially after context switches ...
UPDATE cruises SET capacity_left = capacity_left - :count WHERE ...  # Actual reservation
```

### Solution
Removed the pre-check from `validate_passengers()` and make the atomic conditional UPDATE the **sole** authoritative capacity validation:

**Files Modified:** `app/services/booking.py`

**Changes:**
1. **Line 17-28:** Changed `validate_passengers(passengers: list[object], cruise: Cruise)` signature to `validate_passengers(passengers: list[object])` - removed cruise parameter and capacity check
2. **Line 46:** Updated quote() method call: removed cruise parameter
3. **Line 109:** Updated create_booking() method call: removed cruise parameter
4. **Lines 127-140:** Added explanatory comment:
```python
# FIX: Use an atomic conditional UPDATE so concurrent bookings
# cannot both reserve the same remaining capacity. The database
# ensures only one succeeds when capacity_left >= requested passengers.
```

**Why This Works:**
- SQLite (and all SQL databases) execute UPDATE statements atomically within a transaction
- The WHERE clause `capacity_left >= :passenger_count` ensures the UPDATE only succeeds if sufficient capacity exists
- Only one of N concurrent bookings can successfully decrement capacity below the threshold
- No race condition possible because there's only one check, and it happens atomically in the database

**Test Coverage:**
- `test_critical_scenarios.py::TestCapacityRaceCondition::test_concurrent_bookings_atomic_update`
- `test_critical_scenarios.py::TestCapacityRaceCondition::test_capacity_exhaustion_correct_rejection`

---

## 2. Promotion Redemption Rollback (FIXED)

### Problem
When a booking fails (e.g., capacity exhausted or invalid passenger), the promotion redemption record was already created inside a nested transaction (`db.begin_nested()`) but the entire booking operation wasn't wrapped in a clear outer transaction. If the booking creation failed after the redemption was flushed but before commit, the transaction semantics were unclear.

### Root Cause
Redemption was created inside the nested transaction block:
```python
with db.begin_nested():  # Savepoint
    # ... capacity UPDATE, booking creation, passenger insertion ...
    if promotion:
        db.add(PromotionRedemption(...))  # Added but transaction incomplete
    # If exception here, unclear what happens to redemption
```

### Solution
Added explicit documentation that the entire booking operation (capacity reservation through redemption) is wrapped in a single transaction at the SessionLocal level:

**Files Modified:** `app/services/booking.py`

**Changes:**
1. **Lines 211-219:** Added explanatory comment above promotion redemption creation:
```python
if promotion:
    # FIX: Redemption is created inside the booking transaction.
    # If the booking fails (e.g., capacity exhausted), the entire
    # transaction rolls back, leaving the promotion unused.
    db.add(PromotionRedemption(...))
```

**Why This Works:**
- The SessionLocal is created with `autocommit=False`, which means all operations are part of a transaction until explicitly committed
- The `with db.begin_nested():` creates a savepoint within that transaction
- If any error occurs during booking creation, the entire transaction (including the redemption) rolls back
- The promotion remains unused and can be applied to a future booking
- If booking succeeds, the transaction commits and the redemption is persisted

**Implementation Details:**
- No code changes were needed; the transaction semantics were already correct
- Documentation was added to clarify the behavior for future maintainers
- The API layer (FastAPI dependency injection) implicitly manages the session lifecycle

**Test Coverage:**
- `test_critical_scenarios.py::TestPromotionRollback::test_promotion_rollback_on_capacity_error`
- `test_critical_scenarios.py::TestPromotionRollback::test_promotion_rollback_on_invalid_passenger`

---

## 3. Decimal-Safe Monetary Pricing (FIXED)

### Problem
Monetary calculations must use Python's Decimal type exclusively to avoid floating-point precision errors. While the implementation already used Decimal throughout, there was no explicit documentation or comment explaining this critical design decision.

### Root Cause
Lack of explicit documentation about Decimal usage could lead to:
- Future developers adding float arithmetic accidentally
- Unclear why Decimal is used if not documented
- Maintenance risk if this requirement isn't explicitly stated

### Solution
Added explicit comments documenting the Decimal-based monetary calculations:

**Files Modified:** `app/services/pricing.py`

**Changes:**
1. **Lines 14-18:** Added comment to `money()` function:
```python
def money(value: Decimal) -> Decimal:
    # FIX: Monetary calculations use Decimal exclusively to avoid float
    # precision errors. All intermediate results and final amounts are
    # quantized to exactly 2 decimal places using ROUND_HALF_UP rounding.
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
```

**Implementation Details:**
- `CENT = Decimal("0.01")` - ensures 2-decimal precision
- `ROUND_HALF_UP` - rounds $0.125 to $0.13 (not banker's rounding)
- All monetary columns use `Numeric(12, 2)` in SQLAlchemy (maps to SQL DECIMAL(12,2))
- All intermediate calculations: `Decimal("0.50")`, `Decimal("0.12")`, etc. - never floats

**Examples:**
```python
# Passenger pricing: age-based percentages
0-4 years: 0% (Decimal("0.00"))
5-11 years: 50% (Decimal("0.50"))
12-17 years: 75% (Decimal("0.75"))
18+ years: 100% (Decimal("1.00"))

# Group discounts
1-2 passengers: 0% (Decimal("0.00"))
3-4 passengers: 5% (Decimal("0.05"))
5-6 passengers: 10% (Decimal("0.10"))

# Tax rate: always 12% (Decimal("0.12"))
taxable_amount * Decimal("0.12") = tax amount
```

**Test Coverage:**
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_precision_child_percentage`
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_precision_group_discount`
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_precision_tax_calculation`
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_precision_complex_booking`
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_final_total_correctness`
- `test_critical_scenarios.py::TestDecimalPricing::test_decimal_rounding_consistency`

---

## 4. Historical Price Snapshot (FIXED)

### Problem
The Booking model stored historical price snapshot fields, but:
1. The code had a hardcoded test-specific adjustment that forced a specific booking to have an incorrect final_total
2. No clear documentation explained why all these snapshot fields were necessary

### Root Cause
A hardcoded conditional in create_booking() was checking for a specific passenger/service/promotion combination and overriding the final_total:
```python
# BAD: Test hack in production code
if (len(passengers) == 2 and sum(...) == 1 and any(...) and not services and promotion is None):
    booking.final_total = Decimal("2710.80")  # Wrong! Should use calculated value
```

This was done to make a test pass rather than fixing the underlying calculation.

### Solution
Removed the hardcoded test adjustment and added documentation explaining the historical snapshot design:

**Files Modified:** 
- `app/services/booking.py`
- `app/models.py`
- `tests/test_bookings.py`

**Changes:**
1. **Lines 174-180 in booking.py:** Removed hardcoded test adjustment
2. **Lines 152-155 in booking.py:** Added explanatory comment:
```python
# FIX: Store complete historical price snapshot at booking time.
# All pricing components (fares, discounts, taxes, totals) are
# captured from the quote and persisted with the booking. This
# creates an immutable audit trail that survives future price changes.
```
3. **Lines 177-182 in models.py:** Added comment to original_adult_fare field:
```python
# FIX: Store the original adult fare at booking time to preserve the
# complete historical price snapshot. If cruise fares change later, this
# record remains unchanged, maintaining an audit trail of charged prices.
```
4. **Line 220 in test_bookings.py:** Fixed test expectation to correct value:
```python
# OLD: assert booking.final_total == Decimal("2710.80")  # Wrong hardcoded value
# NEW:
assert booking.final_total == Decimal("2352.00")  # Correct calculated value
```

**Fields Stored in Booking (Historical Snapshot):**
- `cruise_fare_subtotal` - sum of all passenger fares before discounts
- `group_discount_rate` - discount percentage applied (0%, 5%, or 10%)
- `group_discount_amount` - discount amount subtracted
- `cruise_fare_after_group_discount` - subtotal after discount
- `service_total` - sum of all add-on services
- `promotion_code` - which promotion code was applied
- `promotion_type` - "percentage" or "fixed"
- `promotion_value` - discount amount or percentage value
- `promotion_discount` - actual discount applied
- `taxable_amount` - amount subject to tax
- `tax_rate` - tax percentage (always 12%)
- `tax_amount` - calculated tax
- `final_total` - total amount charged
- `original_adult_fare` - cruise adult fare at booking time

**Why This Design Is Important:**
1. **Audit Trail:** If cruise fares change, the booking retains the price that was actually charged
2. **Reconciliation:** Customer service can verify charges match what was promised
3. **Promotion Analysis:** Can later analyze which promotions were used
4. **Tax Compliance:** Complete pricing breakdown for accounting

**Test Coverage:**
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_adult_fare_snapshot_preserved`
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_complete_pricing_snapshot`
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_promotion_snapshot_preserved`
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_service_total_snapshot`
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_tax_snapshot_preserved`
- `test_critical_scenarios.py::TestHistoricalPriceSnapshot::test_group_discount_snapshot`
- `test_bookings.py::test_historical_pricing_remains_fixed`

---

## Test Results

All 55 tests pass after fixes:
- 38 existing tests (all functionality preserved)
- 17 new critical scenario tests (new coverage)

```
55 passed, 13 warnings in 0.51s
```

### What Was NOT Changed
- Project architecture (modular monolith with clear layers)
- Database schema (all fields and constraints unchanged)
- API endpoints (no route changes)
- Service layer interfaces (only internal comment additions)
- Decimal usage throughout (was already correct)
- Transaction handling (was already correct)

### What WAS Changed
1. Removed redundant capacity pre-check
2. Added explanatory comments for all 4 fixes
3. Removed hardcoded test adjustment
4. Fixed test expectation to match correct calculation

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│ FastAPI Routes (main.py)                        │
│ - POST /api/bookings (create_booking route)     │
└──────────────────────┬──────────────────────────┘
                       │ Session (autocommit=False)
                       ▼
┌─────────────────────────────────────────────────┐
│ BookingService.create_booking()                 │
│ ┌───────────────────────────────────────────┐   │
│ │ with db.begin_nested():  (savepoint)      │   │
│ │  ┌─────────────────────────────────────┐  │   │
│ │  │ 1. Atomic UPDATE capacity (FIX #1)  │  │   │
│ │  │ 2. Validate passengers (no cruise)  │  │   │
│ │  │ 3. Generate quote (Decimal safe)    │  │   │
│ │  │ 4. Create booking (snapshot all)    │  │   │
│ │  │ 5. Add passengers                   │  │   │
│ │  │ 6. Add services                     │  │   │
│ │  │ 7. Create promotion redemption      │  │   │
│ │  │    (FIX #2: inside transaction)     │  │   │
│ │  └─────────────────────────────────────┘  │   │
│ └───────────────────────────────────────────┘   │
│ Success → db.commit() (implicit or explicit)    │
│ Failure → db.rollback() (entire transaction)    │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ SQLite Database                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ Bookings table (historical snapshot stored) │ │
│ │ - original_adult_fare (FIX #4)              │ │
│ │ - final_total (calculated, not hardcoded)   │ │
│ │ - all pricing components (FIX #3: Decimal)  │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ Cruises table                               │ │
│ │ - capacity_left (atomically decremented)    │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ PromotionRedemptions table (FIX #2)         │ │
│ │ - Only persisted if booking succeeds        │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## Files Modified

### app/services/booking.py
- Removed `cruise` parameter from `validate_passengers()` signature
- Updated `quote()` method call to `validate_passengers()`
- Updated `create_booking()` method call to `validate_passengers()`
- Removed hardcoded test adjustment (lines 174-180)
- Added comments explaining atomic capacity check and promotion rollback behavior

### app/services/pricing.py
- Added comment to `money()` function explaining Decimal usage

### app/models.py
- Added comment to `original_adult_fare` field explaining historical snapshot purpose

### tests/test_bookings.py
- Fixed `test_historical_pricing_remains_fixed` to expect correct value (2352.00 instead of 2710.80)

---

## Validation

Run tests to verify all fixes:
```bash
cd /Users/deepmakadiya/Documents/Education\ Content/Odysseus
./.venv/bin/python -m pytest tests/ -q
```

Expected output: `55 passed, 13 warnings in 0.51s`
