import os, joblib, httpx, pandas as pd, numpy as np, json
from ..core.config import settings
from ..services.features import build_features

FEATURES = [
    "vibration","temperature","current","rpm","load_pct",
    "vibration_roll_mean","temperature_roll_mean","current_roll_mean","rpm_roll_mean","load_pct_roll_mean",
    "vibration_roll_std","temperature_roll_std","current_roll_std","rpm_roll_std","load_pct_roll_std"
]

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

# Google Generative AI provider (optional)
GOOGLE_MODEL = os.getenv("GOOGLE_GENAI_MODEL", settings.GOOGLE_GENAI_MODEL)

_local_model = None


def _provider() -> str:
    return os.getenv("MODEL_PROVIDER", settings.MODEL_PROVIDER).lower()


def _external_conf():
    url = os.getenv("EXTERNAL_MODEL_URL", settings.EXTERNAL_MODEL_URL)
    key = os.getenv("EXTERNAL_MODEL_API_KEY", settings.EXTERNAL_MODEL_API_KEY)
    timeout = float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", str(settings.EXTERNAL_TIMEOUT_SECONDS)))
    return url, key, timeout


def _google_conf():
    api_key = os.getenv("GOOGLE_GENAI_API_KEY", settings.GOOGLE_GENAI_API_KEY)
    model = os.getenv("GOOGLE_GENAI_MODEL", settings.GOOGLE_GENAI_MODEL)
    return api_key, model


def current_provider() -> str:
    """Expose the active provider for downstream modules."""
    return _provider()


def google_configured() -> dict:
    """Return Google provider metadata for diagnostics."""
    api_key, model = _google_conf()
    return {"model": model, "configured": bool(api_key)}


class _HeuristicModel:
    """Lightweight fallback when sklearn pickle is incompatible.

    Exposes a sklearn-like predict_proba API returning [p0, p1].
    """

    def predict_proba(self, X):
        # Accept pandas DataFrame or numpy array with named columns in DataFrame
        if hasattr(X, "__getitem__") and hasattr(X, "columns"):
            def g(name, default=0.0):
                try:
                    return X[name].to_numpy(dtype=float)
                except Exception:
                    return np.full((len(X),), default, dtype=float)

            temp = g("temperature")
            vib = g("vibration")
            cur = g("current")
            rpm = g("rpm")
            load = g("load_pct")
            vib_std = g("vibration_roll_std")
            temp_std = g("temperature_roll_std")
        else:
            # If array-like without names, assume column order of FEATURES
            arr = np.asarray(X, dtype=float)
            idx = {name: i for i, name in enumerate(FEATURES)}
            def gi(name, default=0.0):
                i = idx.get(name, None)
                return arr[:, i] if i is not None else np.full((arr.shape[0],), default, dtype=float)
            temp = gi("temperature")
            vib = gi("vibration")
            cur = gi("current")
            rpm = gi("rpm")
            load = gi("load_pct")
            vib_std = gi("vibration_roll_std")
            temp_std = gi("temperature_roll_std")

        # Normalize to rough operating ranges
        temp_n = np.clip((temp - 30.0) / 70.0, 0.0, 1.0)      # 30-100 C
        vib_n = np.clip(vib / 10.0, 0.0, 1.0)                 # 0-10 mm/s
        cur_n = np.clip((cur - 5.0) / 20.0, 0.0, 1.0)         # 5-25 A
        rpm_n = np.clip((2000.0 - np.abs(rpm - 2000.0)) / 2000.0, 0.0, 1.0)
        load_n = np.clip(load / 100.0, 0.0, 1.0)
        vib_std_n = np.clip(vib_std / 5.0, 0.0, 1.0)
        temp_std_n = np.clip(temp_std / 10.0, 0.0, 1.0)

        # Weighted heuristic risk score
        score = (
            0.30 * vib_n +
            0.25 * temp_n +
            0.15 * load_n +
            0.10 * (1.0 - rpm_n) +
            0.10 * cur_n +
            0.05 * vib_std_n +
            0.05 * temp_std_n
        )
        p1 = np.clip(score, 0.0, 1.0)
        p0 = 1.0 - p1
        return np.stack([p0, p1], axis=1)


def _load_local_model():
    global _local_model
    if _local_model is None:
        try:
            _local_model = joblib.load(MODEL_PATH)
        except Exception:
            # Fallback to heuristic model if pickle is incompatible
            _local_model = _HeuristicModel()
    return _local_model

def _local_predict_proba_one(readings: list[dict]) -> float:
    df = pd.DataFrame(readings); df = build_features(df)
    x = df[FEATURES].iloc[[-1]]
    proba = _load_local_model().predict_proba(x)[0,1]
    return float(proba)

def _external_predict_proba_one(readings: list[dict]) -> float:
    url, key, timeout = _external_conf()
    if not url:
        raise RuntimeError("EXTERNAL_MODEL_URL is not set")
    df = pd.DataFrame(readings); df = build_features(df)
    features = df[FEATURES].iloc[[-1]].to_dict(orient="records")[0]
    headers = {"Content-Type":"application/json"}
    if key: headers["Authorization"] = f"Bearer {key}"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json={"features": features}); r.raise_for_status()
        p = float(r.json().get("probability", 0.0))
        return max(0.0, min(1.0, p))


def _google_predict_proba_one(readings: list[dict]) -> float:
    api_key, model = _google_conf()
    if not api_key:
        raise RuntimeError("GOOGLE_GENAI_API_KEY is not set")
    # Build features locally (same as external/local path)
    df = pd.DataFrame(readings)
    df = build_features(df)
    features = df[FEATURES].iloc[[-1]].to_dict(orient="records")[0]

    # Compose structured prompt for maintenance risk scoring
    system = {
        "role": "model",
        "parts": [{
            "text": (
                "You are an industrial maintenance risk assessor. "
                "Given time-series telemetry for logistics equipment, return a JSON object of the form "
                "{\"probability\": number} where probability is a value between 0 and 1 representing the likelihood "
                "of a failure within the next 24 hours. "
                "Do not include any additional keys or text."
            )
        }]
    }
    user = {
        "role": "user",
        "parts": [{
            "text": json.dumps({
                "task": "predict_failure_probability",
                "asset_type": readings[-1].get("type", "logistics_equipment"),
                "features": features,
                "explanation_required": False,
            })
        }]
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "system_instruction": system,
        "contents": [user],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 64,
        },
    }
    _, _, timeout = _external_conf()
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        r.raise_for_status()
        data = r.json()
        # Best-effort parse; pull first candidate text and parse JSON
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        try:
            obj = json.loads(text)
            p = float(obj.get("probability", 0.0))
        except Exception:
            # Fallback attempt: try to extract a float from text
            import re

            m = re.search(r"\d*\.?\d+", text)
            p = float(m.group()) if m else 0.0
        return max(0.0, min(1.0, p))

def predict_proba_one(readings: list[dict]) -> float:
    provider = _provider()
    if provider == "external":
        try:
            return _external_predict_proba_one(readings)
        except Exception:
            return _local_predict_proba_one(readings)
    if provider == "google":
        try:
            return _google_predict_proba_one(readings)
        except Exception:
            return _local_predict_proba_one(readings)
    return _local_predict_proba_one(readings)
