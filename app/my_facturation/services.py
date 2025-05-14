# app/my_facturation/services.py

from datetime import date
from fastapi import HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session, aliased
from app.payu.models import Invoice
from app.facturation.models import (
    Lot,
    PropertyLot,
    PaymentInterval,
    User
)

class MyFacturationService:
    def __init__(self, db: Session):
        self.db = db

    
    def list_user_invoices(self, user_id: int):
        """
        Devuelve todas las facturas asociadas a un usuario:
         - invoice_id
         - reference_code
         - property_id
         - lot_id
         - payment_interval (nombre)
         - expiration_date (fecha, sin hora)
         - total_amount
         - status
        """
        # 0) Validar que el usuario exista
        if not self.db.query(User).filter(User.id == user_id).first():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        PI = aliased(PaymentInterval)

        rows = (
            self.db.query(
                Invoice.id.label("invoice_id"),             
                Invoice.reference_code,
                PropertyLot.property_id,
                Invoice.lot_id,
                PI.name.label("payment_interval"),
                Invoice.expiration_date,
                Invoice.total_amount,
                Invoice.status
            )
            .select_from(Invoice)
            .filter(Invoice.user_id == user_id)
            .join(Lot, Invoice.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .order_by(Invoice.expiration_date.desc())
            .all()
        )

        result = []
        for inv_id, ref_code, prop_id, lot_id, interval, exp_dt, amount, status in rows:
            exp_date = exp_dt.date() if hasattr(exp_dt, "date") else exp_dt
            result.append({
                "invoice_id":       inv_id,
                "reference_code":   ref_code,
                "property_id":      prop_id,
                "lot_id":           lot_id,
                "payment_interval": interval,
                "expiration_date":  exp_date,
                "total_amount":     float(amount),
                "status":           status
            })
        return result

    def get_user_invoice_summary(self, user_id: int):
        # 0) Verificar existencia de usuario
        if not self.db.query(User).filter(User.id == user_id).first():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        today = date.today()
        q = (
            self.db.query(
                func.count(Invoice.id).label("total"),
                func.count(case((Invoice.status == "pagada", 1))).label("paid"),
                func.count(case((Invoice.status == "pendiente", 1))).label("pending"),
                func.count(case(((Invoice.expiration_date < today) & (Invoice.status != "pagada"), 1))).label("overdue"),
            )
            .filter(Invoice.user_id == user_id)
        )
        return q.one()._asdict()
