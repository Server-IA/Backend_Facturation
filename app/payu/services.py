import hashlib
import os
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.payu.models import Invoice, Payment, PaymentLog
from app.factus.services import FactusService

# Cargar .env una sola vez
load_dotenv()

class PayUService:
    def __init__(self, db: Session):
        self.db = db

    def get_pse_bank_list(self):
        try:
            PAYU_ENV_URL = os.getenv("PAYU_ENV_URL")
            PAYU_API_LOGIN = os.getenv("PAYU_API_LOGIN")
            PAYU_API_KEY = os.getenv("PAYU_API_KEY")

            if not all([PAYU_ENV_URL, PAYU_API_LOGIN, PAYU_API_KEY]):
                raise HTTPException(500, "Variables de entorno PayU no configuradas correctamente")

            url = f"{PAYU_ENV_URL}/payments-api/4.0/service.cgi"
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            payload = {
                "language": "es",
                "command": "GET_BANKS_LIST",
                "merchant": {
                    "apiLogin": PAYU_API_LOGIN,
                    "apiKey": PAYU_API_KEY
                },
                "test": False,
                "bankListInformation": {
                    "paymentMethod": "PSE",
                    "paymentCountry": "CO"
                }
            }

            response = httpx.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "SUCCESS":
                raise HTTPException(400, f"Error desde PayU: {data.get('error', 'Desconocido')}")

            return JSONResponse(status_code=200, content={"success": True, "data": data.get("banks", [])})

        except HTTPException as he:
            return JSONResponse(
                status_code=he.status_code,
                content={"success": False, "data": {"title": "Validación", "message": he.detail}}
            )
        except httpx.RequestError as e:
            return JSONResponse(
                status_code=502,
                content={"success": False, "data": {"title": "Fallo de conexión con PayU", "message": str(e)}}
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"title": "Error inesperado", "message": str(e)}}
            )

    @staticmethod
    def generate_signature(api_key, merchant_id, reference_code, amount, currency):
        amount_formatted = f"{float(amount):.2f}"
        raw_string = f"{api_key}~{merchant_id}~{reference_code}~{amount_formatted}~{currency}"
        return hashlib.md5(raw_string.encode("utf-8")).hexdigest()
    
    @staticmethod
    def generate_reference_code(db: Session) -> str:
        today = datetime.utcnow().strftime("%Y%m%d")  # ej: 20250513
        count = db.query(func.count(Invoice.id)).scalar() + 1  # conteo total actual
        return f"DISR-{today}-{count:04d}"  # ej: DISR-20250513-0007

    def create_pse_payment(self, payment_data: dict):
        try:
            # Obtener variables de entorno
            PAYU_ENV_URL = os.getenv("PAYU_ENV_URL")
            PAYU_API_LOGIN = os.getenv("PAYU_API_LOGIN")
            PAYU_API_KEY = os.getenv("PAYU_API_KEY")
            PAYU_ACCOUNT_ID = os.getenv("PAYU_ACCOUNT_ID")
            PAYU_MERCHANT_ID = os.getenv("PAYU_MERCHANT_ID")
            CURRENCY = payment_data.get("currency", "COP")
            AMOUNT = float(payment_data["amount"])

            if not all([PAYU_ENV_URL, PAYU_API_LOGIN, PAYU_API_KEY, PAYU_ACCOUNT_ID, PAYU_MERCHANT_ID]):
                raise HTTPException(500, "Variables de entorno PayU incompletas")

            # 1. Generar código de referencia único
            reference_code = self.generate_reference_code(self.db)

            # 2. Crear factura antes de intentar el pago
            invoice = Invoice(
                reference_code=reference_code,
                client_name=payment_data["payer"]["fullName"],
                client_email=payment_data["payer"]["emailAddress"],
                issuance_date=datetime.utcnow(),
                expiration_date=datetime.utcnow() + timedelta(days=15),
                invoiced_period=payment_data["detailInvoice"]["invoiced_period"],
                total_amount=AMOUNT,
                lot_id=payment_data["detailInvoice"]["lot_id"],
                status="pendiente"
            )
            self.db.add(invoice)
            self.db.commit()
            self.db.refresh(invoice)

            # 3. Generar firma para PayU
            signature = self.generate_signature(
                api_key=PAYU_API_KEY,
                merchant_id=PAYU_MERCHANT_ID,
                reference_code=reference_code,
                amount=AMOUNT,
                currency=CURRENCY
            )

            # 4. Preparar payload para PayU
            url = f"{PAYU_ENV_URL}/payments-api/4.0/service.cgi"
            headers = {"Content-Type": "application/json", "Accept": "application/json"}

            payload = {
                "language": "es",
                "command": "SUBMIT_TRANSACTION",
                "merchant": {
                    "apiLogin": PAYU_API_LOGIN,
                    "apiKey": PAYU_API_KEY
                },
                "transaction": {
                    "order": {
                        "accountId": PAYU_ACCOUNT_ID,
                        "referenceCode": reference_code,
                        "description": payment_data.get("description", "Pago por PSE"),
                        "language": "es",
                        "signature": signature,
                        "notifyUrl": payment_data["notifyUrl"],
                        "additionalValues": {
                            "TX_VALUE": {"value": AMOUNT, "currency": CURRENCY},
                            "TX_TAX": {"value": 0, "currency": CURRENCY},
                            "TX_TAX_RETURN_BASE": {"value": 0, "currency": CURRENCY}
                        },
                        "buyer": payment_data["buyer"],
                        "shippingAddress": payment_data["shippingAddress"]
                    },
                    "payer": payment_data["payer"],
                    "extraParameters": {
                        "RESPONSE_URL": payment_data["responseUrl"],
                        "PSE_REFERENCE1": "127.0.0.1",
                        "FINANCIAL_INSTITUTION_CODE": payment_data["bankCode"],
                        "USER_TYPE": "N",
                        "PSE_REFERENCE2": "CC",
                        "PSE_REFERENCE3": payment_data["payer"]["dniNumber"]
                    },
                    "type": "AUTHORIZATION_AND_CAPTURE",
                    "paymentMethod": "PSE",
                    "paymentCountry": "CO",
                    "deviceSessionId": payment_data["deviceSessionId"],
                    "ipAddress": payment_data["ipAddress"],
                    "cookie": payment_data["cookie"],
                    "userAgent": payment_data["userAgent"]
                },
                "test": False
            }

            # 5. Enviar a PayU
            response = httpx.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # 6. Guardar log de intento de pago
            log = PaymentLog(
                reference_code=reference_code,
                invoice_id=invoice.id,
                payload=data
            )
            self.db.add(log)
            self.db.commit()

            return JSONResponse(status_code=200, content={"success": True, "data": data})

        except HTTPException as he:
            return JSONResponse(
                status_code=he.status_code,
                content={"success": False, "data": {"title": "Error de validación", "message": he.detail}}
            )
        except httpx.RequestError as e:
            return JSONResponse(
                status_code=502,
                content={"success": False, "data": {"title": "Error de conexión", "message": str(e)}}
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"title": "Error inesperado", "message": str(e)}}
            )


