# app/routes/billing.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.billing.services import BillingService
from app.database import get_db

router = APIRouter(prefix="/billing", tags=["Facturación"])

# --- Facturas ---

@router.get("/invoices/summary")
def invoice_summary(db: Session = Depends(get_db)):
    emitidas, pagadas, pendientes, vencidas = BillingService(db).get_invoice_counts()
    return {
        "emitidas":   emitidas,
        "pagadas":    pagadas,
        "pendientes": pendientes,
        "vencidas":   vencidas
    }

@router.get("/invoices/chart/{year}")
def invoice_chart_year(year: int, db: Session = Depends(get_db)):
    return BillingService(db).get_invoice_chart_year(year)

@router.get("/invoices/amount/{year}/{month}")
def invoice_amount_month(year: int, month: int, db: Session = Depends(get_db)):
    return {"total_facturado": BillingService(db).get_invoice_amount_month(year, month)}

@router.get("/invoices")
def get_invoices(offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return BillingService(db).list_invoices(offset, limit)

@router.get("/invoices/general")
def get_invoices_general(offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    svc = BillingService(db)
    data = svc.list_invoices_general(offset, limit)
    return {"success": True, "data": data}


# --- Transacciones (Pagos) ---

@router.get("/payments/summary/{year}/{month}")
def payment_summary(year: int, month: int, db: Session = Depends(get_db)):
    return BillingService(db).get_payment_totals(year, month)

@router.get("/payments/chart/year/{year}")
def payment_chart_year(year: int, db: Session = Depends(get_db)):
    return BillingService(db).get_payment_chart_year(year)

@router.get("/payments/chart/{year}/{month}")
def payment_chart_month(year: int, month: int, db: Session = Depends(get_db)):
    return BillingService(db).get_payment_chart_month(year, month)

@router.get("/payments")
def get_payments(offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return BillingService(db).list_payments(offset, limit)
