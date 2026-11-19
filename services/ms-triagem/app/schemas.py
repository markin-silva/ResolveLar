from typing import Literal

from pydantic import BaseModel, Field

CATEGORIAS = ("eletricista", "encanador", "tecnico-gas", "pedreiro", "pintor", "marceneiro", "chaveiro",
              "instalador")
Categoria = Literal["eletricista", "encanador", "tecnico-gas", "pedreiro", "pintor", "marceneiro", "chaveiro",
                    "instalador"]
Urgencia = Literal["EMERGENCIA", "ALTA", "MEDIA", "BAIXA"]


class Classificacao(BaseModel):
    """Saída estruturada do LLM (e do fallback)."""

    categoria: Categoria = Field(description="Categoria de prestador mais adequada")
    urgencia: Urgencia = Field(description="Nível de urgência segundo os critérios do contexto")
    resumo: str = Field(description="Resumo do problema em uma frase, em português")
    orientacoesSeguranca: list[str] = Field(
        description="De 2 a 5 orientações práticas e imediatas de segurança, em português, baseadas no contexto")
    perguntasComplementares: list[str] = Field(
        description="Até 2 perguntas curtas que ajudem o prestador a entender o problema")


class TriagemIn(BaseModel):
    descricao: str = Field(min_length=10, max_length=2000, examples=["Meu chuveiro parou de esquentar e o disjuntor desarma"])
    cidade: str | None = Field(default=None, examples=["Lavras"])
    uf: str | None = Field(default=None, min_length=2, max_length=2)
