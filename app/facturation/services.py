# services.py
from datetime import datetime, timedelta
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.facturation.models import Concept, ConsumptionMeasurement, InvoiceConcept, Lot
from app.facturation.schemas import ConceptCreate, ConceptUpdate
from app.payu.models import Invoice, Payment


class FacturationService:
    def __init__(self, db: Session):
        self.db = db

    def list_concepts(self):
        try:
            conceptos = (
                self.db
                    .query(Concept)
                    .join(Concept.scope)
                    .join(Concept.tipo)
                    .join(Concept.estado)
                    .outerjoin(Concept.property)
                    .outerjoin(Concept.lot)
                    .all()
            )
            if not conceptos:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "data": {"title": "Concepts", "message": "No se encontraron conceptos."}}
                )

            result = []
            for c in conceptos:
                result.append({
                    "id": c.id,
                    "nombre": c.nombre,
                    "descripcion": c.descripcion,
                    "valor": str(c.valor),
                    "scope_id":   c.scope.id,
                    "scope_name": c.scope.name,
                    "tipo_id":    c.tipo.id,
                    "tipo_name":  c.tipo.name,
                    "estado_id":  c.estado.id,
                    "estado_name": getattr(c.estado, "name", str(c.estado.id)),
                    "predio_id":  c.property.id  if c.property else None,
                    "predio_name": c.property.name if c.property else None,
                    "lote_id":    c.lot.id       if c.lot else None,
                    "lote_name":  c.lot.name     if c.lot else None,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                })
            return JSONResponse(status_code=200, content={"success": True, "data": result})

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"title": "Error al listar conceptos", "message": str(e)}}
            )

    def create_concept(self, payload: ConceptCreate):
        try:
            # Validar estado_id o asignar default Activo=27
            if payload.estado_id is None:
                estado_id = 27
            elif payload.estado_id in (27, 28):
                estado_id = payload.estado_id
            else:
                raise HTTPException(
                    status_code=400,
                    detail="estado_id inválido: sólo se permiten 27 (Activo) o 28 (Inactivo)"
                )

            # Validar scope General (1): no se permiten predio/lote
            if payload.scope_id == 1 and (payload.predio_id or payload.lote_id):
                raise HTTPException(400, "No puede especificar predio_id ni lote_id cuando scope es 'General'")

            if payload.scope_id == 2:
                if payload.predio_id is None or payload.lote_id is None:
                    raise HTTPException(400, "predio_id y lote_id son obligatorios cuando scope es 'Específico'")
                lote = self.db.get(Lot, payload.lote_id)
                if not lote:
                    raise HTTPException(400, "Lote no encontrado")
                # Validar many-to-many via property_lot
                predio_ids = [prop.id for prop in lote.properties]
                if payload.predio_id not in predio_ids:
                    raise HTTPException(400, "El lote no está asociado al predio indicado")

            # Construir objeto usando estado_id validado
            data = payload.model_dump(exclude_unset=True)
            data['estado_id'] = estado_id
            obj = Concept(**data)

            self.db.add(obj)
            self.db.commit()
            self.db.refresh(obj)

            return JSONResponse(status_code=201, content={"success": True, "data": jsonable_encoder(obj)})

        except HTTPException as he:
            return JSONResponse(
                status_code=he.status_code,
                content={"success": False, "data": {"title": "Validación", "message": he.detail}}
            )
        except Exception as e:
            msg = str(e)
            # Manejo de violaciones de FK (scope, tipo, predio, lote)
            if 'concepts_scope_id_fkey' in msg:
                title, message = "Error referencial", "scope_id no existe"
            elif 'concepts_tipo_id_fkey' in msg:
                title, message = "Error referencial", "tipo_id no existe"
            elif 'concepts_predio_id_fkey' in msg:
                title, message = "Error referencial", "predio_id no existe"
            elif 'concepts_lote_id_fkey' in msg:
                title, message = "Error referencial", "lote_id no existe"
            else:
                return JSONResponse(status_code=500, content={"success": False, "data": {"title": "Error al crear concepto", "message": msg}})
            return JSONResponse(status_code=400, content={"success": False, "data": {"title": title, "message": message}})


    def update_concept(self, concept_id: int, payload: ConceptUpdate):
        try:
            obj = self.db.get(Concept, concept_id)
            if not obj:
                raise HTTPException(404, "Concepto no encontrado")

            data = payload.model_dump(exclude_unset=True)
            scope    = data.get("scope_id", obj.scope_id)
            predio   = data.get("predio_id", obj.predio_id)
            lote_id  = data.get("lote_id",   obj.lote_id)

            # Rechazar predio/lote si cambian a General
            if scope == 1 and (predio or lote_id):
                raise HTTPException(
                    status_code=400,
                    detail="No puede especificar predio_id ni lote_id cuando scope es 'General'"
                )
            # Validar específico
            if scope == 2:
                if predio is None or lote_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="predio_id y lote_id son obligatorios cuando scope es 'Específico'"
                    )
                lote = self.db.get(Lot, lote_id)
                if not lote or lote.property_id != predio:
                    raise HTTPException(
                        status_code=400,
                        detail="El lote no pertenece al predio indicado"
                    )

            for k, v in data.items():
                setattr(obj, k, v)
            self.db.commit()
            self.db.refresh(obj)
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": jsonable_encoder(obj)}
            )

        except HTTPException as he:
            return JSONResponse(
                status_code=he.status_code,
                content={"success": False, "data": {"title": "Validación", "message": he.detail}}
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"title": "Error al actualizar concepto", "message": str(e)}}
            )
        
    def enable_concept(self, concept_id: int):
        try:
            obj = self.db.get(Concept, concept_id)
            if not obj:
                raise HTTPException(404, "Concepto no encontrado")
            obj.estado_id = 27  # Activo
            self.db.commit()
            self.db.refresh(obj)
            return JSONResponse(status_code=200, content={"success": True, "data": jsonable_encoder(obj)})
        except HTTPException as he:
            return JSONResponse(status_code=he.status_code, content={"success": False, "data": {"title": "Validación", "message": he.detail}})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "data": {"title": "Error al habilitar concepto", "message": str(e)}})

    def disable_concept(self, concept_id: int):
        try:
            obj = self.db.get(Concept, concept_id)
            if not obj:
                raise HTTPException(404, "Concepto no encontrado")
            obj.estado_id = 28  # Inactivo
            self.db.commit()
            self.db.refresh(obj)
            return JSONResponse(status_code=200, content={"success": True, "data": jsonable_encoder(obj)})
        except HTTPException as he:
            return JSONResponse(status_code=he.status_code, content={"success": False, "data": {"title": "Validación", "message": he.detail}})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "data": {"title": "Error al inhabilitar concepto", "message": str(e)}})
        
