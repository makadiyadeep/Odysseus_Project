from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.exceptions import BusinessRuleError, PromotionValidationError
from app.models import Customer, Promotion, PromotionRedemption
from app.services.promotion import PromotionService


def make_customer(db: Session, name: str = "Alice", email: str | None = None) -> Customer:
    customer = Customer(name=name, email=email or f"{name.lower()}@example.com")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def make_promotion(
    db: Session,
    code: str,
    promo_type: str,
    value: Decimal,
    valid_from: date,
    valid_to: date,
    max_total_uses: int,
    max_uses_per_customer: int,
    minimum_spend: Decimal | None,
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


def make_redemption(db: Session, promotion: Promotion, customer: Customer, booking_id: int) -> PromotionRedemption:
    redemption = PromotionRedemption(
        promotion_id=promotion.id,
        customer_id=customer.id,
        booking_id=booking_id,
    )
    db.add(redemption)
    db.commit()
    return redemption


def test_valid_percentage_promotion(db):
    customer = make_customer(db)
    promotion = make_promotion(
        db,
        "SAVE10",
        "percentage",
        Decimal("10"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        100,
        1,
        Decimal("1000"),
    )

    validated = PromotionService.validate_promotion(db, customer.id, "SAVE10", Decimal("1500"), date(2026, 7, 1))

    assert validated.id == promotion.id
    assert PromotionService.calculate_discount(promotion, Decimal("1500")) == Decimal("150.00")


def test_valid_fixed_promotion(db):
    customer = make_customer(db)
    promotion = make_promotion(
        db,
        "FIRST150",
        "fixed",
        Decimal("150"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        50,
        1,
        Decimal("2000"),
    )

    validated = PromotionService.validate_promotion(db, customer.id, "FIRST150", Decimal("2500"), date(2026, 8, 1))

    assert validated.id == promotion.id
    assert PromotionService.calculate_discount(promotion, Decimal("2500")) == Decimal("150.00")


def test_invalid_promotion_code(db):
    customer = make_customer(db)

    with pytest.raises(PromotionValidationError, match="PROMO_NOT_FOUND") as exc:
        PromotionService.validate_promotion(db, customer.id, "MISSING", Decimal("2000"), date(2026, 7, 1))

    assert exc.value.code == "PROMO_NOT_FOUND"


def test_expired_promotion(db):
    customer = make_customer(db)
    make_promotion(
        db,
        "WINTER5",
        "percentage",
        Decimal("5"),
        date(2025, 1, 1),
        date(2025, 3, 31),
        100,
        1,
        None,
    )

    with pytest.raises(PromotionValidationError, match="PROMO_EXPIRED") as exc:
        PromotionService.validate_promotion(db, customer.id, "WINTER5", Decimal("1000"), date(2025, 4, 1))

    assert exc.value.code == "PROMO_EXPIRED"


def test_future_promotion(db):
    customer = make_customer(db)
    make_promotion(
        db,
        "FUTURE10",
        "percentage",
        Decimal("10"),
        date(2027, 1, 1),
        date(2027, 12, 31),
        100,
        1,
        None,
    )

    with pytest.raises(PromotionValidationError, match="PROMO_NOT_YET_VALID") as exc:
        PromotionService.validate_promotion(db, customer.id, "FUTURE10", Decimal("1000"), date(2026, 12, 31))

    assert exc.value.code == "PROMO_NOT_YET_VALID"


def test_minimum_spend_not_met(db):
    customer = make_customer(db)
    make_promotion(
        db,
        "HAPPY20",
        "percentage",
        Decimal("20"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        100,
        1,
        Decimal("2000"),
    )

    with pytest.raises(PromotionValidationError, match="PROMO_MINIMUM_SPEND_NOT_MET") as exc:
        PromotionService.validate_promotion(db, customer.id, "HAPPY20", Decimal("1500"), date(2026, 7, 1))

    assert exc.value.code == "PROMO_MINIMUM_SPEND_NOT_MET"


def test_total_usage_limit_reached(db):
    customer = make_customer(db)
    promotion = make_promotion(
        db,
        "LIMITED5",
        "percentage",
        Decimal("5"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        1,
        5,
        None,
    )
    make_redemption(db, promotion, customer, 101)

    with pytest.raises(PromotionValidationError, match="PROMO_TOTAL_LIMIT_REACHED") as exc:
        PromotionService.validate_promotion(db, customer.id, "LIMITED5", Decimal("2000"), date(2026, 7, 1))

    assert exc.value.code == "PROMO_TOTAL_LIMIT_REACHED"


def test_customer_usage_limit_reached(db):
    customer = make_customer(db)
    promotion = make_promotion(
        db,
        "USER2",
        "percentage",
        Decimal("10"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        10,
        1,
        None,
    )
    make_redemption(db, promotion, customer, 201)

    with pytest.raises(PromotionValidationError, match="PROMO_CUSTOMER_LIMIT_REACHED") as exc:
        PromotionService.validate_promotion(db, customer.id, "USER2", Decimal("2000"), date(2026, 7, 1))

    assert exc.value.code == "PROMO_CUSTOMER_LIMIT_REACHED"


def test_successful_redemption_marks_usage(db):
    customer = make_customer(db)
    promotion = make_promotion(
        db,
        "GOOD10",
        "percentage",
        Decimal("10"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        100,
        2,
        None,
    )

    validated = PromotionService.validate_promotion(db, customer.id, "GOOD10", Decimal("2000"), date(2026, 7, 1))
    PromotionService.record_redemption(db, validated.id, customer.id, 301)
    db.commit()

    assert validated.id == promotion.id
    assert db.query(PromotionRedemption).count() == 1


def test_discount_cannot_make_taxable_subtotal_negative(db):
    promotion = make_promotion(
        db,
        "OVER50",
        "fixed",
        Decimal("1000"),
        date(2026, 1, 1),
        date(2026, 12, 31),
        100,
        2,
        Decimal("0"),
    )

    discount = PromotionService.calculate_discount(promotion, Decimal("200"))

    assert discount == Decimal("200.00")
    assert discount >= Decimal("0")


def test_invalid_promotion_type_raises_business_error(db):
    promotion = Promotion(
        code="BADTYPE",
        promo_type="unknown",
        value=Decimal("10"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        max_total_uses=100,
        max_uses_per_customer=1,
        minimum_spend=None,
        is_active=True,
    )

    with pytest.raises(BusinessRuleError, match="PROMO_TYPE_INVALID"):
        PromotionService.calculate_discount(promotion, Decimal("1000"))
