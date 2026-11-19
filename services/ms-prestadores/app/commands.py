"""Lado de comando (docs/04, 3.3): valida, grava no Write DB e registra o evento na outbox (mesma transação)."""
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.http import ApiError
from app.messaging import registrar_evento
from app.models import Prestador, agora

CATEGORIAS = ["eletricista", "encanador", "tecnico-gas", "pedreiro", "pintor", "marceneiro", "chaveiro",
              "instalador"]


def _normalizar_categorias(v: list[str]) -> list[str]:
    cats = sorted({c.strip().lower() for c in v if c.strip()})
    invalidas = [c for c in cats if c not in CATEGORIAS]
    if invalidas:
        raise ValueError(f"categorias inválidas: {invalidas}. Válidas: {CATEGORIAS}")
    return cats


class Localizacao(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class CadastrarPrestador(BaseModel):
    prestadorId: str | None = Field(default=None, pattern=r"^prest_[a-z0-9_]{1,40}$")
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    fotoUrl: str | None = None
    categorias: list[str] = Field(min_length=1)
    cidade: str = Field(min_length=2)
    uf: str = Field(min_length=2, max_length=2)
    bairrosAtendidos: list[str] = Field(default_factory=list)
    localizacao: Localizacao | None = None
    raioAtendimentoKm: int = Field(default=10, ge=1, le=200)
    precoMedioCentavos: int | None = Field(default=None, ge=0)

    @field_validator("categorias")
    @classmethod
    def _cats(cls, v):
        return _normalizar_categorias(v)


class AtualizarPerfil(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    fotoUrl: str | None = None
    categorias: list[str] | None = Field(default=None, min_length=1)
    cidade: str | None = Field(default=None, min_length=2)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    precoMedioCentavos: int | None = Field(default=None, ge=0)

    @field_validator("categorias")
    @classmethod
    def _cats(cls, v):
        return _normalizar_categorias(v) if v is not None else v


class DefinirAreasAtendimento(BaseModel):
    bairrosAtendidos: list[str]
    raioAtendimentoKm: int = Field(ge=1, le=200)
    localizacao: Localizacao | None = None


# campos públicos do agregado que vão para o evento (contato NÃO vai para o modelo de leitura)
PUBLICOS = {"nome": "nome", "fotoUrl": "foto_url", "categorias": "categorias", "cidade": "cidade", "uf": "uf",
            "precoMedioCentavos": "preco_medio_centavos"}


def representar(p: Prestador) -> dict:
    """Representação do modelo de escrita (resposta dos comandos: consistência imediata para quem editou)."""
    return {
        "prestadorId": p.id, "nome": p.nome, "email": p.email, "telefone": p.telefone, "fotoUrl": p.foto_url,
        "categorias": p.categorias, "cidade": p.cidade, "uf": p.uf, "bairrosAtendidos": p.bairros_atendidos,
        "localizacao": {"lat": p.lat, "lon": p.lon} if p.lat is not None else None,
        "raioAtendimentoKm": p.raio_atendimento_km, "precoMedioCentavos": p.preco_medio_centavos,
        "ativo": p.ativo, "versao": p.versao, "atualizadoEm": p.atualizado_em.isoformat(),
        "_links": {"self": {"href": f"/v1/prestadores/{p.id}", "method": "GET"},
                   "areasAtendimento": {"href": f"/v1/prestadores/{p.id}/areas-atendimento", "method": "PUT"}},
    }


def _obter(s: Session, prestador_id: str) -> Prestador:
    p = s.get(Prestador, prestador_id, with_for_update=True)
    if not p:
        raise ApiError(404, "Not Found", f"Prestador {prestador_id} não encontrado.")
    return p


def _commit(s: Session) -> None:
    try:
        s.commit()
    except IntegrityError as exc:
        s.rollback()
        raise ApiError(409, "Conflict", "Prestador ou e-mail já cadastrado.",
                       "https://api.resolvelar.com.br/erros/prestador-duplicado") from exc


def cadastrar(s: Session, cmd: CadastrarPrestador) -> Prestador:
    pid = cmd.prestadorId or f"prest_{uuid.uuid4().hex[:8]}"
    if s.get(Prestador, pid):
        raise ApiError(409, "Conflict", f"Prestador {pid} já existe.",
                       "https://api.resolvelar.com.br/erros/prestador-duplicado")
    p = Prestador(
        id=pid, nome=cmd.nome, email=cmd.email, telefone=cmd.telefone, foto_url=cmd.fotoUrl,
        categorias=cmd.categorias, cidade=cmd.cidade, uf=cmd.uf.upper(), bairros_atendidos=cmd.bairrosAtendidos,
        lat=cmd.localizacao.lat if cmd.localizacao else None, lon=cmd.localizacao.lon if cmd.localizacao else None,
        raio_atendimento_km=cmd.raioAtendimentoKm, preco_medio_centavos=cmd.precoMedioCentavos, versao=1,
    )
    s.add(p)
    registrar_evento(s, "PrestadorCadastrado", pid, p.versao, {
        "prestadorId": pid, "nome": p.nome, "fotoUrl": p.foto_url, "categorias": p.categorias,
        "cidade": p.cidade, "uf": p.uf, "bairrosAtendidos": p.bairros_atendidos,
        "localizacao": cmd.localizacao.model_dump() if cmd.localizacao else None,
        "raioAtendimentoKm": p.raio_atendimento_km, "precoMedioCentavos": p.preco_medio_centavos,
    })
    _commit(s)
    s.refresh(p)
    return p


def atualizar_perfil(s: Session, prestador_id: str, cmd: AtualizarPerfil) -> Prestador:
    p = _obter(s, prestador_id)
    if not p.ativo:
        raise ApiError(409, "Conflict", "Prestador desativado não pode ser alterado.")
    mudancas, alterou = {}, False
    campos = cmd.model_dump(exclude_unset=True)
    for chave, valor in campos.items():
        coluna = {"fotoUrl": "foto_url", "precoMedioCentavos": "preco_medio_centavos"}.get(chave, chave)
        if chave == "uf" and valor:
            valor = valor.upper()
        if getattr(p, coluna) != valor:
            setattr(p, coluna, valor)
            alterou = True
            if chave in PUBLICOS:
                mudancas[chave] = valor
    if not alterou:
        return p  # nada mudou: sem nova versão nem evento
    p.versao += 1
    p.atualizado_em = agora()
    s.add(p)
    # só gera evento se algo público mudou (e-mail/telefone ficam só no modelo de escrita)
    registrar_evento(s, "PerfilPrestadorAtualizado", p.id, p.versao, {"prestadorId": p.id, **mudancas})
    _commit(s)
    s.refresh(p)
    return p


def definir_areas(s: Session, prestador_id: str, cmd: DefinirAreasAtendimento) -> Prestador:
    p = _obter(s, prestador_id)
    if not p.ativo:
        raise ApiError(409, "Conflict", "Prestador desativado não pode ser alterado.")
    p.bairros_atendidos = sorted({b.strip() for b in cmd.bairrosAtendidos if b.strip()})
    p.raio_atendimento_km = cmd.raioAtendimentoKm
    if cmd.localizacao:
        p.lat, p.lon = cmd.localizacao.lat, cmd.localizacao.lon
    p.versao += 1
    p.atualizado_em = agora()
    s.add(p)
    registrar_evento(s, "AreasAtendimentoAlteradas", p.id, p.versao, {
        "prestadorId": p.id, "bairrosAtendidos": p.bairros_atendidos, "raioAtendimentoKm": p.raio_atendimento_km,
        "localizacao": {"lat": p.lat, "lon": p.lon} if p.lat is not None else None,
    })
    _commit(s)
    s.refresh(p)
    return p


def desativar(s: Session, prestador_id: str) -> None:
    p = _obter(s, prestador_id)
    if not p.ativo:
        return  # idempotente
    p.ativo = False
    p.versao += 1
    p.atualizado_em = agora()
    s.add(p)
    registrar_evento(s, "PrestadorDesativado", p.id, p.versao, {"prestadorId": p.id, "ativo": False})
    _commit(s)


def vazio(s: Session) -> bool:
    return s.exec(select(Prestador.id).limit(1)).first() is None
