import os
from fastapi.responses import JSONResponse
import httpx
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import text
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

    def generate_invoice_from_payment(self, payment: Payment, user):
        invoice = self.db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()

        if not invoice:
            raise HTTPException(status_code=404, detail="Factura no encontrada para este pago")
        
        items = []
        concepts = self.get_concepts_invoice(invoice.id)

        for concept in concepts:
            
            item = {
                "code_reference": concept["code_reference"] or "0000",  # Código del concepto, o uno genérico si no hay
                "name": concept["concept_name"] or "Concepto sin nombre",
                "quantity": concept["quantity"],
                # "discount_rate": 0,
                "discount_rate": 100 if float(concept["price"]) < 0 else 0,
                "price": abs(float(concept["price"])),
                "tax_rate": "0.00",  # Puedes ajustar si manejas impuestos
                "unit_measure_id": 70,
                "standard_code_id": 1,
                "is_excluded": 0,
                "tribute_id": 1,
                "withholding_taxes": []
            }
            items.append(item)

        try:
            token = self.obtener_token_factus()

            payload = {
                "numbering_range_id": 8,  # Confirmado por tu sandbox
                "reference_code": invoice.reference_code+'dfsdfsdfsdf',
                "observation": "",
                "payment_form": "1",  # Contado
                "payment_due_date": (invoice.expiration_date or datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
                "payment_method_code": "10",  # Transferencia
                "billing_period": {
                    "start_date": invoice.billing_start_date.strftime("%Y-%m-%d"),
                    "start_time": "00:00:00",
                    "end_date": invoice.billing_end_date.strftime("%Y-%m-%d") if invoice.billing_start_date else (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
                    "end_time": "23:59:59"
                },
                "customer": {
                    "identification": str(user["user_identification"]),
                    "dv": "3",
                    "company": "",
                    "trade_name": "",
                    "names": invoice.client_name,
                    "address": user["user_address"],
                    "email": invoice.client_email,
                    "phone": user["user_phone"],
                    "legal_organization_id": "2",
                    "tribute_id": "21",
                    "identification_document_id": "3",
                    "municipality_id": "980"
                },
                "items": items
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
        
    def get_concepts_invoice(self, invoice_id: int):
        try:
            sql = text("""
                SELECT
                    CONCAT('CON-', c.id) AS code_reference,
                    c.nombre AS concept_name,
                    CASE WHEN c.scope_id = 1 THEN 1 ELSE cm.final_volume END AS quantity,
                    ic.total_amount AS price
                FROM invoice_concept ic
                INNER JOIN invoice i ON i.id = ic.invoice_id
                INNER JOIN concepts c ON c.id = ic.concept_id
                LEFT JOIN consumption_measurements cm ON cm.id = ic.consumption_measurement_id
                WHERE i.id = :invoice_id
            """)
            result = self.db.execute(sql, {"invoice_id": invoice_id})
            rows = result.fetchall()

            concepts = []
            for row in rows:
                data = dict(row._mapping)
                data["quantity"] = int(data["quantity"])  # convertir Decimal a float
                data["price"] = float(data["price"])
                concepts.append(data)

            return concepts

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"message": str(e)}}
            )
