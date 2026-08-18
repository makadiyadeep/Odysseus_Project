# Unit Test Cases

## 1. Positive cases

### Successful booking creation
- A valid customer and cruise can create a booking with at least one adult passenger.
- A booking creates the expected booking reference and stores booking totals.

### Successful quote generation
- A valid quote can be generated for a cruise with passengers and optional services.
- Quote totals include cruise fare, discount, tax, and final total.

### Customer and cruise retrieval
- API requests can retrieve an existing customer and cruise by id.
- Cruise list endpoint returns available cruises.

## 2. Negative cases

### Promotion threshold and expiry checks
- A promotion is accepted exactly at its minimum spend threshold.
- A future or expired code is rejected before any booking is created.
- A booking that fails after promotion validation does not leave a redemption record behind.

### Missing adult passenger
- A booking with only children is rejected.

### Invalid passenger age
- Ages outside 0-120 are rejected.

### Missing customer or cruise
- Requests for non-existent customer or cruise ids fail with a clear error.

### Empty booking payload
- A booking with no passengers is rejected.

### Invalid promotion code
- A non-existent or expired promotion code is rejected.

## 3. Boundary cases

### Maximum passenger count
- Exactly 6 passengers is allowed.
- 7 passengers is rejected.

### Minimum supported age
- Age 0 is valid and priced as free.

### Exact capacity match
- Booking is allowed when remaining capacity equals passenger count.

### Zero remaining capacity
- A new booking fails if there are no seats left.

## 4. Promotion cases
### Minimum spend threshold
- The promotion is valid when the booking total equals the minimum threshold.
- The promotion is rejected when the booking total is below threshold.

### Failure rollback
- If booking creation fails after promotion validation, promotion redemption remains at zero and the booking is not persisted.
### Valid promotion
- A promotion valid for the date and minimum spend is accepted.

### Minimum spend requirement
- A promotion fails validation if the booking total is below the configured minimum spend.

### Percentage promotion
- A percentage promo reduces subtotal before tax.

### Fixed amount promotion
- A fixed-value promotion applies a capped discount to the total subtotal.

### Per-customer use limit
- A customer cannot reuse a promotion beyond the configured per-customer limit.

### Total usage limit
- The promotion stops being valid once the maximum total redemptions are reached.

## 5. Capacity cases

### Insufficient capacity
- A booking fails if the requested passenger count exceeds cruise capacity.

### Capacity decrement
- Successful booking reduces `capacity_left` by the number of passengers.

### Capacity exact match business rule
- A booking is accepted when the capacity requirement is exactly matched.

## 6. Historical pricing cases

### Fare change after booking
- A cruise adult fare can change after a booking is created without changing the stored booking values.
- The booking keeps its original `original_adult_fare` and final total snapshot.

### Snapshot integrity
- The historical values stored on the booking remain fixed even when the underlying cruise fare changes later.

## 7. Rollback cases

### Failed booking should not persist partial writes
- If capacity is insufficient, no booking row is created.
- The cruise capacity remains unchanged.

### Transaction integrity
- If any part of the booking creation fails, the transaction is rolled back, including capacity updates and inserted child records.

## 8. Service-level coverage implemented in code

The actual test suite covers the major business rules across:

- pricing rules
- service totals
- sales tax calculation sequence
- promotions
- capacity enforcement
- transaction rollback
- historical price snapshots
- API integration for the main endpoints

These are the implemented verification points for the assessment and match the current application behavior.
