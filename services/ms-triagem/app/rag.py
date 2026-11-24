"""RAG: base de conhecimento em Markdown (app/conhecimento) indexada no ChromaDB embarcado.

Cada seção `## ...` vira um chunk. Embeddings locais (all-MiniLM-L6-v2 via ONNX, baixado no build da
imagem), então a busca semântica funciona sem internet e sem chave de API. O índice é refeito quando o
conteúdo dos .md muda (hash guardado nos metadados da coleção).
"""
import hashlib
import logging
import os
import re
import threading
from functools import cached_property
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

logger = logging.getLogger("app.rag")


class _OnnxPoucasThreads(ONNXMiniLM_L6_V2):
    """Mesmo modelo do Chroma, com poucas threads: dentro do Docker, junto de ~20 contêineres, o ONNX
    tentando usar todos os núcleos disputa CPU e fica mais lento, não mais rápido."""

    def __init__(self, threads: int):
        super().__init__(preferred_providers=["CPUExecutionProvider"])
        self._threads = threads

    @cached_property
    def model(self):
        so = self.ort.SessionOptions()
        so.log_severity_level = 3
        so.graph_optimization_level = self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = self._threads
        so.inter_op_num_threads = 1
        return self.ort.InferenceSession(os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx"),
                                         providers=["CPUExecutionProvider"], sess_options=so)


class EmbeddingLocal(DefaultEmbeddingFunction):
    """Equivale ao embedding "default" do Chroma (mesmo modelo e mesmo nome, então o índice continua
    compatível), mas reaproveita UMA sessão ONNX. O `DefaultEmbeddingFunction` original cria um modelo novo a
    cada chamada, ou seja, recarregava os 79 MB do modelo a cada triagem (1 a 3 s em vez de ~0,05 s)."""

    def __init__(self, threads: int = 2):
        super().__init__()
        self._onnx = _OnnxPoucasThreads(threads)
        self._lock = threading.Lock()

    def __call__(self, input):
        with self._lock:
            return self._onnx(input)

DIR = Path(__file__).parent / "conhecimento"
COLECAO = "base_conhecimento"


def carregar_chunks() -> list[dict]:
    chunks = []
    for md in sorted(DIR.glob("*.md")):
        texto = md.read_text(encoding="utf-8")
        titulo_doc = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), md.stem)
        for bloco in re.split(r"(?m)^## ", texto)[1:]:
            secao, _, corpo = bloco.partition("\n")
            secao, corpo = secao.strip(), corpo.strip()
            if not corpo:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", secao.lower()).strip("-")
            chunks.append({"id": f"{md.stem}#{slug}", "texto": f"{titulo_doc} — {secao}\n{corpo}",
                           "fonte": md.name, "secao": secao})
    return chunks


class BaseConhecimento:
    def __init__(self, path: str, threads: int = 2):
        self.client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self.ef = EmbeddingLocal(threads)
        self.colecao = None

    def aquecer(self) -> None:
        """Carrega o modelo e faz uma busca na subida: a primeira triagem não paga o custo de carregar."""
        self.buscar("aquecimento da base de conhecimento", 1)

    def indexar(self) -> int:
        chunks = carregar_chunks()
        digest = hashlib.sha256("".join(c["id"] + c["texto"] for c in chunks).encode()).hexdigest()[:16]
        col = self.client.get_or_create_collection(COLECAO, embedding_function=self.ef,
                                                   metadata={"hnsw:space": "cosine", "hash": digest})
        if (col.metadata or {}).get("hash") != digest or col.count() != len(chunks):
            logger.info("Reindexando base de conhecimento (%s chunks)", len(chunks))
            self.client.delete_collection(COLECAO)
            col = self.client.create_collection(COLECAO, embedding_function=self.ef,
                                                metadata={"hnsw:space": "cosine", "hash": digest})
            col.add(ids=[c["id"] for c in chunks], documents=[c["texto"] for c in chunks],
                    metadatas=[{"fonte": c["fonte"], "secao": c["secao"]} for c in chunks])
        self.colecao = col
        return col.count()

    def buscar(self, consulta: str, k: int = 4) -> list[dict]:
        if self.colecao is None:
            return []
        res = self.colecao.query(query_texts=[consulta], n_results=k)
        return [
            {"texto": doc, "fonte": meta["fonte"], "secao": meta["secao"], "distancia": round(dist, 4)}
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def total(self) -> int:
        return self.colecao.count() if self.colecao is not None else 0
