from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import SessionLocal
from ..ml import assistant as assistant_ml
from ..ml.predict import current_provider, google_configured, predict_proba_one
from ..models.alert import Alert
from ..models.assistant_log import AssistantLog
from ..models.device import Device
from ..models.maintenance_feedback import MaintenanceFeedback
from ..models.prediction import Prediction
from ..models.reading import Reading
from ..schemas.common import (
    AlertOut,
    AssistantLogOut,
    MaintenanceFeedbackCreate,
    MaintenanceFeedbackOut,
    PredictionOut,
    ReadingBatch,
    ReadingIn,
)


router = APIRouter(prefix="/insights", tags=["insights"])


ASSISTANT_MODES: dict[str, dict] = {
    "triage_summary": {
        "label": "Triage Summary",
        "description": "Summarize current issues, key risks, and immediate next steps for a specific asset.",
        "requires_device": True,
        "system_prompt": (
            "You are an operations triage assistant for logistics equipment. "
            "Given the provided telemetry context, craft a concise summary (3-4 bullet points) covering "
            "current symptoms, probable causes, and immediate next actions. Keep language clear and actionable."
        ),
        "fallback": "Review telemetry and alerts for {asset_name} and schedule a quick inspection focusing on vibration and temperature outliers.",
    },
    "technician_playbook": {
        "label": "Technician Playbook",
        "description": "Provide a hands-on diagnostic checklist technicians can follow for the selected asset.",
        "requires_device": True,
        "system_prompt": (
            "You are a senior maintenance engineer. Based on the asset context, produce a numbered checklist of diagnostic steps, "
            "tools required, and safety notes a field technician should follow."
        ),
        "fallback": "Prepare a technician checklist covering visual inspection, sensor verification, lubrication, and safety lock-out for {asset_name}.",
    },
    "maintenance_prioritization": {
        "label": "Maintenance Prioritization",
        "description": "Prioritize upcoming maintenance across the fleet using current risks and alerts.",
        "requires_device": False,
        "system_prompt": (
            "You are a maintenance planner. Rank the provided assets by urgency using probability trends, alert volume, and operating context. "
            "Return a short ordered list with justification for each priority."
        ),
        "fallback": "Review the high risk count and open predictive alerts to prioritize inspections manually, starting with assets showing repeated alerts.",
    },
    "anomaly_explanation": {
        "label": "Anomaly Explanation",
        "description": "Explain unusual telemetry behavior observed on a specific asset.",
        "requires_device": True,
        "system_prompt": (
            "You are monitoring telemetry for anomalies. Explain any spikes or trends and suggest likely root causes."
        ),
        "fallback": "Investigate recent telemetry deviations on {asset_name}; compare vibration and temperature trends against historical averages.",
    },
    "inventory_hint": {
        "label": "Inventory Hint",
        "description": "Recommend spare parts or supplies that should be staged for upcoming maintenance windows.",
        "requires_device": False,
        "system_prompt": (
            "Use failure probabilities and asset types to suggest parts or consumables to stage. "
            "Assume a typical logistics warehouse inventory policy."
        ),
        "fallback": "Stage common wear parts (belts, bearings, hydraulic hoses) for assets showing elevated risk and temperature trends.",
    },
    "training_brief": {
        "label": "Training Brief",
        "description": "Create a short training or knowledge-sharing brief for maintenance teams based on recent events.",
        "requires_device": False,
        "system_prompt": (
            "Summarize the latest maintenance insights into a brief for technicians, highlighting lessons learned and best practices."
        ),
        "fallback": "Prepare a short training note covering recent alerts, key telemetry indicators, and safety reminders for the team.",
    },
    "incident_message": {
        "label": "Incident Communication",
        "description": "Draft a stakeholder-facing message summarizing the incident status and next steps for a selected asset.",
        "requires_device": True,
        "system_prompt": (
            "Draft a brief communication (3-4 sentences) suitable for stakeholders, summarizing the issue, impact, and planned actions."
        ),
        "fallback": "Notify stakeholders that {asset_name} is under review; share latest alert details and advise that maintenance is being scheduled.",
    },
    "simulation_feedback": {
        "label": "Simulation Feedback",
        "description": "Label simulated scenarios as normal, early degradation, or critical.",
        "requires_device": False,
        "system_prompt": (
            "Given simulated telemetry context, classify scenarios as normal operations, early-stage degradation, or critical action needed, and explain why."
        ),
        "fallback": "Review simulator outputs and tag them manually as normal, warning, or critical based on vibration and temperature thresholds.",
    },
    "escalation_guidance": {
        "label": "Escalation Guidance",
        "description": "Decide whether to escalate to supervisors or keep monitoring based on fleet context.",
        "requires_device": False,
        "system_prompt": (
            "You are a duty manager. Decide whether escalation is needed. Provide rationale referencing risk counts and alert history."
        ),
        "fallback": "Escalate if predictive alerts continue or if any asset shows repeated high severity events; otherwise monitor closely.",
    },
    "compliance_report": {
        "label": "Compliance Narrative",
        "description": "Produce a short compliance or audit narrative using recent telemetry and actions.",
        "requires_device": False,
        "system_prompt": (
            "Draft a short compliance narrative documenting recent checks, alerts, and responses suitable for audit records."
        ),
        "fallback": "Document recent maintenance actions, alert counts, and risk assessments manually for compliance reporting.",
    },
}


