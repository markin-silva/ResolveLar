"""Lado de consulta (docs/04, 3.4): lê SOMENTE o Read DB desnormalizado, com cache Redis."""
from sqlalchemy import func
from sqlmodel import Session, col, select

from app import cache
from app.config import get_settings
from app.database import read_engine
from app.models import PrestadorView


def documento(v: PrestadorView) -> dict:
    return {
        "prestadorId": v.prestador_id, "nome": v.nome, "fotoUrl": v.foto_url, "categorias": v.categorias,
        "cidade": v.cidade, "uf": v.uf, "bairrosAtendidos": v.bairros_atendidos,
        "localizacao": {"lat": v.lat, "lon": v.lon} if v.lat is not None else None,
        "raioAtendimentoKm": v.raio_atendimento_km, "notaMedia": round(v.nota_media, 2),
        "totalAvaliacoes": v.total_avaliacoes, "servicosConcluidos": v.servicos_concluidos,
        "disponivelHoje": v.disponivel_hoje, "precoMedioCentavos": v.preco_medio_centavos, "ativo": v.ativo,
        "versao": v.versao, "atualizadoEm": v.atualizado_em.isoformat(),
        "_links": {"self": {"href": f"/v1/prestadores/{v.prestador_id}", "method": "GET"}},
    }


def buscar(cidade: str | None, categoria: str | None, page: int, size: int) -> tuple[dict, bool]:
    """Retorna (resultado, veio_do_cache)."""
    key = f"busca:{(cidade or '').lower()}:{(categoria or '').lower()}:{page}:{size}"
    cached = cache.get_json(key)
    if cached is not None:
        return cached, True

    filtros = [col(PrestadorView.ativo).is_(True)]
    if cidade:
        filtros.append(func.lower(PrestadorView.cidade) == cidade.strip().lower())
    if categoria:
        filtros.append(col(PrestadorView.categorias).contains([categoria.strip().lower()]))

    with Session(read_engine()) as s:
        total = s.exec(select(func.count()).select_from(PrestadorView).where(*filtros)).one()
        stmt = (select(PrestadorView).where(*filtros)
                .order_by(col(PrestadorView.nota_media).desc(), col(PrestadorView.total_avaliacoes).desc(),
                          PrestadorView.prestador_id)
                .offset((page - 1) * size).limit(size))
        items = [documento(v) for v in s.exec(stmt).all()]

    params = "&".join(f"{k}={v}" for k, v in (("cidade", cidade), ("categoria", categoria)) if v)
    base = f"/v1/prestadores?{params + '&' if params else ''}size={size}"
    links = {"self": {"href": f"{base}&page={page}", "method": "GET"}}
    if page * size < total:
        links["next"] = {"href": f"{base}&page={page + 1}", "method": "GET"}
    if page > 1:
        links["prev"] = {"href": f"{base}&page={page - 1}", "method": "GET"}

    result = {"items": items, "page": page, "size": size, "total": total, "_links": links}
    cache.set_json(key, result, get_settings().SEARCH_CACHE_TTL_SECONDS)
    return result, False


def detalhar(prestador_id: str) -> tuple[dict | None, bool]:
    key = cache.chave_prestador(prestador_id)
    cached = cache.get_json(key)
    if cached is not None:
        return cached, True
    with Session(read_engine()) as s:
        v = s.get(PrestadorView, prestador_id)
    if v is None or v.versao == 0:  # versao 0 = só reputação recebida, cadastro ainda não projetado
        return None, False
    doc = documento(v)
    cache.set_json(key, doc, get_settings().CACHE_TTL_SECONDS)
    return doc, False
