# Two-stage so model weights are baked into the image rather than downloaded at
# container start. An air-gapped deployment (ADR 0003) cannot reach the Hugging
# Face hub at runtime.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf

WORKDIR /app

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download weights into the image.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('Alibaba-NLP/gte-modernbert-base', device='cpu')"

COPY src/ src/
COPY scripts/ scripts/
COPY eval/ eval/
COPY data/raw/ data/raw/

# Build the index at image build time so the container starts ready to serve.
RUN python src/index/build_index.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
