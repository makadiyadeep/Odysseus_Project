from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Cruise


class CruiseService:
    @staticmethod
    def list_cruises(db: Session):
        return db.query(Cruise).all()

    @staticmethod
    def get_cruise(db: Session, cruise_id: int):
        return db.query(Cruise).filter(Cruise.id == cruise_id).first()
