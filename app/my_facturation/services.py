from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, func, over, case
from sqlalchemy.orm import Session, aliased

from app.payu.models import Invoice
from app.facturation.models import Lot, PropertyLot, PaymentInterval, User, Property

class MyFacturationService:
    def __init__(self, db: Session):
        self.db = db

    def list_user_invoices(self, user_id: int):
        """
        Devuelve todas las facturas asociadas a un usuario:
         - invoice_id
         - reference_code
         - property_id
         - property_name
         - lot_id
         - lot_name
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
                Property.name.label("property_name"),
                Invoice.lot_id,
                Lot.name.label("lot_name"),
                PI.name.label("payment_interval"),
                PI.interval_days.label("payment_days"),
                Invoice.invoiced_period,
                Invoice.expiration_date,
                Invoice.issuance_date,
                Invoice.total_amount,
                Invoice.status,
                Invoice.pdf_url,
                User.document_number
            )
            .filter(Invoice.user_id == user_id)
            .join(User, User.id == Invoice.user_id)
            .join(Lot, Invoice.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval_id == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .join(Property, Property.id == PropertyLot.property_id)
            .order_by(Invoice.expiration_date.desc())
            .all()
        )

        result = []

        for (
            inv_id,
            ref_code,
            prop_id,
            prop_name,
            lot_id,
            lot_name,
            interval,
            payment_days,
            invoiced_period,
            exp_dt,
            iss_dt,
            amount,
            status,
            pdf_url,
            doc_number
        ) in rows:
            exp_date = exp_dt.date() if hasattr(exp_dt, "date") else exp_dt
            iss_date = iss_dt.date() if hasattr(iss_dt, "date") else iss_dt
            result.append({
                "invoice_id":       inv_id,
                "reference_code":   ref_code,
                "property_id":      prop_id,
                "property_name":    prop_name,
                "lot_id":           lot_id,
                "lot_name":         lot_name,
                "payment_interval": interval,
                "payment_days":     payment_days,
                "invoiced_period":  invoiced_period,
                "expiration_date":  exp_date,
                "issuance_date":    iss_date,
                "total_amount":     float(amount),
                "invoice_status":   status,
                "pdf_url":          pdf_url,
                "document_number":  doc_number
            })
        return result
    
    def list_user_latest_invoices_by_lot(self, user_id: int):
        if not self.db.query(User).filter(User.id == user_id).first():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        PI = aliased(PaymentInterval)

        subquery = (
            self.db.query(
                Invoice.id.label("invoice_id"),
                Invoice.reference_code,
                Invoice.lot_id,
                PropertyLot.property_id,
                Property.name.label("property_name"),
                Lot.name.label("lot_name"),
                PI.name.label("payment_interval"),
                PI.interval_days.label("payment_days"),
                Invoice.invoiced_period,
                Invoice.expiration_date,
                Invoice.issuance_date,
                Invoice.total_amount,
                Invoice.status,
                Invoice.pdf_url,
                User.document_number,
                func.row_number().over(
                    partition_by=Invoice.lot_id,
                    order_by=Invoice.issuance_date.desc()  # ← CAMBIO CLAVE
                ).label("rn")
            )
            .filter(Invoice.user_id == user_id)
            .join(User, User.id == Invoice.user_id)
            .join(Lot, Invoice.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval_id == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .join(Property, Property.id == PropertyLot.property_id)
            .subquery()
        )

        rows = self.db.query(subquery).filter(subquery.c.rn <= 12).all()

        result = []
        for row in rows:
            exp_date = row.expiration_date.date() if hasattr(row.expiration_date, "date") else row.expiration_date
            iss_date = row.issuance_date.date() if hasattr(row.issuance_date, "date") else row.issuance_date

            result.append({
                "invoice_id":       row.invoice_id,
                "reference_code":   row.reference_code,
                "property_id":      row.property_id,
                "property_name":    row.property_name,
                "lot_id":           row.lot_id,
                "lot_name":         row.lot_name,
                "payment_interval": row.payment_interval,
                "payment_days":     row.payment_days,
                "invoiced_period":  row.invoiced_period,
                "expiration_date":  exp_date,
                "issuance_date":    iss_date,
                "total_amount":     float(row.total_amount),
                "invoice_status":   row.status,
                "pdf_url":          row.pdf_url,
                "document_number":  row.document_number
            })

        return result


    def get_user_invoice_summary(self, user_id: int):
        """
        Resumen de facturas de un usuario:
         - total: número total de facturas
         - paid: facturas con status 'pagada'
         - pending: facturas con status 'pendiente'
         - overdue: expiradas y no pagadas
        """
        # 0) Verificar existencia de usuario
        if not self.db.query(User).filter(User.id == user_id).first():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        today = date.today()
        summary = (
            self.db.query(
                func.count(Invoice.id).label("total"),
                func.count(case((Invoice.status == "pagada", 1))).label("paid"),
                func.count(case((Invoice.status == "pendiente", 1))).label("pending"),
                func.count(case(((Invoice.expiration_date < today) & (Invoice.status != "pagada"), 1))).label("overdue"),
            )
            .filter(Invoice.user_id == user_id)
            .one()
        )
        return summary._asdict()
