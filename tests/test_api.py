from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app, get_db
from app.models import Cruise, Customer, Promotion


@pytest.fixture
def client_and_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def seed_data(db):
    customer = Customer(name="Alice", email="alice@example.com")
    db.add(customer)
    db.commit()
    db.refresh(customer)

    cruise = Cruise(
        ship_name="Wonder of the Seas",
        destination="Caribbean",
        nights=7,
        adult_fare=Decimal("1200"),
        capacity_left=10,
    )
    db.add(cruise)
    db.commit()
    db.refresh(cruise)

    promo = Promotion(
        code="SUMMER10",
        promo_type="percentage",
        value=Decimal("10"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        max_total_uses=100,
        max_uses_per_customer=1,
        minimum_spend=Decimal("1000"),
        is_active=True,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)

    return customer, cruise, promo


def test_get_cruises_and_single_cruise(client_and_db):
    client, db = client_and_db
    seed_data(db)

    response = client.get("/api/cruises")
    assert response.status_code == 200
    assert len(response.json()) >= 1

    cruise_id = db.query(Cruise).first().id
    response = client.get(f"/api/cruises/{cruise_id}")
    assert response.status_code == 200
    assert response.json()["id"] == cruise_id


def test_create_and_fetch_customer(client_and_db):
    client, _ = client_and_db

    response = client.post("/api/customers", json={"name": "Test User", "email": "user@example.com"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "user@example.com"

    customer_id = payload["id"]
    response = client.get(f"/api/customers/{customer_id}")
    assert response.status_code == 200
    assert response.json()["id"] == customer_id


def test_booking_quote_endpoint(client_and_db):
    client, db = client_and_db
    customer, cruise, _ = seed_data(db)

    payload = {
        "customer_id": customer.id,
        "cruise_id": cruise.id,
        "passengers": [{"first_name": "Alice", "last_name": "One", "age": 18}, {"first_name": "Sophie", "last_name": "One", "age": 12}],
        "services": [],
        "promotion_code": "SUMMER10",
    }
    response = client.post("/api/bookings/quote", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["passenger_count"] == 2
    assert body["quote_summary"]["final_total"] > 0


def test_create_booking_and_get_by_reference(client_and_db):
    client, db = client_and_db
    customer, cruise, _ = seed_data(db)

    payload = {
        "customer_id": customer.id,
        "cruise_id": cruise.id,
        "passengers": [{"first_name": "Alice", "last_name": "One", "age": 18}, {"first_name": "Sophie", "last_name": "One", "age": 12}],
        "services": [],
        "promotion_code": "SUMMER10",
    }
    response = client.post("/api/bookings", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["booking_reference"].startswith("CR-")
    assert body["total"] > 0
    assert body["promotion"]["code"] == "SUMMER10"

    booking_reference = body["booking_reference"]
    response = client.get(f"/api/bookings/{booking_reference}")
    assert response.status_code == 200
    assert response.json()["booking_reference"] == booking_reference


def test_validate_promotion_endpoint(client_and_db):
    client, db = client_and_db
    customer, _, _ = seed_data(db)

    response = client.post(
        "/api/promotions/validate",
        json={"customer_id": customer.id, "cruise_id": 1, "code": "SUMMER10", "booking_total": "2000"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["code"] == "SUMMER10"
