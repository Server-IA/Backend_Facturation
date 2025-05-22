# services.py
from app.factus.services import FactusService
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pandas as pd
from app.facturation.models import Concept, Lot , PropertyLot, Property,PropertyUser,ConsumptionMeasurement, Request , InvoiceConcept , ConceptType, ScopeType
from app.facturation.schemas import ConceptCreate, ConceptUpdate , PredictInput
from app.payu.models import Invoice, Payment
from app.ml import (
     get_models
)
from app.utils.geo import get_altitude, get_weather_data
from app.utils.mapping import crop_to_soil_type

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
        base_dir = Path(__file__).resolve().parent.parent
        self.modelo_consumo_path = modelo_consumo_path or str(base_dir / "ml_models" / "modelo_consumo.pkl")
        self.modelo_lluvia_path = modelo_lluvia_path or str(base_dir / "ml_models" / "modelo_lluvia.pkl")
        self.modelo_clasificacion_path = modelo_clasificacion_path or str(base_dir / "ml_models" / "modelo_clasificacion.pkl")
        self.columnas_path = columnas_path or str(base_dir / "ml_models" / "columnas_esperadas.pkl")
        self.m_cons = joblib.load(self.modelo_consumo_path)
        self.m_rain = joblib.load(self.modelo_lluvia_path)
        self.m_clas = joblib.load(self.modelo_clasificacion_path)
        self.cols   = joblib.load(self.columnas_path)
        self.scaler = joblib.load(scaler_path) if scaler_path else None
        self.rain_sensitivity = rain_sensitivity

    def predict_consumption(self, payload: PredictInput):
        try:
            df = pd.DataFrame([payload.dict()])
            df = pd.get_dummies(df, columns=["TipoCultivo", "TipoTierra"], drop_first=True)
            for c in self.cols:
                if c not in df.columns:
                    df[c] = 0
            df = df[self.cols]
            df_scaled = pd.DataFrame(self.scaler.transform(df), columns=self.cols) if self.scaler else df
            historical_avg = None
            if payload.lot_id is not None:
                historical_avg = (
                    self.db.query(func.avg(ConsumptionMeasurement.final_volume))
                      .join(Request, Request.id == ConsumptionMeasurement.request_id)
                      .filter(Request.lot_id == payload.lot_id)
                      .scalar()
                )
                historical_avg = round(historical_avg or 0, 2)
            consumo_base = float(self.m_cons.predict(df_scaled)[0])
            lluvia = float(self.m_rain.predict(df_scaled)[0])
            clase = self.m_clas.predict(df_scaled)[0]
            factores_clase = {"A": 1.00, "B": 1.10, "C": 0.90}
            factor = factores_clase.get(str(clase), 1.0)
            consumo_ajustado = (consumo_base - lluvia * self.rain_sensitivity) * factor
            return {
                "prediccion_consumo_base": round(consumo_base, 2),
                "promedio_historico_consumo": historical_avg,
                "prediccion_lluvia_mm": round(lluvia, 2),
                "factor_ajuste_por_clase": factor,
                "consumo_ajustado_final": round(consumo_ajustado, 2),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo calcular la predicción de consumo: {e}"
            )


