from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON

class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacoes"
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True, max_length=100)
    cidade: str = Field(max_length=200)
    uf: str = Field(max_length=2)
    ciclo: int = Field(default=2026, index=True)
    status: str = Field(default="rascunho", max_length=40)
    # rascunho → descobrindo_portais → crawleando → avaliando_ia → aguardando_revisao
    # → confirmado → publicado
    avaliador_id: Optional[int] = Field(default=None, foreign_key="usuarios.id")
    nota_geral: Optional[float] = None
    classificacao: Optional[str] = Field(default=None, max_length=20)
    pontuacoes_dimensao: Optional[dict] = Field(sa_column=Column(JSON), default=None)
    dossie_resumo: Optional[dict] = Field(sa_column=Column(JSON), default=None)
    criado_em: datetime = Field(default_factory=datetime.utcnow, index=True)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    publicado_em: Optional[datetime] = None
    url_publica: Optional[str] = Field(default=None, max_length=500)


class AvaliacaoItem(SQLModel, table=True):
    __tablename__ = "avaliacao_itens"
    id: Optional[int] = Field(default=None, primary_key=True)
    avaliacao_id: int = Field(foreign_key="avaliacoes.id", index=True)
    codigo: str = Field(foreign_key="indicadores.codigo", index=True, max_length=20)
    nota: Optional[float] = None
    justificativa: Optional[str] = None
    url_evidencia: Optional[str] = Field(default=None, max_length=1000)
    fontes_consultadas: Optional[list] = Field(sa_column=Column(JSON), default=None)
    o_que_falta: Optional[str] = None           # recomendação acionável (Requisito #7)
    desconto_motivos: Optional[list] = Field(sa_column=Column(JSON), default=None)
    confianca: Optional[float] = None
    ia_modelo: Optional[str] = Field(default=None, max_length=80)
    ia_gerado_em: Optional[datetime] = None
    revisado_humano: bool = Field(default=False)
    revisor_id: Optional[int] = Field(default=None, foreign_key="usuarios.id")
    revisado_em: Optional[datetime] = None


class AvaliacaoPagina(SQLModel, table=True):
    """Dossiê: cada página crawleada."""
    __tablename__ = "avaliacao_paginas"
    id: Optional[int] = Field(default=None, primary_key=True)
    avaliacao_id: int = Field(foreign_key="avaliacoes.id", index=True)
    url: str = Field(max_length=1000, index=True)
    url_final: Optional[str] = Field(default=None, max_length=1000)
    status_code: Optional[int] = None
    tipo: str = Field(default="html", max_length=20)  # html | pdf | doc | image
    titulo: Optional[str] = Field(default=None, max_length=500)
    texto: Optional[str] = None                       # texto extraído (pode ser longo)
    capturado_em: datetime = Field(default_factory=datetime.utcnow)
    profundidade: int = Field(default=0)


class AvaliacaoLog(SQLModel, table=True):
    __tablename__ = "avaliacao_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    avaliacao_id: int = Field(foreign_key="avaliacoes.id", index=True)
    nivel: str = Field(default="info", max_length=10)  # info | warn | error
    mensagem: str
    criado_em: datetime = Field(default_factory=datetime.utcnow, index=True)
