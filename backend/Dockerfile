FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# Ensure numeric libs work (scikit-learn / numpy OpenMP)
RUN apt-get update \
  && apt-get install -y --no-install-recommends libgomp1 \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
