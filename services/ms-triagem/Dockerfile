# ---- Stage 1: builder (gera wheels das dependências) ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/chroma && chown -R appuser:appuser /data
USER appuser

# Baixa o modelo de embeddings (all-MiniLM-L6-v2, ONNX) no build: em runtime o serviço fica na
# internal_net e o RAG funciona sem internet.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['aquecimento'])"

COPY --chown=appuser:appuser app ./app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