class AssistanceRequest(BaseModel):
    mode: str
    device_id: Optional[int] = None
    notes: Optional[str] = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/predictions", response_model=List[PredictionOut])
def list_predictions(db: Session = Depends(get_db)):
    return db.query(Prediction).order_by(Prediction.timestamp.desc()).limit(200).all()


@router.get("/alerts", response_model=List[AlertOut])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).order_by(Alert.timestamp.desc()).limit(200).all()


@router.get("/config")
def get_config():
    return {
        "provider": current_provider(),
        "alert_prob_threshold": settings.ALERT_PROB_THRESHOLD,
        "temperature_max": settings.ALERT_TEMPERATURE_MAX,
        "google": google_configured(),
        "assistant_modes": [
            {
                "id": key,
                "label": value["label"],
                "description": value["description"],
                "requires_device": value["requires_device"],
            }
            for key, value in ASSISTANT_MODES.items()
        ],
    }


def _build_metrics(db: Session) -> dict:
    now = datetime.utcnow()
    horizon = now - timedelta(hours=24)
    device_rows = db.query(Device).all()
    device_count = len(device_rows)

    alerts_open = db.query(Alert).filter(Alert.acknowledged == False).all()  # noqa: E712
    active_alerts = len(alerts_open)

    readings_today = (
        db.query(func.count(Reading.id)).filter(Reading.timestamp >= horizon).scalar() or 0
    )
    recent_preds = (
        db.query(Prediction)
        .filter(Prediction.timestamp >= horizon)
        .order_by(Prediction.timestamp.desc())
        .all()
    )
    latest_pred = recent_preds[0].probability if recent_preds else None
    high_risk = sum(1 for p in recent_preds if p.probability >= settings.ALERT_PROB_THRESHOLD)

    device_map = {d.id: d for d in device_rows}

    type_stats: dict[str, dict] = {}
    location_stats: dict[str, dict] = {}

    for d in device_rows:
        loc = d.location or "Unassigned"
        t_stat = type_stats.setdefault(
            d.type,
            {
                "type": d.type,
                "count": 0,
                "active_alerts": 0,
                "avg_probability": None,
                "locations": set(),
            },
        )
        t_stat["count"] += 1
        t_stat["locations"].add(loc)

        l_stat = location_stats.setdefault(
            loc,
            {
                "location": loc,
                "devices": 0,
                "active_alerts": 0,
            },
        )
        l_stat["devices"] += 1

    alerts_by_device: dict[int, list[Alert]] = defaultdict(list)
    for alert in alerts_open:
        dev = device_map.get(alert.device_id)
        if not dev:
            continue
        alerts_by_device[alert.device_id].append(alert)
        type_stats.setdefault(
            dev.type,
            {
                "type": dev.type,
                "count": 0,
                "active_alerts": 0,
                "avg_probability": None,
                "locations": set(),
            },
        )["active_alerts"] += 1
        location_stats.setdefault(
            dev.location or "Unassigned",
            {
                "location": dev.location or "Unassigned",
                "devices": 0,
                "active_alerts": 0,
            },
        )["active_alerts"] += 1

    for pred in recent_preds:
        dev = device_map.get(pred.device_id)
        if not dev:
            continue
        stat = type_stats.setdefault(
            dev.type,
            {
                "type": dev.type,
                "count": 0,
                "active_alerts": 0,
                "avg_probability": None,
                "locations": set(),
            },
        )
        stat.setdefault("_prob_sum", 0.0)
        stat.setdefault("_prob_count", 0)
        stat["_prob_sum"] += pred.probability
        stat["_prob_count"] += 1

    type_summary = []
    for stat in type_stats.values():
        prob_sum = stat.pop("_prob_sum", 0.0)
        prob_count = stat.pop("_prob_count", 0)
        stat["avg_probability"] = (prob_sum / prob_count) if prob_count else None
        stat["locations"] = sorted(stat["locations"])
        type_summary.append(stat)

    location_summary = list(location_stats.values())

    latest_readings: dict[int, Reading] = {}
    for reading in (
        db.query(Reading)
        .order_by(Reading.device_id, Reading.timestamp.desc())
        .all()
    ):
        if reading.device_id not in latest_readings:
            latest_readings[reading.device_id] = reading

    latest_predictions: dict[int, Prediction] = {}
    for pred in (
        db.query(Prediction)
        .order_by(Prediction.device_id, Prediction.timestamp.desc())
        .all()
    ):
        if pred.device_id not in latest_predictions:
            latest_predictions[pred.device_id] = pred

    device_snapshots = []
    for device in device_rows:
        latest_read = latest_readings.get(device.id)
        latest_pred_obj = latest_predictions.get(device.id)
        device_snapshots.append(
            {
                "id": device.id,
                "name": device.name,
                "type": device.type,
                "location": device.location,
                "status": device.status,
                "latest_probability": latest_pred_obj.probability if latest_pred_obj else None,
                "latest_probability_timestamp": latest_pred_obj.timestamp.isoformat() if latest_pred_obj else None,
                "latest_reading": {
                    "timestamp": latest_read.timestamp.isoformat(),
                    "vibration": latest_read.vibration,
                    "temperature": latest_read.temperature,
                    "current": latest_read.current,
                    "rpm": latest_read.rpm,
                    "load_pct": latest_read.load_pct,
                }
                if latest_read
                else None,
                "open_alerts": [
                    {
                        "id": alert.id,
                        "kind": alert.kind,
                        "severity": alert.severity,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat(),
                    }
                    for alert in alerts_by_device.get(device.id, [])
                ],
            }
        )

    recommendations = []
    predictive_alerts = (
        db.query(Alert)
        .filter(Alert.kind == "predictive")
        .order_by(Alert.timestamp.desc())
        .limit(5)
        .all()
    )
    for alert in predictive_alerts:
        dev = device_map.get(alert.device_id)
        if not dev:
            continue
        recommendations.append(
            {
                "device_id": dev.id,
                "device_name": dev.name,
                "type": dev.type,
                "severity": alert.severity,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
            }
        )

    feedback_rows = (
        db.query(MaintenanceFeedback)
        .order_by(MaintenanceFeedback.created_at.desc())
        .limit(10)
        .all()
    )
    feedback_entries = [
        {
            "id": fb.id,
            "device_id": fb.device_id,
            "device_name": device_map.get(fb.device_id).name if device_map.get(fb.device_id) else None,
            "outcome": fb.outcome,
            "notes": fb.notes,
            "submitted_by": fb.submitted_by,
            "related_probability": fb.related_probability,
            "created_at": fb.created_at.isoformat(),
        }
        for fb in feedback_rows
    ]

    return {
        "device_count": device_count,
        "active_alerts": active_alerts,
        "readings_last_24h": readings_today,
        "high_risk_count": high_risk,
        "latest_probability": latest_pred,
        "type_summary": type_summary,
        "location_summary": location_summary,
        "device_snapshots": device_snapshots,
        "recommendations": recommendations,
        "feedback_entries": feedback_entries,
    }


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    return _build_metrics(db)


