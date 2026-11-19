"""RAG: base de conhecimento em Markdown (app/conhecimento) indexada no ChromaDB embarcado.

Cada seção `## ...` vira um chunk. Embeddings locais (all-MiniLM-L6-v2 via ONNX, baixado no build da
imagem), então a busca semântica funciona sem internet e sem chave de API. O índice é refeito quando o
conteúdo dos .md muda (hash guardado nos metadados da coleção).
"""
import hashlib
import logging
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

logger = logging.getLogger("app.rag")

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
    def __init__(self, path: str):
        self.client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self.ef = DefaultEmbeddingFunction()
        self.colecao = None

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
