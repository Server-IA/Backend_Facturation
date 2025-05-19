import json
import os
from fastapi.responses import JSONResponse
import httpx
import base64
import smtplib
import zipfile
from io import BytesIO
from email.message import EmailMessage
from email.utils import make_msgid
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

    def generate_invoice_from_payment(self, payment, user):
        invoice = self.db.query(Invoice).filter(Invoice.id == payment.id).first()

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
                "reference_code": invoice.reference_code,
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
            invoice.status = "pendiente"
            invoice.dian_status = "aceptada"
            invoice.zip_sent_at = datetime.utcnow()
            invoice.factus_number = factura.get("number")
            invoice.payload = data
            self.db.commit()

            # guardar facturas
            self.descargar_pdf_xml_factura(invoice.id)


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
        
    def descargar_pdf_xml_factura(self, invoice_id: int):
        try:
            invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()

            if not invoice or not invoice.public_url:
                raise HTTPException(status_code=404, detail="Factura o public_url no encontrado")

            # Obtener token de acceso
            token = self.obtener_token_factus()

            base_url = "https://api-sandbox.factus.com.co/v1/bills"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }

            # Descargar PDF (es binario)
            response_pdf = httpx.get(f"{base_url}/download-pdf/{invoice.factus_number}", headers=headers, timeout=30)
            response_pdf.raise_for_status()

            # Descargar XML
            response_xml = httpx.get(f"{base_url}/download-xml/{invoice.factus_number}", headers=headers, timeout=30)
            response_xml.raise_for_status()

            respuesta = response_xml.json()
            xml_b64 = respuesta["data"]["xml_base_64_encoded"]
            file_name = respuesta["data"]["file_name"]

            # Guardar XML
            ruta_xml = self.guardar_xml(xml_b64, file_name)

            respuesta = response_pdf.json()
            file_name = respuesta["data"]["file_name"]
            ruta_pdf = self.guardar_pdf(response_pdf.content, file_name)

            # Guardar en la base de datos
            invoice.pdf_url = ruta_xml
            invoice.xml_url = ruta_pdf
            self.db.commit()
            self.db.refresh(invoice)

            html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; background-color: #f5f6f8; padding: 30px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <img src="https://disriegos.vercel.app/assets/DisRiego-C6ldPlFt.svg" alt="Dis Riego" style="height: 40px;">
                        <h2 style="color: #218c74;">DisRiego</h2>
                    </div>

                    <p>Estimado(a) <strong>{invoice.client_name}</strong>,</p>
                    <p>Ha recibido una factura o nota electrónica. Adjunto a este correo encontrará el documento.</p>

                    <h4 style="margin-top: 30px;">Resumen del documento:</h4>
                    <p><strong>Emisor:</strong> Disriego</p>
                    <p><strong>Tipo de documento:</strong> Factura de venta</p>
                    <p><strong>Número de documento:</strong> {invoice.factus_number}</p>
                    <p><strong>Fecha de emisión:</strong> {invoice.issuance_date}</p>
                    <p><strong>Fecha de vencimiento:</strong> {invoice.expiration_date}</p>
                    <p><strong>Valor a pagar:</strong> ${invoice.total_amount}</p>

                    <p style="margin-top: 30px;">Saludos,<br>
                    El equipo de <strong>DisRiego</strong></p>

                    <div style="margin-top: 40px; background-color: #f0f0f0; padding: 15px; font-size: 12px; color: #666;">
                        Este correo fue enviado a <strong>{invoice.client_email}</strong>. Si no deseas recibir este tipo de correos, puedes gestionar tus preferencias de correo electrónico.<br><br>
                        Teléfono: 3133045345<br>
                        Dirección: Carrera 10 # 9 - 04
                    </div>
                    </div>
                </body>
                </html>
                """


            self.send_invoice_zip_by_email(
                invoice.client_email,
                "Descarga tu Factura electrónica",
                html_body,
                invoice.pdf_url,
                invoice.xml_url
            )

            return {
                "success": True,
                "pdf_url": invoice.pdf_url,
                "xml_url": invoice.xml_url
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def guardar_xml(xml_base_64: str, nombre_archivo: str, carpeta: str = "uploads/facturas"):
        carpeta = f"{carpeta}/{nombre_archivo}/"
        os.makedirs(carpeta, exist_ok=True)
        xml_bytes = base64.b64decode(xml_base_64)
        ruta = os.path.join(carpeta, f"{nombre_archivo}.xml")
        with open(ruta, "wb") as f:
            f.write(xml_bytes)
        return ruta
    
    @staticmethod
    def guardar_pdf(response_pdf_content: bytes, nombre_archivo: str, carpeta: str = "uploads/facturas"):
        # Decodificar JSON
        response_data = json.loads(response_pdf_content.decode("utf-8"))
        pdf_b64 = response_data["data"]["pdf_base_64_encoded"]
        pdf_bytes = base64.b64decode(pdf_b64)
        carpeta = f"{carpeta}/{nombre_archivo}/"
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"{nombre_archivo}.pdf")
        with open(ruta, "wb") as f:
            f.write(pdf_bytes)

        return ruta
    
    def enviar_factura_por_correo(self, destinatario: str, subject: str, body: str, pdf_path: str, xml_path: str):
        remitente = os.getenv("SMTP_EMAIL")
        clave = os.getenv("SMTP_PASSWORD")  # Usa App Password si es Gmail

        msg = EmailMessage()
        msg["From"] = remitente
        msg["To"] = destinatario
        msg["Subject"] = subject
        # msg.set_content(body)
        msg.set_content("Este correo contiene una factura electrónica adjunta.")
        msg.add_alternative(body, subtype="html")

        # Adjuntar PDF
        with open(pdf_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(pdf_path))

        # Adjuntar XML
        with open(xml_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="xml", filename=os.path.basename(xml_path))

        # Enviar correo
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remitente, clave)
            smtp.send_message(msg)

        print("Correo enviado correctamente.")

    
    def send_invoice_zip_by_email(self, recipient: str, subject: str, body: str, pdf_path: str, xml_path: str):
        sender = os.getenv("SMTP_EMAIL")
        password = os.getenv("SMTP_PASSWORD")

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        # msg.set_content(body)
        msg.set_content("Este correo contiene una factura electrónica adjunta.")
        msg.add_alternative(body, subtype="html")

        # Crear archivo ZIP en memoria
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.write(pdf_path, arcname=os.path.basename(pdf_path))
            zip_file.write(xml_path, arcname=os.path.basename(xml_path))
        zip_buffer.seek(0)

        # Adjuntar ZIP
        zip_filename = f"{os.path.splitext(os.path.basename(pdf_path))[0]}.zip"
        msg.add_attachment(zip_buffer.read(), maintype="application", subtype="zip", filename=zip_filename)

        # Enviar correo
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        print("ZIP email sent successfully.")


