import pandas as pd


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.assign(timestamp=ts.dt.tz_convert(None))
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["vibration","temperature","current","rpm","load_pct"]:
        df[f"{col}_roll_mean"] = df[col].rolling(5, min_periods=1).mean()
        df[f"{col}_roll_std"] = df[col].rolling(5, min_periods=1).std().fillna(0.0)
    return df
