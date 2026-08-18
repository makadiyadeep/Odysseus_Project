from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.exceptions import BusinessRuleError, PromotionValidationError
from app.models import Promotion, PromotionRedemption
from app.services.pricing import PricingService


class PromotionService:
    @staticmethod
    def _now_date() -> date:
        return datetime.utcnow().date()

    @staticmethod
    def _promotion_exists(db: Session, code: str) -> Promotion | None:
        return db.query(Promotion).filter(Promotion.code == code).first()

    @staticmethod
    def _total_redemptions(db: Session, promotion_id: int) -> int:
        return (
            db.query(func.count(PromotionRedemption.id))
            .filter(PromotionRedemption.promotion_id == promotion_id)
            .scalar()
            or 0
        )

    @staticmethod
    def _customer_redemptions(db: Session, promotion_id: int, customer_id: int) -> int:
        return (
            db.query(func.count(PromotionRedemption.id))
            .filter(
                PromotionRedemption.promotion_id == promotion_id,
                PromotionRedemption.customer_id == customer_id,
            )
            .scalar()
            or 0
        )

    @staticmethod
    def validate_promotion(
        db: Session,
        customer_id: int,
        code: str,
        booking_total: Decimal,
        booking_date: date | None = None,
    ) -> Promotion:
        booking_date = booking_date or PromotionService._now_date()
        promotion = PromotionService._promotion_exists(db, code)
        if promotion is None:
            raise PromotionValidationError("PROMO_NOT_FOUND", f"Promotion code {code} was not found.")

        if booking_date < promotion.valid_from:
            raise PromotionValidationError("PROMO_NOT_YET_VALID", f"Promotion code {code} is not valid yet.")
        if booking_date > promotion.valid_to:
            raise PromotionValidationError("PROMO_EXPIRED", f"Promotion code {code} has expired.")

        total_uses = PromotionService._total_redemptions(db, promotion.id)
        if total_uses >= promotion.max_total_uses:
            raise PromotionValidationError(
                "PROMO_TOTAL_LIMIT_REACHED",
                f"Promotion code {code} has reached its total usage limit.",
            )

        customer_uses = PromotionService._customer_redemptions(db, promotion.id, customer_id)
        if customer_uses >= promotion.max_uses_per_customer:
            raise PromotionValidationError(
                "PROMO_CUSTOMER_LIMIT_REACHED",
                f"Customer has already used promotion code {code} the maximum allowed times.",
            )

        if promotion.minimum_spend is not None and booking_total < promotion.minimum_spend:
            raise PromotionValidationError(
                "PROMO_MINIMUM_SPEND_NOT_MET",
                f"Promotion code {code} requires a minimum spend of {promotion.minimum_spend}.",
            )

        return promotion

    @staticmethod
    def calculate_discount(promotion: Promotion, subtotal: Decimal) -> Decimal:
        if promotion is None:
            return Decimal("0")
        if subtotal <= 0:
            return Decimal("0")

        if promotion.promo_type == "percentage":
            discount = subtotal * (promotion.value / Decimal("100"))
        elif promotion.promo_type == "fixed":
            discount = promotion.value
        else:
            raise BusinessRuleError("PROMO_TYPE_INVALID", f"Unsupported promotion type: {promotion.promo_type}")

        return min(discount, subtotal)

    @staticmethod
    def discount_for_promotion(promotion: Promotion, subtotal: Decimal) -> Decimal:
        return PricingService.calculate_promotion_discount(promotion, subtotal)

    @staticmethod
    def record_redemption(db: Session, promotion_id: int, customer_id: int, booking_id: int) -> PromotionRedemption:
        redemption = PromotionRedemption(
            promotion_id=promotion_id,
            customer_id=customer_id,
            booking_id=booking_id,
        )
        db.add(redemption)
        return redemption
