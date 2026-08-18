# Business Requirements

## 1. Understanding of the requirements

This application models a cruise booking domain as a modular monolith. The core business problem is to support:

- browsing available cruises
- creating customer records
- calculating booking quotes based on passenger age, cruise fare, services, and promotion eligibility
- confirming bookings while enforcing capacity and business constraints
- storing a historical snapshot of the fare used at booking time
- validating promotion codes against business rules

The implementation is deliberately limited to the domain rules and service logic required by the assessment, without adding front-end, authentication, or broader operational features.

## 2. Assumptions

- Cruise fares are stored in a single adult fare value and passenger pricing is derived from age brackets.
- Adult pricing is the base fare for passengers aged 18 or older.
- Children/teens receive discounted passenger pricing by age band.
- Promotions are applied after cruise + service subtotal and before tax.
- Taxes are calculated on the discounted taxable amount based on a fixed rate of 12%.
- Capacity is enforced using the cruise's `capacity_left` field, which is decremented at booking time.
- Historical pricing is captured at booking creation so later price changes to the cruise do not affect the original booking total.

## 3. Ambiguities found

Several business points needed interpretation because the assessment did not define every edge case in detail:

- The actual tax behavior was not specified in the narrative, so the implementation adopted a fixed 12% sales tax applied after promotion discount.
- Promotion validation rules were not fully specified beyond code validity, date range, usage limits, and minimum spend, so the code implements reasonable domain checks consistent with the assessment tests.
- The historical pricing requirement implies storing the original cruise adult fare at booking time, but it does not specify a separate audit table, so the application stores the fare directly on the booking record.
- Capacity was assumed to be a reservation-style field that can be reduced exactly by passenger count, and booking creation fails atomically if capacity is insufficient.

## 4. Decisions made

- Passenger validation rejects empty lists, bookings with no adult passenger, invalid ages, and more than 6 passengers.
- Cruise lookup and customer lookup are required before quote or booking creation.
- Quote generation validates the same business rules but does not create a booking record or decrement capacity.
- Booking creation performs all persistence within a transactional unit to ensure capacity, booking creation, and redemption records either all succeed or all roll back.
- Promotions are validated as a service concern rather than a route concern.

## 5. Tax calculation decision

The assessment requires tax behavior to be consistent and deterministic. The implementation uses:

- Tax rate: 12%
- Calculation order: cruise subtotal + service total - promotion discount = taxable amount
- Tax amount = taxable_amount * 0.12
- Final total = taxable_amount + tax amount

This decision is based on the tests and was applied consistently across the pricing service and booking snapshot logic.

## 6. Promotion rules

Promotion validation covers:

- code existence
- active date window (`valid_from` to `valid_to`)
- global usage limit (`max_total_uses`)
- per-customer usage limit (`max_uses_per_customer`)
- minimum spend requirement when configured

Promotion discount behavior:

- percentage promotions reduce the subtotal by the requested percent
- fixed value promotions subtract a fixed amount, capped to the subtotal
- the promotion is applied after cruise/services subtotal and before tax
- only one promotion code is validated per quote or booking

## 7. Capacity rules

- A cruise cannot accept more passengers than `capacity_left`.
- A booking is rejected if the request exceeds the remaining capacity.
- Booking creation decrements `capacity_left` by the requested passenger count.
- Matching the exact remaining capacity is allowed.
- Capacity failures raise a domain-level capacity exception and trigger rollback.
- The system enforces capacity through an atomic conditional SQL update in the booking transaction; the pre-check is validation only and cannot be treated as the reservation mechanism.

## 8. Historical pricing decision

The booking record stores:

- `original_adult_fare`
- `cruise_fare_subtotal`
- `group_discount_rate`
- `group_discount_amount`
- `cruise_fare_after_group_discount`
- `service_total`
- `promotion_discount`
- `taxable_amount`
- `tax_amount`
- `final_total`

This means a cruise fare change after the booking is created does not alter the original price snapshot already stored for that booking, satisfying the historical pricing requirement.

## 9. Out-of-scope items

The following items were intentionally excluded from this implementation because they were outside the assessment requirements:

- authentication and authorization
- user roles or admin dashboards
- frontend UI or API documentation UI
- payment processing
- cancel/reschedule flows
- refunds or partial cancellations
- multi-tenant or distributed system concerns
- advanced reporting or analytics
- async background workers
- microservice decomposition

## 10. Implemented vs future improvements

Implemented features are the cruise catalog, customer creation, quote generation, booking creation, promotion validation, and booking retrieval in a modular monolith using SQLAlchemy and FastAPI.

Future improvements would include richer validation, stronger API contracts, richer error taxonomy, pagination, audit logging, and more domain coverage around edge-case promotions and service variants.
