# app/services/billing.py

from datetime import date
from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session , aliased
from app.payu.models       import Payment , Invoice
from app.facturation.models import PaymentInterval, PropertyLot ,PropertyUser , Property , Lot , User
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

    def list_invoices_general(self, offset: int = 0, limit: int = 100):
            """
            Devuelve listado de facturas con los campos requeridos para la vista general.
            """
            # aliases para evitar ambigüedades
            PI = aliased(PaymentInterval)
            PL = aliased(PropertyLot)
            UP = aliased(PropertyUser)
            U  = aliased(User)
            P  = aliased(Payment)

            query = (
                self.db.query(
                    Invoice.reference_code.label("invoice_number"),             # :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}
                    PL.property_id.label("property_id"),                       # :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}
                    Invoice.lot_id.label("lot_id"),
                    U.document_number.label("client_document"),
                    PI.name.label("payment_interval"),
                    Invoice.issuance_date,
                    Invoice.expiration_date,
                    Invoice.total_amount.label("amount_due"),
                    Invoice.status.label("invoice_status"),
                    P.status.label("payment_status"),
                    Invoice.dian_status.label("dian_status")
                )
                # desde invoice → lote
                .join(Lot, Invoice.lot_id == Lot.id)
                # lote → property_lot → user_property → users
                .join(PL, PL.lot_id == Lot.id)
                .join(UP, UP.property_id == PL.property_id)
                .join(U, U.id == UP.user_id)
                # lote → payment_intervals
                .join(PI, PI.id == Lot.payment_interval_id)
                # left join a pagos (puede no haber pago aún)
                .outerjoin(P, P.invoice_id == Invoice.id)
                .order_by(Invoice.issuance_date.desc())
                .offset(offset)
                .limit(limit)
            )

            # devolvemos lista de diccionarios
            return [row._asdict() for row in query.all()]
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
