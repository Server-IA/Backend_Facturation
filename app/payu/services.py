import hashlib
import os
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, text
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
            CURRENCY = "COP"

            if not all([PAYU_ENV_URL, PAYU_API_LOGIN, PAYU_API_KEY, PAYU_ACCOUNT_ID, PAYU_MERCHANT_ID]):
                raise HTTPException(500, "Variables de entorno PayU incompletas")
            
            invoice_id = payment_data["detailInvoice"]["invoice_id"]

            # 2. Crear factura antes de intentar el pago
            invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()

            # validar si la factura ya fue pagada
            if invoice.status == 'pagada':
                return JSONResponse(status_code=400, content={"success": False, "data": {"tittle" : "La factura ya fue pagada"}})

            if invoice.total_amount <= 0:
                return JSONResponse(status_code=400, content={"success": False, "data": {"title" : "La factura debe tener un monto mayor a $0 para generar la transaccion"}})

            users = self.get_user_info_by_lot(invoice.lot_id)

            # 3. Generar firma para PayU
            signature = self.generate_signature(
                api_key=PAYU_API_KEY,
                merchant_id=PAYU_MERCHANT_ID,
                reference_code=invoice.reference_code,
                amount=invoice.total_amount,
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
                        "referenceCode": invoice.reference_code,
                        "description": "Pago por PSE",
                        "language": "es",
                        "signature": signature,
                        "notifyUrl": "https://backend-facturation.onrender.com/payu/notificacion",
                        "additionalValues": {
                            "TX_VALUE": {"value": invoice.total_amount, "currency": CURRENCY},
                            "TX_TAX": {"value": 0, "currency": CURRENCY},
                            "TX_TAX_RETURN_BASE": {"value": 0, "currency": CURRENCY}
                        },
                        "buyer": {
                            "fullName": users["user_name"],
                            "emailAddress": users["user_email"],
                            "contactPhone": users["user_phone"],
                            "dniNumber": users["user_identification"],
                            "shippingAddress": {
                                "street1": "Carrera 123 # 456",
                                "street2": "",
                                "city": "Neiva",
                                "state": "Huila",
                                "country": "CO",
                                "postalCode": "410001",
                                "phone": "3001234567"
                            }
                        },
                        "shippingAddress": {
                            "street1": "Carrera 123 # 456",
                            "street2": "",
                            "city": "Neiva",
                            "state": "Huila",
                            "country": "CO",
                            "postalCode": "410001",
                            "phone": "3001234567"
                        }
                    },
                    "payer": {
                        "fullName": users["user_name"],
                        "emailAddress": users["user_email"],
                        "contactPhone": users["user_phone"],
                        "dniNumber": users["user_identification"],
                        "billingAddress": {
                            "street1": "Carrera 123 # 456",
                            "street2": "",
                            "city": "Neiva",
                            "state": "Huila",
                            "country": "CO",
                            "postalCode": "410001",
                            "phone": "3001234567"
                        }
                    },
                    "extraParameters": {
                        "RESPONSE_URL": "https://backend-facturation.onrender.com/payu/retorno",
                        "PSE_REFERENCE1": "127.0.0.1",
                        "FINANCIAL_INSTITUTION_CODE": payment_data["bankCode"],
                        "USER_TYPE": "N",
                        "PSE_REFERENCE2": "CC",
                        "PSE_REFERENCE3": users["user_identification"]
                    },
                    "type": "AUTHORIZATION_AND_CAPTURE",
                    "paymentMethod": "PSE",
                    "paymentCountry": "CO",
                    "deviceSessionId": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
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
                reference_code=invoice.reference_code,
                invoice_id=invoice.id,
                payload=data
            )
            self.db.add(log)
            self.db.commit()

            if data["transactionResponse"]["state"] == 'DECLINED':
                return JSONResponse(status_code=200, content={"success": True, "data": data["transactionResponse"]["paymentNetworkResponseErrorMessage"]})
            else:
                return JSONResponse(status_code=200, content={"success": True, "data": data["transactionResponse"]["extraParameters"]["BANK_URL"]})

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
        
    def get_user_info_by_lot(self, lot_id: int):
        try:
            sql = text("""
                SELECT 
                    u.id AS user_id,
                    CONCAT(u.name, ' ', u.first_last_name, ' ', u.second_last_name) AS user_name,
                    u.email AS user_email,
                    u.document_number AS user_identification,
                    u.phone AS user_phone,
                    u.address AS user_address,
                    l.id AS lot_id,
                    pl.property_id
                FROM lot l
                JOIN property_lot pl ON pl.lot_id = l.id
                JOIN user_property up ON up.property_id = pl.property_id
                JOIN users u ON u.id = up.user_id
                WHERE l.id = :lot_id
                LIMIT 1
            """)
            result = self.db.execute(sql, {"lot_id": lot_id})
            row = result.fetchone()

            if not row:
                return {}

            return dict(row._mapping)
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "data": {"message": str(e)}})


class PayUProcessor:
    def __init__(self, db: Session):
        self.db = db

    def process_notification(self, data: dict):
        # 1. Validar si el pago ya existe por transaction_id
        if self.db.query(Payment).filter_by(transaction_id=data.get("transaction_id")).first():
            return {"message": "Ya se encuentra registrado el pago registrado"}

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

        # 6. Guardar log de intento de pago
        log = PaymentLog(
            reference_code=reference_code,
            invoice_id=log.invoice_id,
            payload=data
        )
        self.db.add(log)
        self.db.commit()

        # 4. Generar factura electrónica si el estado es aprobado (4)
        if pago.status == "4":
            # generar envio de facturas

            return {
                "success": True,
                "message": "Pago registrado y factura generada",
                "data": pago.status
            }
        elif pago.status == "6":
            return {
                "success": True,
                "message": "Pago rechazado",
                "data": pago.status
            }
        return {
            "success": True,
            "message": "Pago registrado sin generar factura",
            "status": pago.status
        }
