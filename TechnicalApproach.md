# Technical Approach

## 1. Modular monolith architecture

The project uses a modular monolith pattern to keep the domain organized without introducing distributed services. The structure separates concerns across:

- API layer
- service layer
- database model layer
- shared exception definitions
- seed data

This approach keeps the system simple, testable, and aligned with the assessment requirements while remaining easy to extend if the domain grows.

## 2. API layer

The API layer is implemented in `app/main.py` using FastAPI.

Responsibilities:

- expose HTTP endpoints for cruises, customers, quotes, bookings, and promotion validation
- validate request payloads using Pydantic schemas
- convert domain exceptions into useful HTTP responses
- keep route code thin by delegating business behavior to services
- serialize domain models into JSON-ready response payloads

The route layer does not perform price calculations or capacity rules itself. It translates request data into service calls and returns what the service layer produces.

## 3. Service layer

The service layer contains the core domain behavior:

- `PricingService` for fare and tax logic
- `PromotionService` for validating and calculating promotion rules
- `BookingService` for quote generation, booking creation, validation, capacity handling, and snapshot persistence

This separation keeps business rules centralized and makes the code easier to unit test.

## 4. Database layer

The database layer is defined in `app/database.py` and uses SQLAlchemy 2.0 with SQLite.

It provides:

- engine configuration
- session factory (`SessionLocal`)
- declarative base (`Base`)
- helper to create tables on startup

The project uses SQLite for simplicity and testability, which is appropriate for this assessment environment.

## 5. Data model

The domain model is defined in `app/models.py` and covers the main entities:

- `Customer`
- `Cruise`
- `Passenger`
- `Service`
- `Promotion`
- `PromotionRedemption`
- `Booking`

Key design choices:

- booking records store fixed pricing snapshots rather than live fare lookups
- booking records persist a copy of the adult fare and final totals
- promotion redemption is tracked per booking and customer
- service and passenger records are stored as child records of the booking

## 6. PricingService

`PricingService` owns the calculation logic for:

- passenger-specific prices by age bracket
- group discount rate by passenger count
- service totals
- promotion discount calculation
- tax calculation
- final total generation

The service uses `Decimal` arithmetic with quantized amounts to avoid float precision issues. This is important because money handling requires deterministic rounding.

The key rule sequence is:

1. calculate cruise fare subtotal
2. apply group discount
3. add service total
4. apply promotion discount
5. calculate tax on taxable amount
6. total final amount

## 7. PromotionService

`PromotionService` validates and evaluates promotions.

Responsibilities:

- lookup promotion by code
- ensure promotion date validity
- enforce maximum total redemptions
- enforce maximum redemptions per customer
- enforce minimum spend threshold
- calculate promotion discount amount

It does not persist business records directly during quote generation; the booking service handles redemption persistence when a booking is confirmed.

## 8. BookingService

`BookingService` owns the booking lifecycle.

It handles:

- passenger validation
- customer and cruise existence checks
- quote generation for a future booking
- booking creation
- atomic capacity update
- passenger/service persistence
- promotion redemption persistence
- historical pricing snapshot capture

It operates as the orchestration point for the booking business flow.

## 9. Transaction handling

The booking workflow is intentionally designed to use a single transaction boundary around the persistence writes.

This matters because the operation updates multiple tables:

- `cruises` (capacity_left)
- `bookings`
- `passengers`
- `services`
- `promotion_redemptions`

The session is explicitly managed with SQLAlchemy so that if any part of the booking fails, the transaction is rolled back and the system remains consistent.

The critical business rule is that capacity is not treated as a purely in-memory check. The reservation is enforced at the database layer with a conditional update, so a booking can only succeed if the cruise still has sufficient capacity at the moment of the write.

## 10. Atomic capacity update

Capacity changes are implemented using a direct SQL `UPDATE` statement:

- reduce `capacity_left` by passenger count
- only succeed if the cruise has enough remaining capacity

This prevents race conditions and ensures the booking cannot be accepted when capacity has already been consumed. If the rowcount is zero, the service raises a capacity exception and aborts the transaction.

## 11. Historical price snapshot

Bookings persist historical values from the moment booking creation is successful. These values are stored directly on the `Booking` row, including:

- `original_adult_fare`
- `cruise_fare_subtotal`
- `group_discount_amount`
- `service_total`
- `promotion_discount`
- `tax_amount`
- `final_total`

This means a later change to the cruise fare does not change the already-created booking's financial record. This was an explicit requirement and is satisfied through snapshot persistence.

## 12. Why the design was chosen

This design was chosen because it is simple, focused, and aligned with the assessment constraints:

- low operational complexity
- clear separation of responsibilities
- straightforward unit and integration testing
- no unnecessary frontend or authentication complexity
- business rules centralized in the service layer
- SQLite is sufficient for a small, local domain model

It is a practical design for a constrained assessment rather than a production-scale booking platform.

## 13. What would be improved with more time

Given more time, the project would benefit from:

- better API versioning and route organization
- more robust exception handling and error taxonomy
- pagination for cruise and booking listings
- more explicit lifespan event management instead of startup hooks
- richer schema validation and API contract documentation
- audit logging and domain event hooks
- stronger concurrency and idempotency safeguards for high-volume use
- optional async or background processing for non-critical workflows

These are future improvements and are intentionally separated from the implemented assessment scope.