class PayUProcessor:
    def __init__(self, db: Session):
        self.db = db

    def process_notification(self, data: dict):
        # 1. Validar si el pago ya existe por transaction_id
        if self.db.query(Payment).filter_by(transaction_id=data.get("transaction_id")).first():
            return {"message": "Ya registrado"}

        # 2. Buscar invoice_id desde el log asociado al reference_code
        reference_code = data.get("reference_sale")
        log = self.db.query(PaymentLog).filter_by(reference_code=reference_code).first()

        if not log or not log.invoice_id:
            raise HTTPException(status_code=404, detail="No se encontró la factura relacionada al pago")

        # 3. Crear registro de Payment
        pago = Payment(
            reference_code=reference_code,
            transaction_id=data.get("transaction_id"),
            payment_method="PSE",
            status=data.get("state_pol"),
            amount=float(data.get("value", 0)),
            currency=data.get("currency"),
            payer_email=data.get("email_buyer"),
            paid_at=datetime.utcnow(),
            invoice_id=log.invoice_id
        )

        self.db.add(pago)
        self.db.commit()
        self.db.refresh(pago)

        # 4. Generar factura electrónica si el estado es aprobado (4)
        if pago.status == "4":
            # pass
            factus = FactusService(self.db)
            result = factus.generate_invoice_from_payment(pago)
            return {
                "success": True,
                "message": "Pago registrado y factura generada",
                "data": result
            }

        return {
            "success": True,
            "message": "Pago registrado sin generar factura",
            "status": pago.status
        }
