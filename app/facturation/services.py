# services.py
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pandas as pd
from app.facturation.models import Concept, Lot , ConsumptionMeasurement, Request , InvoiceConcept , ConceptType, ScopeType
from app.facturation.schemas import ConceptCreate, ConceptUpdate , PredictInput
from app.payu.models import Invoice, Payment
from app.ml import (
     get_models
)


class MLService:
    def __init__(
        self,
        db: Session,
        modelo_consumo_path: str = None,
        modelo_lluvia_path: str = None,
        modelo_clasificacion_path: str = None,
        columnas_path: str = None,
        rain_sensitivity: float = 0.1,
        scaler_path: str = None
    ):
        self.db = db
        # carpeta donde está este archivo
        base_dir = Path(__file__).resolve().parent.parent  # sube un nivel para llegar a la raíz

        # si no te pasan ruta, la construyes aquí
        self.modelo_consumo_path = modelo_consumo_path or str(base_dir / "ml_models" / "modelo_consumo.pkl")
        self.modelo_lluvia_path = modelo_lluvia_path or str(base_dir / "ml_models" / "modelo_lluvia.pkl")
        self.modelo_clasificacion_path = modelo_clasificacion_path or str(base_dir / "ml_models" / "modelo_clasificacion.pkl")
        self.columnas_path = columnas_path or str(base_dir / "ml_models" / "columnas_esperadas.pkl")

        # carga los modelos
        self.m_cons = joblib.load(self.modelo_consumo_path)
        self.m_rain = joblib.load(self.modelo_lluvia_path)
        self.m_clas = joblib.load(self.modelo_clasificacion_path)
        self.cols   = joblib.load(self.columnas_path)
        self.scaler = joblib.load(scaler_path) if scaler_path else None
        self.rain_sensitivity = rain_sensitivity

        # Si tienes un scaler (MinMax o Standard), cárgalo
        self.scaler = joblib.load(scaler_path) if scaler_path else None

    def predict_consumption(self, payload: PredictInput):
        """
        Recibe los datos de temperatura, humedad, etc., hace predicción
        y devuelve:
         - consumo_base: predicción cruda
         - historical_avg: promedio histórico si hay lot_id
         - lluvia: predicción de lluvia
         - consumo_ajustado: con factor de clase y lluvia
        """
        try:
            # 1) Convertir el payload en DataFrame
            df = pd.DataFrame([payload.dict()])

            # 2) Dummy-encoding de variables categóricas
            df = pd.get_dummies(df, columns=["TipoCultivo", "TipoTierra"], drop_first=True)

            # 3) Añadir columnas faltantes y reordenar
            for c in self.cols:
                if c not in df.columns:
                    df[c] = 0
            df = df[self.cols]

            # 4) Escalado (si aplica)
            if self.scaler:
                df_scaled = pd.DataFrame(self.scaler.transform(df), columns=self.cols)
            else:
                df_scaled = df

            # 5) Promedio histórico de consumo (si vienen datos de lot_id)
            historical_avg = None
            if payload.lot_id is not None:
                historical_avg = (
                    self.db.query(func.avg(ConsumptionMeasurement.final_volume))
                      .join(Request, Request.id == ConsumptionMeasurement.request_id)
                      .filter(Request.lot_id == payload.lot_id)
                      .scalar()
                )
                # redondear para salida amigable
                historical_avg = round(historical_avg or 0, 2)

            # 6) Predicción base de consumo
            consumo_base = float(self.m_cons.predict(df_scaled)[0])

            # 7) Predicción de lluvia
            lluvia = float(self.m_rain.predict(df_scaled)[0])

            # 8) Predicción de clase de cultivo y factor
            clase = self.m_clas.predict(df_scaled)[0]
            factores_clase = {"A": 1.00, "B": 1.10, "C": 0.90}
            factor = factores_clase.get(str(clase), 1.0)

            # 9) Ajuste final restando efecto lluvia y aplicando factor de clase
            consumo_ajustado = (consumo_base - lluvia * self.rain_sensitivity) * factor

            # 10) Devolver todos los resultados redondeados
            return {
                "prediccion_consumo_base": round(consumo_base, 2),                # Consumo estimado sin ajustes
                "promedio_historico_consumo": historical_avg,                     # Promedio real del lote (historical_avg_consumption)
                "prediccion_lluvia_mm": round(lluvia, 2),                         # Lluvia estimada por el modelo
                "factor_ajuste_por_clase": factor,                                # Ajuste según clase de cultivo
                "consumo_ajustado_final": round(consumo_ajustado, 2),             # Consumo luego de restar lluvia y aplicar factor
            }

        except Exception as e:
            # Un único manejo de errores
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo calcular la predicción de consumo: {e}"
            )
    



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
        
    def list_concept_types(self):
        """
        Devuelve todos los tipos de concepto ordenados por nombre.
        """
        return (
            self.db
               .query(ConceptType)
               .order_by(ConceptType.name)
               .all()
        )

    def list_scope_types(self):
        """
        Devuelve todos los scopes de alcance ordenados por nombre.
        """
        return (
            self.db
               .query(ScopeType)
               .order_by(ScopeType.name)
               .all()
        )

    def create_concept(self, payload: ConceptCreate):
        """
        Crea un nuevo Concept. El estado viene por defecto (Activo=27) si no se especifica.
        Valida reglas de negocio según scope.
        """
        try:
            # 1) Validar estado_id o asignar default Activo=27
            estado_id = payload.estado_id if getattr(payload, 'estado_id', None) in (27, 28) else 27

            # 2) Validar scope General (1): no predio ni lote
            if payload.scope_id == 1 and (payload.predio_id or payload.lote_id):
                raise HTTPException(400, "No puede especificar predio_id ni lote_id cuando scope es 'General'")

            # 3) Validar scope Específico (2): predio y lote obligatorios y relacionados
            if payload.scope_id == 2:
                if payload.predio_id is None or payload.lote_id is None:
                    raise HTTPException(400, "predio_id y lote_id son obligatorios cuando scope es 'Específico'")
                lote = self.db.get(Lot, payload.lote_id)
                if not lote:
                    raise HTTPException(400, "Lote no encontrado")
                # lote.properties es relación PropertyLot -> Property
                predio_ids = [pl.property_id for pl in lote.properties]
                if payload.predio_id not in predio_ids:
                    raise HTTPException(400, "El lote no está asociado al predio indicado")

            # 4) Crear objeto Concept
            data = payload.model_dump(exclude_unset=True)
            data['estado_id'] = estado_id
            concept = Concept(**data)

            self.db.add(concept)
            self.db.commit()
            self.db.refresh(concept)
            return concept

        except HTTPException:
            raise
        except Exception as e:
            msg = str(e)
            # Manejo de violaciones FK
            if 'concepts_scope_id_fkey' in msg:
                raise HTTPException(400, "scope_id no existe")
            if 'concepts_tipo_id_fkey' in msg:
                raise HTTPException(400, "tipo_id no existe")
            if 'concepts_predio_id_fkey' in msg:
                raise HTTPException(400, "predio_id no existe")
            if 'concepts_lote_id_fkey' in msg:
                raise HTTPException(400, "lote_id no existe")
            raise HTTPException(500, msg)

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
            concept = self.db.query(Concept).filter(Concept.lote_id == invoice.lot_id).first()

            total = 0
            for row in consumptions:
                final_volume = row.final_volume
                concept_total = 0

                if concept.tipo_id == 1:
                    concept_total = final_volume + concept.valor
                elif concept.tipo_id == 2:
                    concept_total = final_volume - concept.valor
                elif concept.tipo_id == 3:
                    concept_total = final_volume * concept.valor
                elif concept.tipo_id == 4 and concept.valor != 0:
                    concept_total = final_volume / concept.valor
                else:
                    concept_total = final_volume * concept.valor

                total += concept_total

                # 3. Actualizar el consumo usando el ORM
                consumo_obj = self.db.query(ConsumptionMeasurement).get(row.id)
                consumo_obj.invoice_id = invoice.id
                self.db.add(consumo_obj)

            invoice.total_amount = total
            self.db.commit()
            self.db.refresh(invoice)

        except Exception as e:
            raise Exception(f"Error linking consumptions: {e}")

    