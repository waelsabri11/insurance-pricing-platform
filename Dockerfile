# Quote API only: the tariff and the optimized multipliers are JSON files, so the image needs
# FastAPI and nothing from the training stack (no pandas, scipy, statsmodels or scikit-learn).
FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install fastapi==0.157.0 pydantic==2.14.1 uvicorn==0.54.0 \
    && useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY src/pricing/__init__.py src/pricing/rating.py src/pricing/demand.py src/pricing/offer.py src/pricing/api.py src/pricing/
COPY models/tariff.json models/price_optimization.json models/
ENV PYTHONPATH=/app/src
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "pricing.api:app", "--host", "0.0.0.0", "--port", "8000"]
