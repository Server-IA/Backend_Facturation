# services.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pandas as pd
from app.facturation.models import Concept, Lot , ConsumptionMeasurement, Request
from app.facturation.schemas import ConceptCreate, ConceptUpdate , PredictInput

from app.ml import (
     get_models
)


class MLService:
    def __init__(self, db: Session):
        self.db = db

    def predict_consumption(self, payload: PredictInput, rain_sensitivity: float = 0.1):
        """
        Predice consumo ajustado por la lluvia esperada y clasificación del cultivo,
        usando los tres modelos existentes sin reentrenarlos.

        rain_sensitivity: cuánto reduce el consumo cada unidad predicha de lluvia.
        """
        # 1) Carga de modelos
        models = get_models()
        m_cons = models["consumo"]
        m_rain = models["lluvia"]
        m_clas = models["clasificacion"]
        cols   = models["columnas"]

        # 2) Preprocesamiento idéntico al inicial
        data = payload.model_dump()
        df   = pd.DataFrame([data])
        df   = pd.get_dummies(df)
        for c in cols:
            if c not in df.columns:
                df[c] = 0
        df = df[cols]

        # 3) Predicción base de consumo
        try:
            base_cons = float(m_cons.predict(df)[0])
        except Exception as e:
            raise HTTPException(500, f"Error en consumo: {e}")

        # 4) Predicción de clasificación
        try:
            clase = m_clas.predict(df)[0]
        except Exception as e:
            raise HTTPException(500, f"Error en clasificación: {e}")

        # 5) Predicción de lluvia
        try:
            rain = float(m_rain.predict(df)[0])
        except Exception as e:
            raise HTTPException(500, f"Error en lluvia: {e}")

        # 6) Factor de ajuste según la clase de cultivo
        class_factors = {
            "A": 1.00,
            "B": 1.10,
            "C": 0.90,
        }
        factor_clase = class_factors.get(str(clase), 1.0)

        # 7) Cálculo del consumo ajustado
        #    - Se reduce según lluvia (cuanto más llueva, menos consumo)
        #    - Se multiplica por el factor de la clase de cultivo
        adjusted_cons = (base_cons - rain * rain_sensitivity) * factor_clase

        # 8) Construcción y retorno de la respuesta
        result = {
            "base_consumption":     round(base_cons, 2),
            "predicted_rain":       round(rain, 2),
            "crop_class":           clase,
            "class_factor":         factor_clase,
            "rain_sensitivity":     rain_sensitivity,
            "adjusted_consumption": round(adjusted_cons, 2),
        }
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({"success": True, "data": result})
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