def _log_assistant_interaction(
    db: Session,
    *,
    device_id: Optional[int],
    mode: str,
    provider: str,
    message: str,
    notes: Optional[str],
):
    log = AssistantLog(
        device_id=device_id,
        mode=mode,
        provider=provider,
        message=message,
        notes=notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/assistant/logs", response_model=List[AssistantLogOut])
def list_assistant_logs(
    limit: int = 50,
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(AssistantLog).order_by(AssistantLog.created_at.desc())
    if device_id is not None:
        query = query.filter(AssistantLog.device_id == device_id)
    rows = query.limit(max(1, min(limit, 200))).all()
    device_map = {d.id: d for d in db.query(Device).filter(Device.id.in_({row.device_id for row in rows if row.device_id})).all()}
    return [
        AssistantLogOut(
            id=row.id,
            device_id=row.device_id,
            device_name=device_map.get(row.device_id).name if row.device_id and device_map.get(row.device_id) else None,
            mode=row.mode,
            provider=row.provider,
            message=row.message,
            notes=row.notes,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/feedback", response_model=MaintenanceFeedbackOut)
def submit_feedback(payload: MaintenanceFeedbackCreate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == payload.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    feedback = MaintenanceFeedback(
        device_id=payload.device_id,
        outcome=payload.outcome,
        notes=payload.notes,
        submitted_by=payload.submitted_by,
        related_probability=payload.related_probability,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return MaintenanceFeedbackOut(
        id=feedback.id,
        device_id=feedback.device_id,
        device_name=device.name,
        outcome=feedback.outcome,
        notes=feedback.notes,
        submitted_by=feedback.submitted_by,
        related_probability=feedback.related_probability,
        created_at=feedback.created_at,
    )


@router.get("/feedback", response_model=List[MaintenanceFeedbackOut])
def list_feedback(
    limit: int = 50,
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(MaintenanceFeedback).order_by(MaintenanceFeedback.created_at.desc())
    if device_id is not None:
        query = query.filter(MaintenanceFeedback.device_id == device_id)
    rows = query.limit(max(1, min(limit, 200))).all()
    device_map = {d.id: d for d in db.query(Device).filter(Device.id.in_({row.device_id for row in rows})).all()}
    return [
        MaintenanceFeedbackOut(
            id=row.id,
            device_id=row.device_id,
            device_name=device_map.get(row.device_id).name if device_map.get(row.device_id) else "Unknown",
            outcome=row.outcome,
            notes=row.notes,
            submitted_by=row.submitted_by,
            related_probability=row.related_probability,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/what-if")
def what_if(payload: ReadingIn, db: Session = Depends(get_db)):
    base_context = (
        db.query(Reading)
        .filter(Reading.device_id == payload.device_id)
        .order_by(Reading.timestamp.desc())
        .limit(20)
        .all()
    )
    context = [
        {
            "timestamp": r.timestamp,
            "vibration": r.vibration,
            "temperature": r.temperature,
            "current": r.current,
            "rpm": r.rpm,
            "load_pct": r.load_pct,
        }
        for r in reversed(base_context)
    ]
    candidate = payload.model_dump()
    candidate["timestamp"] = candidate.get("timestamp") or datetime.utcnow()
    context.append(candidate)
    probability = predict_proba_one(context)
    return {"probability": probability}


@router.post("/assistant")
def ai_assistant(request: AssistanceRequest, db: Session = Depends(get_db)):
    mode_def = ASSISTANT_MODES.get(request.mode)
    if not mode_def:
        raise HTTPException(status_code=400, detail="Unknown assistance mode")

    metrics = _build_metrics(db)
    device_snapshot = None
    if request.device_id is not None:
        for snap in metrics["device_snapshots"]:
            if snap["id"] == request.device_id:
                device_snapshot = snap
                break
        if not device_snapshot:
            raise HTTPException(status_code=404, detail="Device not found")

    if mode_def["requires_device"] and device_snapshot is None:
        raise HTTPException(status_code=400, detail="Device id is required for this assistance mode")

    context_payload = {
        "mode": request.mode,
        "description": mode_def["description"],
        "notes": request.notes or "",
        "timestamp": datetime.utcnow().isoformat(),
        "device": device_snapshot,
        "metrics": {
            "device_count": metrics["device_count"],
            "active_alerts": metrics["active_alerts"],
            "high_risk_count": metrics["high_risk_count"],
            "type_summary": metrics["type_summary"],
            "location_summary": metrics["location_summary"],
            "recommendations": metrics["recommendations"],
        },
    }

    try:
        ai_response = assistant_ml.generate_response(
            mode_def["system_prompt"],
            context_payload,
        )
        message = ai_response.get("text", "")
        log_entry = _log_assistant_interaction(
            db,
            device_id=request.device_id,
            mode=request.mode,
            provider="google",
            message=message,
            notes=request.notes,
        )
        return {
            "mode": request.mode,
            "provider": "google",
            "model": ai_response.get("model"),
            "message": message,
            "log_id": log_entry.id,
            "created_at": log_entry.created_at,
        }
    except assistant_ml.AssistantUnavailable as exc:
        asset_name = (device_snapshot or {}).get("name", "this equipment")
        fallback_message = mode_def["fallback"].format(asset_name=asset_name, notes=request.notes or "")
        log_entry = _log_assistant_interaction(
            db,
            device_id=request.device_id,
            mode=request.mode,
            provider="fallback",
            message=fallback_message,
            notes=request.notes,
        )
        return {
            "mode": request.mode,
            "provider": "fallback",
            "model": None,
            "message": fallback_message,
            "detail": str(exc),
            "log_id": log_entry.id,
            "created_at": log_entry.created_at,
        }
