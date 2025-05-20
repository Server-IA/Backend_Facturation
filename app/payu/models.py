from sqlalchemy import JSON, Column, Float, Integer, String, Numeric, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Invoice(Base):
    __tablename__ = "invoice"

    id = Column(Integer, primary_key=True, index=True)
    reference_code = Column(String(50), unique=True, nullable=False)
    client_name = Column(String(128), nullable=False)
    client_email = Column(String(128), nullable=False)
    issuance_date = Column(DateTime, default=datetime.utcnow)
    expiration_date = Column(DateTime, nullable=False)
    invoiced_period = Column(String(32), nullable=False)
    billing_start_date = Column(DateTime, nullable=False)
    billing_end_date = Column(DateTime, nullable=False)
    total_amount = Column(Float, nullable=False)
    lot_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    status = Column(String(20), default="pendiente")
    pdf_url = Column(String(500), nullable=True)
    xml_url = Column(String(500), nullable=True)


    # Nuevos campos para Factus
    factus_number = Column(String(50), nullable=True)         # Ej. SETP990012947
    cufe = Column(String(128), nullable=True)
    public_url = Column(String(500), nullable=True)           # URL pública de la factura
    qr_url = Column(Text, nullable=True)                      # Imagen en base64 o URL del código QR
    dian_status = Column(String(50), nullable=True)           # Estado DIAN: aceptada, rechazada...
    zip_sent_at = Column(DateTime, nullable=True)             # Fecha de envío del ZIP al cliente
    payload = Column(JSON, nullable=False)

    # Relaciones
    # payments = relationship("Payment", backref="invoice")
    # logs = relationship("PaymentLog", backref="invoice")
    # concepts = relationship("InvoiceConcept", backref="invoice")

    def __repr__(self):
        return f"<Invoice #{self.id} - {self.reference_code}>"

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=True)
    reference_code = Column(String(50), index=True)
    transaction_id = Column(String(50))
    payment_method = Column(String(20))  # Ej: PSE
    status = Column(String(20))  # Aprobado, Rechazado, Pendiente
    amount = Column(Numeric(12, 2))
    currency = Column(String(5))
    payer_email = Column(String(100))
    paid_at = Column(DateTime, default=datetime.utcnow)

    # invoice = relationship("Invoice", backref="payments")

class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=True)
    reference_code = Column(String(50), index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
