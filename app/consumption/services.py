from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased
from datetime import date

from app.facturation.models import PaymentInterval, ConsumptionMeasurement, PropertyUser , Lot, Request, PropertyLot, Property, TypeCrop
from app.facturation.services import MLService
from app.facturation.schemas import PredictInput
from app.utils.geo import get_altitude, get_weather_data
from app.utils.mapping import crop_to_soil_type

class ConsumptionService:
    def __init__(self, db: Session):
        self.db = db
        self.ml = MLService(db)

    def list_all_consumptions(self):
        PI = aliased(PaymentInterval)
        rows = (
            self.db.query(
                PropertyLot.property_id,
                Lot.id.label("lot_id"),
                PI.name.label("payment_interval"),
                ConsumptionMeasurement.created_at.label("measurement_date"),
                ConsumptionMeasurement.final_volume
            )
            .select_from(ConsumptionMeasurement)
            .join(Request, ConsumptionMeasurement.request_id == Request.id)
            .join(Lot, Request.lot_id == Lot.id)
            .outerjoin(PI, Lot.payment_interval_id == PI.id)
            .join(PropertyLot, PropertyLot.lot_id == Lot.id)
            .order_by(ConsumptionMeasurement.created_at.desc())
            .all()
        )
        return [
            {
                "property_id":      prop,
                "lot_id":           lot,
                "payment_interval": interval,
                "measurement_date": m_date,
                "final_volume":     float(vol)
            }
            for prop, lot, interval, m_date, vol in rows
        ]

    def get_monthly_stats(self, year: int, month: int):
        recs = (
            self.db.query(ConsumptionMeasurement)
               .filter(
                   func.extract("year", ConsumptionMeasurement.created_at) == year,
                   func.extract("month", ConsumptionMeasurement.created_at) == month
               )
               .all()
        )
        if not recs:
            raise HTTPException(404, "No hay consumos registrados para ese mes")

        total_vol = sum(r.final_volume for r in recs)
        registered_avg = total_vol / len(recs)

        proj_vals = []
        for m in recs:
            req = self.db.get(Request, m.request_id)
            lot = self.db.get(Lot, req.lot_id)
            # Obtener type_crop guardando None
            tc = self.db.get(TypeCrop, lot.type_crop_id)
            crop_name = tc.name if tc else None
            soil = crop_to_soil_type(crop_name or "")
            alt = get_altitude(lot.latitude, lot.longitude)
            weather = get_weather_data(lot.latitude, lot.longitude)
            inp = PredictInput(
                Temperatura=weather["temp"],
                Humedad=weather["humidity"],
                Altitud=alt,
                AreaCultivo=lot.extension,
                TipoCultivo=crop_name or "",  # default empty
                TipoTierra=soil,
                lot_id=lot.id
            )
            pred = self.ml.predict_consumption(inp)
            proj_vals.append(pred.get("consumo_ajustado_final", 0.0))

        projected_avg = sum(proj_vals) / len(proj_vals)
        variation = round((projected_avg - registered_avg) / (registered_avg or 1) * 100, 2)

        return {
            "registered_avg":    round(registered_avg, 2),
            "projected_avg":     round(projected_avg, 2),
            "variation_percent": variation
        }

    def get_consumption_detail(self, measurement_id: int):
        rec = self.db.get(ConsumptionMeasurement, measurement_id)
        if not rec:
            raise HTTPException(404, "Medición no encontrada")

        req = self.db.get(Request, rec.request_id)
        lot = self.db.get(Lot, req.lot_id)
        prop_id = (
            self.db.query(PropertyLot.property_id)
               .filter(PropertyLot.lot_id == lot.id)
               .scalar()
        )
        prop = self.db.get(Property, prop_id)

        recs = (
            self.db.query(ConsumptionMeasurement)
               .filter(ConsumptionMeasurement.request_id == rec.request_id)
               .order_by(ConsumptionMeasurement.created_at)
               .all()
        )

        vols = [r.final_volume for r in recs]
        registered_avg = sum(vols) / len(vols) if vols else 0.0

        proj_vals = []
        for _ in recs:
            tc = self.db.get(TypeCrop, lot.type_crop_id)
            crop_name = tc.name if tc else None
            soil = crop_to_soil_type(crop_name or "")
            alt = get_altitude(lot.latitude, lot.longitude)
            weather = get_weather_data(lot.latitude, lot.longitude)
            inp = PredictInput(
                Temperatura=weather["temp"],
                Humedad=weather["humidity"],
                Altitud=alt,
                AreaCultivo=lot.extension,
                TipoCultivo=crop_name or "",  
                TipoTierra=soil,
                lot_id=lot.id
            )
            pred = self.ml.predict_consumption(inp)
            proj_vals.append(pred.get("consumo_ajustado_final", 0.0))

        projected_avg = sum(proj_vals) / len(proj_vals) if proj_vals else 0.0
        variation = round((projected_avg - registered_avg) / (registered_avg or 1) * 100, 2)

        records = [
            {
                "property_id":      prop.id,
                "lot_id":           lot.id,
                "measurement_date": r.created_at,
                "final_volume":     r.final_volume
            }
            for r in recs
        ]

        return {
            "measurement_id":    rec.id,
            "property_id":       prop.id,
            "property_name":     prop.name,
            "lot_id":            lot.id,
            "lot_name":          lot.name,
            "registered_avg":    registered_avg,
            "projected_avg":     projected_avg,
            "variation_percent": variation,
            "records":           records
        }

    def get_properties_total_consumption(self, user_id: int):
        props = (
            self.db.query(Property)
               .join(PropertyUser, Property.id == PropertyUser.property_id)
               .filter(PropertyUser.user_id == user_id)
               .all()
        )
        result = []
        for p in props:
            lot_ids = [l.id for l in p.lots]
            recs = (
                self.db.query(ConsumptionMeasurement)
                   .join(Request, Request.id == ConsumptionMeasurement.request_id)
                   .filter(Request.lot_id.in_(lot_ids))
                   .all()
            )
            if not recs:
                continue
            total = sum(r.final_volume for r in recs)
            latest = max(r.created_at for r in recs)
            result.append({
                "property_id":            p.id,
                "property_name":          p.name,
                "extension":              p.extension,
                "measurement_date":       latest,
                "registered_consumption": total
            })
        return {"success": True, "data": result}

    def predict_district_consumption(self):
        lots = self.db.query(Lot).all()
        total_pred, details = 0.0, []
        for lot in lots:
            tc = self.db.get(TypeCrop, lot.type_crop_id)
            crop_name = tc.name if tc else None
            soil = crop_to_soil_type(crop_name or "")
            alt = get_altitude(lot.latitude, lot.longitude)
            weather = get_weather_data(lot.latitude, lot.longitude)
            inp = PredictInput(
                Temperatura=weather["temp"],
                Humedad=weather["humidity"],
                Altitud=alt,
                AreaCultivo=lot.extension,
                TipoCultivo=crop_name or "",
                TipoTierra=soil,
                lot_id=lot.id
            )
            try:
                pred = self.ml.predict_consumption(inp)
                adj = pred.get("consumo_ajustado_final", 0.0)
                total_pred += adj
                details.append({
                    "lot_id": lot.id,
                    "lot_name": lot.name,
                    "predicted_consumption": adj
                })
            except Exception as e:
                raise HTTPException(500, f"Error IA lote {lot.id}: {e}")

        return {"success": True, "data": {"details": details, "total_predicted_consumption": round(total_pred, 2)}}
