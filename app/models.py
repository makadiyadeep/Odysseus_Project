from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PromotionType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class ServiceType(str, Enum):
    INSURANCE = "insurance"
    WIFI = "wifi"
    SHORE_EXCURSION = "shore_excursion"


class BookingStatus(str, Enum):
    QUOTED = "quoted"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")
    redemptions: Mapped[list["PromotionRedemption"]] = relationship(back_populates="customer")


class Cruise(Base):
    __tablename__ = "cruises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ship_name: Mapped[str] = mapped_column(String(200), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    adult_fare: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    capacity_left: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="cruise")

    __table_args__ = (
        CheckConstraint("nights > 0", name="ck_cruise_nights_positive"),
        CheckConstraint("capacity_left >= 0", name="ck_cruise_capacity_non_negative"),
    )


class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    passenger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="passengers")

    __table_args__ = (
        CheckConstraint("age >= 0", name="ck_passenger_age_non_negative"),
        CheckConstraint("passenger_type IN ('adult', 'child')", name="ck_passenger_type_valid"),
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="services")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_service_quantity_positive"),
        CheckConstraint("service_type IN ('insurance', 'wifi', 'shore_excursion')", name="ck_service_type_valid"),
    )


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    promo_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[Date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Date] = mapped_column(Date, nullable=False)
    max_total_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses_per_customer: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    redemptions: Mapped[list["PromotionRedemption"]] = relationship(back_populates="promotion")

    __table_args__ = (
        CheckConstraint("promo_type IN ('percentage', 'fixed')", name="ck_promotion_type_valid"),
        CheckConstraint("value >= 0", name="ck_promotion_value_non_negative"),
        CheckConstraint("max_total_uses > 0", name="ck_promotion_total_uses_positive"),
        CheckConstraint("max_uses_per_customer > 0", name="ck_promotion_customer_uses_positive"),
    )


class PromotionRedemption(Base):
    __tablename__ = "promotion_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("promotions.id"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, unique=True)
    redeemed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    promotion: Mapped[Promotion] = relationship(back_populates="redemptions")
    customer: Mapped[Customer] = relationship(back_populates="redemptions")
    booking: Mapped["Booking"] = relationship(back_populates="promotion_redemption")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    cruise_id: Mapped[int] = mapped_column(ForeignKey("cruises.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default=BookingStatus.CONFIRMED.value, nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    adult_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cruise_fare_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    group_discount_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    group_discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cruise_fare_after_group_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    service_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    promotion_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    promotion_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    promotion_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    promotion_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    final_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # FIX: Store the original adult fare at booking time to preserve the
    # complete historical price snapshot. If cruise fares change later, this
    # record remains unchanged, maintaining an audit trail of charged prices.
    original_adult_fare: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="bookings")
    cruise: Mapped[Cruise] = relationship(back_populates="bookings")
    passengers: Mapped[list[Passenger]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    services: Mapped[list[Service]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    promotion_redemption: Mapped[Optional[PromotionRedemption]] = relationship(back_populates="booking", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("passenger_count > 0", name="ck_booking_passenger_count_positive"),
        CheckConstraint("adult_count >= 1", name="ck_booking_adult_count_minimum"),
        CheckConstraint("passenger_count <= 6", name="ck_booking_passenger_count_maximum"),
        CheckConstraint("child_count >= 0", name="ck_booking_child_count_non_negative"),
        CheckConstraint("status IN ('quoted', 'confirmed', 'cancelled')", name="ck_booking_status_valid"),
    )
