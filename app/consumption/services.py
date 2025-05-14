# app/consumption/services.py

from datetime import date
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased
from app.facturation.models    import Request, Lot, PropertyLot, Property, PaymentInterval , ConsumptionMeasurement
from app.facturation.models    import User
from app.payu.models           import Invoice
from app.facturation.services                     import MLService  # asumiendo tu servicio de IA

class ConsumptionService:
    def __init__(self, db: Session):
        self.db = db
        self.ml = MLService(db)

    def list_all_consumptions(self):
        """
        Lista todas las mediciones de consumo con:
         - property_id, lot_id, payment_interval, measurement_date, final_volume
        """
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
            .outerjoin(PI, Lot.payment_interval == PI.id)
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
        """
        Estadísticas para un mes:
         - registered_avg: promedio mensual registrado
         - projected_avg:  promedio mensual proyectado por IA
         - variation_percent: (proj - reg)/reg*100
        """
        # 1) Filtrar mediciones del mes
        qry = self.db.query(ConsumptionMeasurement).filter(
            func.extract("year", ConsumptionMeasurement.created_at)  == year,
            func.extract("month",ConsumptionMeasurement.created_at)  == month
        )
        recs = qry.all()
        if not recs:
            raise HTTPException(status_code=404, detail="No hay consumos registrados para ese mes")

        # 2) Promedio registrado
        total_vol = sum(r.final_volume for r in recs)
        registered_avg = total_vol / len(recs)

        # 3) Promedio proyectado: iterar y usar MLService con datos reales de Request
        proj_vals = []
        for m in recs:
            req = self.db.get(Request, m.request_id)
            payload = {
                "Temperatura":    req.Temperatura,
                "Humedad":        req.Humedad,
                "Altitud":        req.Altitud,
                "AreaCultivo":    req.AreaCultivo,
                "TipoCultivo":    req.TipoCultivo,
                "TipoTierra":     req.TipoTierra,
                "lot_id":         req.lot_id
            }
            res = self.ml.predict_consumption(payload)
            proj_vals.append(res["consumo_ajustado"])
        projected_avg = sum(proj_vals) / len(proj_vals)

        # 4) Variación esperada
        variation = round((projected_avg - registered_avg) / (registered_avg or 1) * 100, 2)

        return {
            "registered_avg":    round(registered_avg, 2),
            "projected_avg":     round(projected_avg, 2),
            "variation_percent": variation
        }

    def get_consumption_detail(self, measurement_id: int):
        """
        Detalle de una medición de consumo:
         - measurement_id, property_id, property_name, lot_id, lot_name
         - registered_avg, projected_avg, variation_percent
         - records: lista de todas las mediciones de ese request
        """
        rec = self.db.get(ConsumptionMeasurement, measurement_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Medición no encontrada")

        # buscar request, lote y predio
        req = self.db.get(Request, rec.request_id)
        lot = self.db.get(Lot, req.lot_id)
        prop_id = (
            self.db.query(PropertyLot.property_id)
               .filter(PropertyLot.lot_id == lot.id)
               .scalar()
        )
        prop = self.db.get(Property, prop_id)

        # todas las mediciones de este request
        recs = self.db.query(ConsumptionMeasurement).filter(
            ConsumptionMeasurement.request_id == rec.request_id
        ).order_by(ConsumptionMeasurement.created_at).all()

        # cálculo de promedios
        vols = [r.final_volume for r in recs]
        registered_avg = sum(vols) / len(vols) if vols else 0.0

        proj_vals = []
        for r in recs:
            payload = {
                "Temperatura": 0.0,
                "Humedad":     0.0,
                "Altitud":     0.0,
                "AreaCultivo": 0.0,
                "TipoCultivo": "A",
                "TipoTierra":  "arenosa",
                "lot_id":      req.lot_id
            }
            proj_vals.append(self.ml.predict_consumption(payload)["consumo_ajustado"])
        projected_avg = sum(proj_vals) / len(proj_vals) if proj_vals else 0.0
        variation = round((projected_avg - registered_avg) / (registered_avg or 1) * 100, 2)

        # registros detallados
        records = [
            {
                "property_id":      prop.id,
                "lot_id":           lot.id,
                "payment_interval": lot.payment_interval,  # si lo necesitas
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
