# Quote API only: the tariff is a JSON file, so the image needs FastAPI and nothing from the
# training stack (no pandas, statsmodels or scikit-learn).
FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi==0.157.0 pydantic==2.14.1 uvicorn==0.54.0 \
    && useradd --create-home app
WORKDIR /app
COPY src/pricing/__init__.py src/pricing/rating.py src/pricing/api.py src/pricing/
COPY models/tariff.json models/
ENV PYTHONPATH=/app/src
USER app
EXPOSE 8000
CMD ["uvicorn", "pricing.api:app", "--host", "0.0.0.0", "--port", "8000"]
