from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models import Cruise, Promotion, PromotionType


CRUISE_SEED_DATA = [
    {
        "ship_name": "Wonder of the Seas",
        "destination": "Caribbean",
        "nights": 7,
        "adult_fare": Decimal("1200"),
        "capacity_left": 12,
    },
    {
        "ship_name": "Celebrity Beyond",
        "destination": "Mediterranean",
        "nights": 10,
        "adult_fare": Decimal("1850"),
        "capacity_left": 4,
    },
    {
        "ship_name": "Norwegian Prima",
        "destination": "Alaska",
        "nights": 5,
        "adult_fare": Decimal("950"),
        "capacity_left": 20,
    },
    {
        "ship_name": "Sky Princess",
        "destination": "Northern Europe",
        "nights": 12,
        "adult_fare": Decimal("2100"),
        "capacity_left": 2,
    },
    {
        "ship_name": "MSC Seascape",
        "destination": "Bahamas",
        "nights": 4,
        "adult_fare": Decimal("700"),
        "capacity_left": 0,
    },
]


PROMOTION_SEED_DATA = [
    {
        "code": "SUMMER10",
        "promo_type": PromotionType.PERCENTAGE.value,
        "value": Decimal("10"),
        "valid_from": date(2026, 6, 1),
        "valid_to": date(2026, 8, 31),
        "max_total_uses": 100,
        "max_uses_per_customer": 1,
        "minimum_spend": Decimal("1000"),
    },
    {
        "code": "FIRST150",
        "promo_type": PromotionType.FIXED.value,
        "value": Decimal("150"),
        "valid_from": date(2026, 1, 1),
        "valid_to": date(2026, 12, 31),
        "max_total_uses": 500,
        "max_uses_per_customer": 1,
        "minimum_spend": Decimal("2000"),
    },
    {
        "code": "CREW25",
        "promo_type": PromotionType.PERCENTAGE.value,
        "value": Decimal("25"),
        "valid_from": date(2026, 1, 1),
        "valid_to": date(2026, 12, 31),
        "max_total_uses": 3,
        "max_uses_per_customer": 3,
        "minimum_spend": None,
    },
    {
        "code": "WINTER5",
        "promo_type": PromotionType.PERCENTAGE.value,
        "value": Decimal("5"),
        "valid_from": date(2025, 1, 1),
        "valid_to": date(2025, 3, 31),
        "max_total_uses": 1000,
        "max_uses_per_customer": 5,
        "minimum_spend": None,
    },
]


def seed_data():
    db = SessionLocal()
    try:
        if db.query(Cruise).count() == 0:
            for item in CRUISE_SEED_DATA:
                db.add(Cruise(**item))

        for item in PROMOTION_SEED_DATA:
            existing = db.query(Promotion).filter_by(code=item["code"]).first()
            if existing is None:
                db.add(Promotion(**item))
            else:
                for key, value in item.items():
                    setattr(existing, key, value)

        db.commit()
    finally:
        db.close()
