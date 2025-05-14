# app/services/billing.py
from fastapi import HTTPException
from datetime import date
from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session , aliased
from app.payu.models       import Payment , Invoice 
from app.facturation.models import PaymentInterval, PropertyLot ,PropertyUser , Property , Lot , User , ConsumptionMeasurement , Concept , InvoiceConcept
from app.facturation.models import Var as StatusVar 

class BillingService:
    def __init__(self, db: Session):
        self.db = db

    # --- Facturas ------------------------------------------------------------

    def get_invoice_counts(self):
        """
        Totales de facturas:
         - emitidas: todas las facturas registradas
         - pagadas:  aquellas con status != 'pendiente'
         - pendientes: status == 'pendiente'
         - vencidas: expiration_date < hoy y status != 'pagada'
        """
        today = date.today()
        q = self.db.query(
            func.count(Invoice.id).label("emitidas"),
            func.count(
                case((Invoice.status != "pendiente", 1))
            ).label("pagadas"),
            func.count(
                case((Invoice.status == "pendiente", 1))
            ).label("pendientes"),
            func.count(
                case(
                    ((Invoice.expiration_date < today) & (Invoice.status != "pagada"), 1)
                )
            ).label("vencidas")
        )
        return q.one()

    def list_invoices(self, offset: int = 0, limit: int = 100):
        """
        Devuelve facturas paginadas con el nombre del estado.
        """
        # suponiendo que Invoice.status_id apunta a vars.id
        return (
            self.db.query(
                Invoice,
                vars.name.label("status_name")
            )
            .join(vars, Invoice.status_id == vars.id)
            .order_by(Invoice.issuance_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    
    def get_invoice_chart_year(self, year: int):
        """
        Número de facturas emitidas por mes en el año indicado.
        Salida: [{"mes":1,"total":34}, ..., {"mes":12,"total":21}]
        """
        rows = (
            self.db.query(
                extract("month", Invoice.issuance_date).label("mes"),
                func.count(Invoice.id).label("total")
            )
            .filter(extract("year", Invoice.issuance_date) == year)
            .group_by("mes")
            .order_by("mes")
            .all()
        )
        return [{"mes": int(r.mes), "total": r.total} for r in rows]

    def get_invoice_amount_month(self, year: int, month: int):
        """
        Suma de total_amount de facturas emitidas en un mes cualquiera.
        """
        total = (
            self.db.query(func.coalesce(func.sum(Invoice.total_amount), 0))
            .filter(
                extract("year", Invoice.issuance_date) == year,
                extract("month", Invoice.issuance_date) == month
            )
            .scalar()
        )
        return float(total)

    def list_invoices_general(self):
        """
        Devuelve TODAS las facturas con:
         - invoice_id
         - invoice_number
         - property_id
         - lot_id
         - client_document (coalesce: primero invoice.user_id, luego por lote)
         - payment_interval (nombre; opcional)
         - issuance_date
         - expiration_date
         - amount_due
         - invoice_status
         - dian_status
        """
        PI           = aliased(PaymentInterval)
        DirectUser   = aliased(User)
        LotOwnerUser = aliased(User)

        q = (
            self.db.query(
                Invoice.id.label("invoice_id"),                            
                Invoice.reference_code.label("invoice_number"),
                PropertyLot.property_id,
                Invoice.lot_id,
                func.coalesce(
                    DirectUser.document_number,
                    LotOwnerUser.document_number
                ).label("client_document"),
                PI.name.label("payment_interval"),
                Invoice.issuance_date,
                Invoice.expiration_date,
                Invoice.total_amount.label("amount_due"),
                Invoice.status.label("invoice_status"),
                Invoice.dian_status.label("dian_status"),
            )
            .select_from(Invoice)
            .outerjoin(Lot, Invoice.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval == PI.id)
            .outerjoin(PropertyLot, PropertyLot.lot_id == Lot.id)
            .outerjoin(
                PropertyUser,
                PropertyUser.property_id == PropertyLot.property_id
            )
            .outerjoin(
                LotOwnerUser,
                PropertyUser.user_id == LotOwnerUser.id
            )
            .outerjoin(
                DirectUser,
                Invoice.user_id == DirectUser.id
            )
            .order_by(Invoice.issuance_date.desc())
        )

        return [row._asdict() for row in q.all()]


    def get_invoice_detail(self, invoice_id: int):
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        # Pago asociado
        payment = self.db.query(Payment).filter(Payment.invoice_id == invoice_id).first()
        payment_data = None
        if payment:
            payment_data = {
                "payment_method":     payment.payment_method,
                "reference_code":     payment.reference_code,
                "transaction_amount": float(payment.amount),
                "payment_date":       payment.paid_at,
                "payment_status_id":  payment.status,   # repetimos el texto
                "payment_status_name":payment.status
            }

        # Documento y property_id
        client_document = None
        if invoice.user_id:
            usr = self.db.get(User, invoice.user_id)
            client_document = usr.document_number if usr else None

        property_id = None
        if invoice.lot_id is not None:
            property_id = (
                self.db.query(PropertyLot.property_id)
                       .filter(PropertyLot.lot_id == invoice.lot_id)
                       .scalar()
            )
            if not client_document and property_id:
                pu = self.db.query(PropertyUser).filter(
                    PropertyUser.property_id == property_id
                ).first()
                if pu:
                    usr = self.db.get(User, pu.user_id)
                    client_document = usr.document_number if usr else None

        # Periodo facturado
        period = {
            "start_date":      getattr(invoice, "billing_start_date", None),
            "end_date":        getattr(invoice, "billing_end_date", None),
            "invoiced_period": getattr(invoice, "invoiced_period", None),
        }

        # Conceptos
        total_volume = self.db.query(
            func.sum(ConsumptionMeasurement.final_volume)
        ).filter(ConsumptionMeasurement.invoice_id == invoice_id).scalar() or 0

        conceptos = []
        for concept, ic in self.db.query(Concept, InvoiceConcept).join(
            InvoiceConcept, Concept.id == InvoiceConcept.concept_id
        ).filter(InvoiceConcept.invoice_id == invoice_id):
            conceptos.append({
                "concept_id":     concept.id,
                "nombre":         concept.nombre,
                "descripcion":    concept.descripcion,
                "valor_unitario": float(concept.valor),
                "total_concepto": float(total_volume * concept.valor)
            })

        return {
            "invoice": {
                "invoice_id":         invoice.id,
                "reference_code":     invoice.reference_code,
                "issuance_date":      invoice.issuance_date,
                "expiration_date":    invoice.expiration_date,
                **period,
                "total_amount":       float(invoice.total_amount),
                "client_name":        getattr(invoice, "client_name", None),
                "client_email":       getattr(invoice, "client_email", None),
                "client_document":    client_document,
                "property_id":        property_id,
                "lot_id":             invoice.lot_id,    
                "invoice_status_name":invoice.status,   
                "dian_status_id":     invoice.dian_status,
                "dian_status_name":   invoice.dian_status
            },
            "payment":  payment_data,
            "concepts": conceptos
        }


    # --- Transacciones (Pagos) -----------------------------------------------

    def get_payment_totals(self, year: int, month: int):
        """
        Usa la tabla payments para devolver:
         - ingresos_totales: suma de todos los pagos (sin filtrar)
         - ingresos_anuales: suma de pagos en el año
         - ingresos_mensuales: suma de pagos en el mes del año
         - tasa_rechazo: % de pagos con status = 'RECHAZADO' sobre total de ese mes
        """
        # Ingreso total histórico
        ingresos_totales = float(
            self.db.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
        )

        # Ingreso total del año
        ingresos_anuales = float(
            self.db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(extract("year", Payment.paid_at) == year)
            .scalar()
        )

        # Ingreso total del mes
        ingresos_mensuales = float(
            self.db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                extract("year", Payment.paid_at) == year,
                extract("month", Payment.paid_at) == month
            )
            .scalar()
        )

        # Conteos para tasa de rechazo
        total_pagos_mes = (
            self.db.query(func.count(Payment.id))
            .filter(
                extract("year", Payment.paid_at) == year,
                extract("month", Payment.paid_at) == month
            )
            .scalar()
        ) or 1

        rechazados = (
            self.db.query(func.count(Payment.id))
            .filter(
                extract("year", Payment.paid_at) == year,
                extract("month", Payment.paid_at) == month,
                Payment.status == "RECHAZADO"
            )
            .scalar()
        ) or 0

        tasa_rechazo = round(rechazados / total_pagos_mes * 100, 2)

        return {
            "ingresos_totales":    ingresos_totales,
            "ingresos_anuales":    ingresos_anuales,
            "ingresos_mensuales":  ingresos_mensuales,
            "tasa_rechazo":        tasa_rechazo
        }

    def get_payment_chart_year(self, year: int):
        """
        Número de pagos realizados por mes en el año indicado.
        """
        rows = (
            self.db.query(
                extract("month", Payment.paid_at).label("mes"),
                func.count(Payment.id).label("total")
            )
            .filter(extract("year", Payment.paid_at) == year)
            .group_by("mes")
            .order_by("mes")
            .all()
        )
        return [{"mes": int(r.mes), "total": r.total} for r in rows]

    def get_payment_chart_month(self, year: int, month: int):
        """
        Número diario de pagos en un mes específico.
        """
        rows = (
            self.db.query(
                extract("day", Payment.paid_at).label("dia"),
                func.count(Payment.id).label("total")
            )
            .filter(
                extract("year", Payment.paid_at) == year,
                extract("month", Payment.paid_at) == month
            )
            .group_by("dia")
            .order_by("dia")
            .all()
        )
        return [{"dia": int(r.dia), "total": r.total} for r in rows]

    def list_payments_general(self):
        """
        Listado de todos los pagos con:
         - invoice_number
         - payer_document
         - payment_date
         - reference_code
         - payment_method
         - paid_amount
         - payment_status_id   (igual al texto del status)
         - payment_status_name (texto del status)
        """
        U = aliased(User)

        q = (
            self.db.query(
                Invoice.reference_code.label("invoice_number"),
                U.document_number.label("payer_document"),
                Payment.paid_at.label("payment_date"),
                Payment.reference_code.label("reference_code"),
                Payment.payment_method.label("payment_method"),
                Payment.amount.label("paid_amount"),
                Payment.status.label("payment_status_id"),   # repetimos el código
                Payment.status.label("payment_status_name")  # y el nombre
            )
            .select_from(Payment)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .outerjoin(U, Invoice.user_id == U.id)
            .order_by(Payment.paid_at.desc())
        )

        return [row._asdict() for row in q.all()]


    def get_payment_detail(self, payment_id: int):
        """
        Detalle de un pago:
         - payment_method
         - payer_name
         - transaction_amount
         - payment_status_id   (igual al texto del status)
         - payment_status_name (texto del status)
         - payment_date
         - reference_code
         - payer_email
        """
        pago: Payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
        if not pago:
            raise HTTPException(status_code=404, detail="Pago no encontrado")

        # Nombre del pagador vía invoice.user_id
        payer_name = None
        if pago.invoice_id:
            inv = self.db.query(Invoice).get(pago.invoice_id)
            if inv and inv.user_id:
                usr = self.db.query(User).get(inv.user_id)
                payer_name = f"{usr.name} {usr.first_last_name} {usr.second_last_name}" if usr else None

        return {
            "payment_method":       pago.payment_method,
            "payer_name":           payer_name,
            "transaction_amount":   float(pago.amount),
            "payment_status_id":    pago.status,  # texto como “id”
            "payment_status_name":  pago.status,  # mismo texto como “nombre”
            "payment_date":         pago.paid_at,
            "reference_code":       pago.reference_code,
            "payer_email":          pago.payer_email,
        }
    
    # --- Paginación y listados (sin filtros; frontend los aplica) ------------

    def list_invoices(self, offset: int = 0, limit: int = 100):
        """
        Devuelve facturas en orden descendente de fecha, con paginación.
        """
        return (
            self.db.query(Invoice)
               .order_by(Invoice.issuance_date.desc())
               .offset(offset)
               .limit(limit)
               .all()
        )

    def list_payments(self, offset: int = 0, limit: int = 100):
        """
        Devuelve pagos (transacciones) en orden descendente de fecha, paginados.
        """
        return (
            self.db.query(Payment)
               .order_by(Payment.paid_at.desc())
               .offset(offset)
               .limit(limit)
               .all()
        )
