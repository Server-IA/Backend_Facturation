# app/my_facturation/services.py

from sqlalchemy.orm import Session, aliased
from app.facturation.models import Lot, PropertyLot, PaymentInterval, User
from app.payu.models         import Invoice

class MyFacturationService:
    def __init__(self, db: Session):
        self.db = db

    def list_user_invoices(self, user_id: int):
        """
        Devuelve todas las facturas asociadas a un usuario:
         - reference_code
         - property_id
         - lot_id
         - payment_interval (nombre)
         - expiration_date (fecha, sin hora)
         - total_amount
         - status
        """
        PI = aliased(PaymentInterval)

        rows = (
            self.db.query(
                Invoice.reference_code,
                PropertyLot.property_id,
                Invoice.lot_id,
                PI.name.label("payment_interval"),
                Invoice.expiration_date,
                Invoice.total_amount,
                Invoice.status
            )
            .select_from(Invoice)
            .join(Lot, Invoice.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .filter(Invoice.user_id == user_id)
            .order_by(Invoice.expiration_date.desc())
            .all()
        )

        result = []
        for ref_code, prop_id, lot_id, interval, exp_dt, amount, status in rows:
            # convertir expiration_date de datetime a date
            exp_date = exp_dt.date() if hasattr(exp_dt, "date") else exp_dt
            result.append({
                "reference_code":   ref_code,
                "property_id":      prop_id,
                "lot_id":           lot_id,
                "payment_interval": interval,
                "expiration_date":  exp_date,
                "total_amount":     float(amount),
                "status":           status
            })
        return result