class FacturationService:
    def __init__(self, db: Session):
        self.db = db
        self.ml = MLService(db)

    def predict_consumption_by_lot(self, lot_id: int):
        # 1) Validar lote
        lot = self.db.get(Lot, lot_id)
        if not lot:
            raise HTTPException(status_code=404, detail="Lote no encontrado")

        # 2) Obtener altitud y datos de clima
        alt = get_altitude(lot.latitude, lot.longitude)
        weather = get_weather_data(lot.latitude, lot.longitude)

        # 3) Determinar tipo de cultivo preferido
        req = (
            self.db.query(Request)
               .filter(Request.lot_id == lot_id)
               .order_by(Request.id.desc())
               .first()
        )
        crop = req.TipoCultivo if req and hasattr(req, 'TipoCultivo') and req.TipoCultivo else (
            lot.type_crop.name if lot.type_crop else ""
        )
        soil = crop_to_soil_type(crop)
        area = lot.extension

        # 4) Construir payload para modelo
        inp = PredictInput(
            Temperatura=weather["temp"],
            Humedad=weather["humidity"],
            Altitud=alt,
            AreaCultivo=area,
            TipoCultivo=crop,
            TipoTierra=soil,
            lot_id=lot_id
        )

        # 5) Llamar al servicio de ML y devolver resultado completo
        return self.ml.predict_consumption(inp)

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
        

    
    def get_concept(self, concept_id: int):
        """
        Obtiene un concepto por su ID y devuelve todos los campos,
        incluyendo los nombres de estado, scope, tipo, predio y lote
        en el mismo nivel.
        """
        try:
            c = (
                self.db
                    .query(Concept)
                    .join(Concept.scope)
                    .join(Concept.tipo)
                    .join(Concept.estado)
                    .outerjoin(Concept.property)
                    .outerjoin(Concept.lot)
                    .filter(Concept.id == concept_id)
                    .first()
            )
            if not c:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "data": {"title": "Concepto", "message": "Concepto no encontrado"}}
                )

            result = {
                "id":            c.id,
                "nombre":        c.nombre,
                "descripcion":   c.descripcion,
                "valor":         str(c.valor),
                "scope_id":      c.scope.id,
                "scope_name":    c.scope.name,
                "tipo_id":       c.tipo.id,
                "tipo_name":     c.tipo.name,
                "estado_id":     c.estado.id,
                "estado_name":   c.estado.name,
                "predio_id":     c.property.id   if c.property else None,
                "predio_name":   c.property.name if c.property else None,
                "lote_id":       c.lot.id        if c.lot else None,
                "lote_name":     c.lot.name      if c.lot else None,
                "created_at":    c.created_at.isoformat(),
                "updated_at":    c.updated_at.isoformat(),
            }
            return JSONResponse(status_code=200, content={"success": True, "data": result})

        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "data": {"title": "Error al obtener concepto", "message": str(e)}}
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
            # 1) Estado por defecto (Activo=27 o Inactivo=28 si se envía y es válido)
            estado_id = payload.estado_id if getattr(payload, "estado_id", None) in (27, 28) else 27

            # 2) Scope General (1): no se permiten predio_id ni lote_id
            if payload.scope_id == 1 and (payload.predio_id or payload.lote_id):
                raise HTTPException(400, "No puede especificar predio_id ni lote_id cuando scope es 'General'")

            # 3) Scope Específico (2): predio_id y lote_id obligatorios y deben coincidir
            if payload.scope_id == 2:
                if payload.predio_id is None or payload.lote_id is None:
                    raise HTTPException(400, "predio_id y lote_id son obligatorios cuando scope es 'Específico'")
                lote = self.db.get(Lot, payload.lote_id)
                if not lote:
                    raise HTTPException(400, "Lote no encontrado")
                # Ahora usamos p.id en vez de un atributo inexistente
                predio_ids = [p.id for p in lote.properties]
                if payload.predio_id not in predio_ids:
                    raise HTTPException(400, "El lote no está asociado al predio indicado")

            # 4) Persistir el Concept
            data = payload.model_dump(exclude_unset=True)
            data["estado_id"] = estado_id
            concept = Concept(**data)
            self.db.add(concept)
            self.db.commit()
            self.db.refresh(concept)
            return concept

        except HTTPException:
            raise
        except Exception as e:
            msg = str(e)
            # Mapeo de violaciones FK a mensajes claros
            if "concepts_scope_id_fkey" in msg:
                raise HTTPException(400, "scope_id no existe")
            if "concepts_tipo_id_fkey" in msg:
                raise HTTPException(400, "tipo_id no existe")
            if "concepts_predio_id_fkey" in msg:
                raise HTTPException(400, "predio_id no existe")
            if "concepts_lote_id_fkey" in msg:
                raise HTTPException(400, "lote_id no existe")
            raise HTTPException(500, msg)

    def update_concept(self, concept_id: int, payload: ConceptUpdate):
        """
        Actualiza un concepto existente, validando scope y la relación lote↔predio
        sin usar atributos inexistentes como lote.property_id.
        """
        try:
            obj = self.db.get(Concept, concept_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Concepto no encontrado")

            data = payload.model_dump(exclude_unset=True)
            scope     = data.get("scope_id", obj.scope_id)
            predio_id = data.get("predio_id", obj.predio_id)
            lote_id   = data.get("lote_id",   obj.lote_id)

            # 1) Si cambian a General (1), no se permiten predio ni lote
            if scope == 1 and (predio_id or lote_id):
                raise HTTPException(
                    status_code=400,
                    detail="No puede especificar predio_id ni lote_id cuando scope es 'General'"
                )

            # 2) Si es Específico (2), validar ambos y su relación
            if scope == 2:
                if predio_id is None or lote_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="predio_id y lote_id son obligatorios cuando scope es 'Específico'"
                    )
                lote = self.db.get(Lot, lote_id)
                if not lote:
                    raise HTTPException(status_code=400, detail="Lote no encontrado")
                # Ahora obtenemos los predio.id asociados al lote
                predio_ids = [p.id for p in lote.properties]
                if predio_id not in predio_ids:
                    raise HTTPException(
                        status_code=400,
                        detail="El lote no pertenece al predio indicado"
                    )

            # 3) Aplicar cambios y persistir
            for attr, val in data.items():
                setattr(obj, attr, val)
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
        # 1) Obtener factura
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        # 2) Pago asociado
        payment = self.db.query(Payment).filter(Payment.invoice_id == invoice_id).first()
        payment_data = None
        if payment:
            payment_data = {
                "payment_method":      payment.payment_method,
                "reference_code":      payment.reference_code,
                "transaction_id":      payment.transaction_id,
                "transaction_amount":  float(payment.amount),
                "payment_date":        payment.paid_at,
                "payment_status_id":   payment.status,
                "payment_status_name": payment.status
            }

        # 3) Documento del cliente
        client_document = None
        if invoice.user_id:
            usr = self.db.get(PropertyUser, invoice.user_id)
            # Correction: use User model instead of PropertyUser
            from app.facturation.models import User
            u = self.db.get(User, invoice.user_id)
            client_document = u.document_number if u else None

        # 4) Property id vía lote
        property_id = None
        if invoice.lot_id is not None:
            property_id = (
                self.db.query(PropertyLot.property_id)
                       .filter(PropertyLot.lot_id == invoice.lot_id)
                       .scalar()
            )
            if not client_document and property_id:
                pu = self.db.query(PropertyUser).filter(
                    PropertyUser.property_id == property_id
                ).first()
                if pu:
                    from app.facturation.models import User
                    u2 = self.db.get(User, pu.user_id)
                    client_document = u2.document_number if u2 else None

        # 5) Periodo facturado
        period = {
            "start_date":      getattr(invoice, "billing_start_date", None),
            "end_date":        getattr(invoice, "billing_end_date", None),
            "invoiced_period": getattr(invoice, "invoiced_period", None),
        }

        # 6) Total volumen medido
        total_volume = self.db.query(
            func.sum(ConsumptionMeasurement.final_volume)
        ).filter(ConsumptionMeasurement.invoice_id == invoice_id).scalar() or 0

        # 7) Conceptos facturados
        conceptos = []
        for concept, ic in self.db.query(Concept, InvoiceConcept).join(
            InvoiceConcept, Concept.id == InvoiceConcept.concept_id
        ).filter(InvoiceConcept.invoice_id == invoice_id):
            conceptos.append({
                "concept_id":     concept.id,
                "nombre":         concept.nombre,
                "descripcion":    concept.descripcion,
                "valor_unitario": float(concept.valor),
                "total_concepto": float(total_volume) * float(concept.valor)
            })

        # 8) Construir respuesta
        return {
            "invoice": {
                "invoice_id":         invoice.id,
                "reference_code":     invoice.reference_code,
                "issuance_date":      invoice.issuance_date,
                "expiration_date":    invoice.expiration_date,
                "pdf_url":            invoice.pdf_url,
                **period,
                "total_amount":       float(invoice.total_amount),
                "client_name":        getattr(invoice, "client_name", None),
                "client_email":       getattr(invoice, "client_email", None),
                "client_document":    client_document,
                "property_id":        property_id,
                "lot_id":             invoice.lot_id,
                "invoice_status_name":invoice.status,
                "dian_status_id":     invoice.dian_status,
                "dian_status_name":   invoice.dian_status
            },
            "payment":  payment_data,
            "concepts": conceptos
        }

    def list_user_invoices(self, user_id: int):
        from app.facturation.models import User
        from sqlalchemy.orm import aliased
        from app.payu.models import Invoice as Inv
        from app.facturation.models import PaymentInterval

        # 1) Validar usuario
        if not self.db.query(User).filter(User.id == user_id).first():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        PI = aliased(PaymentInterval)

        rows = (
            self.db.query(
                Inv.id.label("invoice_id"),
                Inv.reference_code,
                PropertyLot.property_id,
                Property.name.label("property_name"),
                Inv.lot_id,
                Lot.name.label("lot_name"),
                PI.name.label("payment_interval"),
                PI.interval_days.label("payment_days"),
                Inv.invoiced_period,
                Inv.expiration_date,
                Inv.issuance_date,
                Inv.total_amount,
                Inv.status,
                Inv.pdf_url,
                User.document_number.label("document_number")
            )
            .join(User, User.id == Inv.user_id)
            .join(Lot, Inv.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval_id == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .join(Property, Property.id == PropertyLot.property_id)
            .filter(Inv.user_id == user_id)
            .order_by(Inv.expiration_date.desc())
            .all()
        )

        result = []
        for (
            inv_id,
            ref_code,
            prop_id,
            prop_name,
            lot_id,
            lot_name,
            interval,
            payment_days,
            invoiced_period,
            exp_dt,
            iss_dt,
            amount,
            status,
            pdf_url,
            doc_number
        ) in rows:
            exp_date = exp_dt.date() if hasattr(exp_dt, "date") else exp_dt
            iss_date = iss_dt.date() if hasattr(iss_dt, "date") else iss_dt
            result.append({
                "invoice_id":       inv_id,
                "reference_code":   ref_code,
                "property_id":      prop_id,
                "property_name":    prop_name,
                "lot_id":           lot_id,
                "lot_name":         lot_name,
                "payment_interval": interval,
                "payment_days":     payment_days,
                "invoiced_period":  invoiced_period,
                "expiration_date":  exp_date,
                "issuance_date":    iss_date,
                "total_amount":     float(amount),
                "status":           status,
                "pdf_url":          pdf_url,
                "document_number":  doc_number
            })
        return result
    
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

            # sql = text("""
            #     SELECT cm.*
            #     FROM consumption_measurements cm
            #     INNER JOIN request r ON r.id = cm.request_id  
            #     WHERE cm.invoice_id IS NULL
            #     AND cm.created_at >= :start_date
            #     AND r.lot_id = :lot_id
            #     AND cm.created_at <= :end_date
            # """)

            # result = self.db.execute(sql, {
            #     "lot_id": invoice.lot_id,
            #     "start_date": invoice.billing_start_date,
            #     "end_date": invoice.billing_end_date
            # })

            # consumptions = result.fetchall()

            # if not consumptions:
            #     return JSONResponse(
            #         status_code=400,
            #         content={
            #             "success": False,
            #             "data": {"title": "Facturación pendiente", "message": "No se puede crear la factura porque no existen consumos."},
            #             },
            #         )
            
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

            # pass
            factus = FactusService(self.db)
            result = factus.generate_invoice_from_payment(invoice, user_lots)

            if result['success'] is False:
                return JSONResponse(status_code=400, content=result)

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

    