# Cruise Booking Assessment

## Project overview

This project implements a modular monolith cruise booking assessment using Python, FastAPI, SQLAlchemy, SQLite, and Pytest.

It supports:

- cruise browsing
- customer creation and lookup
- quote generation
- booking creation
- promotion validation
- price snapshot persistence for historical pricing

The implementation intentionally excludes frontend work, authentication, payment processing, and non-core business operations.

## Technology stack

- Python 3.13
- FastAPI
- SQLAlchemy 2.0
- SQLite
- Pydantic
- Pytest
- httpx for API testing

## Architecture

The project follows a modular monolith layout:

- `app/main.py` — FastAPI app and route layer
- `app/services/` — business logic services
- `app/models.py` — SQLAlchemy domain models
- `app/database.py` — engine and session setup
- `app/schemas.py` — request/response validation models
- `app/exceptions.py` — domain exceptions
- `app/seed.py` — seed data for cruise and promotions
- `tests/` — unit and integration tests

## Setup

1. Open the project folder.
2. Ensure the virtual environment exists.
3. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Database initialization

The application creates the database tables automatically on app startup.

The database URL is defined in `app/database.py` as:

```python
sqlite:///./cruise_booking.db
```

## Seed instructions

The seed data is loaded via `app.seed.seed_data()` during app startup.

If you need to reseed manually, you can run the application startup flow or call the seed function from Python.

## Run command

```bash
.venv/bin/python -m uvicorn app.main:app --reload
```

## Test command

```bash
.venv/bin/python -m pytest -q
```

## API endpoints

### Health

- GET /health

### Cruises

- GET /api/cruises
- GET /api/cruises/{id}

### Customers

- POST /api/customers
- GET /api/customers/{id}

### Bookings

- POST /api/bookings/quote
- POST /api/bookings
- GET /api/bookings/{booking_reference}

### Promotions

- POST /api/promotions/validate

## Example requests and responses

### Create customer

Request:

```http
POST /api/customers
Content-Type: application/json

{
  "name": "Test User",
  "email": "user@example.com"
}
```

Response:

```json
{
  "id": 1,
  "name": "Test User",
  "email": "user@example.com"
}
```

### Quote booking

Request:

```http
POST /api/bookings/quote
Content-Type: application/json

{
  "customer_id": 1,
  "cruise_id": 1,
  "passengers": [
    {"first_name": "Alice", "last_name": "One", "age": 18},
    {"first_name": "Sophie", "last_name": "One", "age": 12}
  ],
  "services": [],
  "promotion_code": "SUMMER10"
}
```

Response:

```json
{
  "customer_id": 1,
  "cruise_id": 1,
  "passenger_count": 2,
  "adults": 1,
  "children": 1,
  "quote_summary": {
    "cruise_fare_subtotal": 2100.0,
    "group_discount_rate": 0.0,
    "group_discount_amount": 0.0,
    "cruise_fare_after_group_discount": 2100.0,
    "service_total": 0.0,
    "promotion_discount": 210.0,
    "taxable_amount": 1890.0,
    "tax_rate": 0.12,
    "tax_amount": 226.8,
    "final_total": 2116.8,
    "currency": "USD"
  },
  "passengers": [
    {"first_name": "Alice", "last_name": "One", "age": 18, "passenger_type": "adult", "unit_price": 1200.0},
    {"first_name": "Sophie", "last_name": "One", "age": 12, "passenger_type": "child", "unit_price": 900.0}
  ],
  "services": [],
  "promotion_code": "SUMMER10"
}
```

### Create booking

Request:

```http
POST /api/bookings
Content-Type: application/json

{
  "customer_id": 1,
  "cruise_id": 1,
  "passengers": [
    {"first_name": "Alice", "last_name": "One", "age": 18},
    {"first_name": "Sophie", "last_name": "One", "age": 12}
  ],
  "services": [],
  "promotion_code": "SUMMER10"
}
```

Response:

```json
{
  "id": 1,
  "booking_reference": "CR-AB12CD34",
  "customer_id": 1,
  "cruise_id": 1,
  "status": "confirmed",
  "cruise": {
    "id": 1,
    "ship_name": "Wonder of the Seas",
    "destination": "Caribbean",
    "nights": 7,
    "adult_fare": 1200.0,
    "capacity_left": 8
  },
  "passengers": [
    {
      "id": 1,
      "first_name": "Alice",
      "last_name": "One",
      "age": 18,
      "passenger_type": "adult",
      "unit_price": 1200.0
    },
    {
      "id": 2,
      "first_name": "Sophie",
      "last_name": "One",
      "age": 12,
      "passenger_type": "child",
      "unit_price": 900.0
    }
  ],
  "services": [],
  "price_breakdown": {
    "cruise_fare_subtotal": 2100.0,
    "group_discount_rate": 0.0,
    "group_discount_amount": 0.0,
    "cruise_fare_after_group_discount": 2100.0,
    "service_total": 0.0,
    "promotion_discount": 210.0,
    "taxable_amount": 1890.0,
    "tax_rate": 0.12,
    "tax_amount": 226.8,
    "final_total": 2116.8,
    "currency": "USD"
  },
  "promotion": {
    "code": "SUMMER10",
    "type": "percentage",
    "value": 10.0,
    "discount_amount": 210.0
  },
  "total": 2116.8
}
```

## Implementation boundaries

This project intentionally does not include:

- frontend UI
- authentication or authorization
- payment handling
- cancel/reschedule flows
- broader analytics or reporting
- distributed services

These are explicitly future enhancements rather than implemented features.
