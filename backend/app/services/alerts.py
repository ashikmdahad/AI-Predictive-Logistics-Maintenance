from ..core.config import settings


def threshold_check(reading: dict) -> list[dict]:
    alerts = []
    if reading.get("temperature", 0) > settings.ALERT_TEMPERATURE_MAX:
        alerts.append({
            "kind": "threshold",
            "severity": "high",
            "message": f"Temperature {reading['temperature']:.1f} exceeds max {settings.ALERT_TEMPERATURE_MAX}°C",
        })
    return alerts


def prob_to_severity(p: float) -> str:
    if p >= 0.8:
        return "high"
    if p >= 0.6:
        return "medium"
    return "low"