class InvoiceService:
    def __init__(self, db):
        self.db = db

    def get_invoice_detail(self, invoice_id: int):
        try:
            invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if not invoice:
                raise HTTPException(status_code=404, detail="Factura no encontrada")
            
            payment = self.db.query(Payment).filter(Payment.invoice_id == invoice_id).first()
            data_payment = {}
            if payment:
                data_payment = {
                    "payment_id": payment.id,
                    "payment_method": payment.payment_method,
                    "payment_date": payment.paid_at,
                    "amount": payment.amount,
                    "reference_code": payment.reference_code,
                    "transaction_id": payment.transaction_id,
                    "payer_email": payment.payer_email
                }
            
            lots = self.db.query(Lot).filter(Lot.id == invoice.lot_id).first()
            if not lots:
                raise HTTPException(status_code=404, detail="Lote no encontrado")
            
            user_lots = self.get_user_info_by_lot(lots.id)
            
            response_data = {
                "invoice": {
                    "factura_id": invoice.id,
                    "reference_code": invoice.reference_code,
                    "issuance_date": invoice.issuance_date,
                    "expiration_date": invoice.expiration_date,
                    "invoiced_period": invoice.invoiced_period,
                    "client_name": invoice.client_name,
                    "client_email": invoice.client_email,
                    "total_amount": invoice.total_amount,
                    "lot_id": invoice.lot_id,
                    "status": invoice.status,
                    "factus_number": invoice.factus_number,
                    "cufe": invoice.cufe,
                    "public_url": invoice.public_url,
                    "qr_url": invoice.qr_url,
                    "dian_status": invoice.dian_status,
                    "zip_sent_at": invoice.zip_sent_at,
                },
                "payment": data_payment,
                "user_lots" : user_lots              
            }

            return JSONResponse(status_code=200, content={"success": True, "data": jsonable_encoder(response_data)})

        except HTTPException as he:
            return JSONResponse(status_code=he.status_code, content={"success": False, "data": {"title": "Validación", "message": he.detail}})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "data": {"title": "Error al obtener factura", "message": str(e)}})
        
    def get_user_info_by_lot(self, lot_id: int):
        try:
            sql = text("""
                SELECT 
                    u.id AS user_id,
                    CONCAT(u.name, ' ', u.first_last_name, ' ', u.second_last_name) AS user_name,
                    u.email AS user_email,
                    u.document_number AS user_identification,
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
        
    @staticmethod
    def generate_reference_code(db: Session) -> str:
        today = datetime.utcnow().strftime("%Y%m%d")  # ej: 20250513
        count = db.query(func.count(Invoice.id)).scalar() + 1  # conteo total actual
        return f"DISR-{today}-{count:04d}"  # ej: DISR-20250513-0007
    
    def create_invoice(self, payment_data: dict):
        try:
            # validar si ya existe una facturacion pendiente para ese lote
            lot_id = payment_data["lot_id"]
            validateInvoice = self.db.query(Invoice).filter(Invoice.lot_id == lot_id).first()
            if validateInvoice:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "data": {"title": "Facturación pendiente", "message": "Ya existe una facturación pendiente para este lote."},
                        },
                    )
            
            user_lots = self.get_user_info_by_lot(payment_data["lot_id"])
            # 1. Generar código de referencia único
            reference_code = self.generate_reference_code(self.db)

            # Obtener el primer día del mes actual
            first_day_this_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # billing_start_date: primer día del mes anterior
            billing_start_date = (first_day_this_month - timedelta(days=1)).replace(day=1)

            # billing_end_date: último día del mes anterior
            billing_end_date = first_day_this_month - timedelta(seconds=1)

            invoice = Invoice(
                reference_code=reference_code,
                user_id=user_lots["user_id"],
                client_name=user_lots['user_name'],
                client_email=user_lots['user_email'],
                billing_start_date=billing_start_date,
                billing_end_date=billing_end_date,
                issuance_date=datetime.utcnow(),
                expiration_date=datetime.utcnow() + timedelta(days=15),
                invoiced_period=30,
                total_amount=0,
                lot_id=payment_data["lot_id"],
                status="pendiente"
            )

            self.db.add(invoice)
            self.db.commit()
            self.db.refresh(invoice)

            self.link_consumptions_and_calculate_total(invoice)

            return JSONResponse(status_code=200, content={"success": True, "data": jsonable_encoder(invoice)})

        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "data": {"message": str(e)}})
        
    # Assuming each unit of consumption costs 100
    def link_consumptions_and_calculate_total(self, invoice):
        try:
            sql = text("""
                SELECT cm.*
                FROM consumption_measurements cm
                INNER JOIN request r ON r.id = cm.request_id  
                WHERE cm.invoice_id IS NULL
                AND cm.created_at >= :start_date
                AND r.lot_id = :lot_id
                AND cm.created_at <= :end_date
            """)

            result = self.db.execute(sql, {
                "lot_id": invoice.lot_id,
                "start_date": invoice.billing_start_date,
                "end_date": invoice.billing_end_date
            })

            consumptions = result.fetchall()

            if not consumptions:
                return  # No consumptions to process

            # consultar los conceptos por lote en Concept y los relacionados
            concepts = self.db.query(Concept).filter(
                or_(
                    Concept.lote_id == invoice.lot_id,
                    Concept.scope_id == 1
                )
            ).all()

            total = 0
            for row in consumptions:
                final_volume = row.final_volume
                concept_total_consump = 0
                for concept in concepts:
                    concept_total = 0
                    if concept.tipo_id == 1:
                        concept_total = concept_total + concept.valor
                    elif concept.tipo_id == 2:
                        concept_total = concept_total - concept.valor
                    elif concept.tipo_id == 3:
                        concept_total = concept_total + (final_volume * concept.valor)
                    elif concept.tipo_id == 4 and concept.valor != 0:
                        concept_total = concept_total / concept.valor
                    else:
                        concept_total = concept_total + (final_volume * concept.valor)

                    invoice_concept = InvoiceConcept(
                        invoice_id=invoice.id,
                        concept_id=concept.id,
                        total_amount=concept_total,
                        consumption_measurement_id=row.id
                    )

                    self.db.add(invoice_concept)
                    self.db.commit()
                    self.db.refresh(invoice_concept)

                    concept_total_consump += concept_total

                total += concept_total_consump

                # 3. Actualizar el consumo usando el ORM
                consumo_obj = self.db.query(ConsumptionMeasurement).get(row.id)
                consumo_obj.invoice_id = invoice.id
                self.db.add(consumo_obj)

            invoice.total_amount = total
            self.db.commit()
            self.db.refresh(invoice)

        except Exception as e:
            raise Exception(f"Error linking consumptions: {e}")

    