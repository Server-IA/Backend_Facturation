import os
import httpx
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.payu.models import Invoice, Payment

class FactusService:
    def __init__(self, db: Session):
        self.db = db

    def obtener_token_factus(self):
        url = "https://api-sandbox.factus.com.co/oauth/token"

        payload = {
            "grant_type": "password",
            "client_id": os.getenv("FACTUS_CLIENT_ID"),
            "client_secret": os.getenv("FACTUS_CLIENT_SECRET"),
            "username": os.getenv("FACTUS_EMAIL"),
            "password": os.getenv("FACTUS_PASSWORD")
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        response = httpx.post(url, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()["access_token"]

    def generate_invoice_from_payment(self, payment: Payment):
        invoice = self.db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()

        if not invoice:
            raise HTTPException(status_code=404, detail="Factura no encontrada para este pago")

        try:
            token = self.obtener_token_factus()

            payload = {
                "numbering_range_id": 8,  # Confirmado por tu sandbox
                "reference_code": invoice.reference_code,
                "observation": "",
                "payment_form": "1",  # Contado
                "payment_due_date": (invoice.expiration_date or datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
                "payment_method_code": "10",  # Transferencia
                "billing_period": {
                    "start_date": invoice.issuance_date.strftime("%Y-%m-%d"),
                    "start_time": "00:00:00",
                    "end_date": invoice.expiration_date.strftime("%Y-%m-%d") if invoice.expiration_date else (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
                    "end_time": "23:59:59"
                },
                "customer": {
                    "identification": "123456789",
                    "dv": "3",
                    "company": "",
                    "trade_name": "",
                    "names": invoice.client_name,
                    "address": "calle generica",
                    "email": invoice.client_email,
                    "phone": "1234567890",
                    "legal_organization_id": "2",
                    "tribute_id": "21",
                    "identification_document_id": "3",
                    "municipality_id": "980"
                },
                "items": [
                    {
                        "code_reference": "12345",
                        "name": "Servicio de agua",
                        "quantity": 1,
                        "discount_rate": 0,
                        "price": float(invoice.total_amount),
                        "tax_rate": "0.00",
                        "unit_measure_id": 70,
                        "standard_code_id": 1,
                        "is_excluded": 0,
                        "tribute_id": 1,
                        "withholding_taxes": []
                    }
                ]
            }

            url = "https://api-sandbox.factus.com.co/v1/bills/validate"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            response = httpx.post(url, json=payload, headers=headers, timeout=30 )
            # print("Respuesta Factus:", response.text)
            response.raise_for_status()
            data = response.json()

            # Acceder correctamente al objeto "bill"
            factura = data.get("data", {}).get("bill", {})
            invoice.cufe = factura.get("cufe")
            invoice.qr_url = factura.get("qr")  # si agregaste el campo
            invoice.public_url = factura.get("public_url")
            invoice.status = "pagada"
            invoice.dian_status = "aceptada"
            invoice.zip_sent_at = datetime.utcnow()
            invoice.payload = data
            self.db.commit()

            return {
                "success": True,
                "invoice_id": invoice.id,
                "cufe": invoice.cufe,
                "message": data.get("message")
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
