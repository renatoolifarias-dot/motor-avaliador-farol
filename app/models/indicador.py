from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON

class Indicador(SQLModel, table=True):
    __tablename__ = "indicadores"
    codigo: str = Field(primary_key=True, max_length=20)
    secao: str = Field(index=True, max_length=20)        # Geral / Saúde / Clima
    dim_key: str = Field(index=True, max_length=50)
    dim_nome: str = Field(max_length=200)
    pergunta: str
    peso: int = 1
    nota_max: float = 1.0
    opcoes_resposta: list = Field(sa_column=Column(JSON), default=[])
    padroes_url_alvo: Optional[list] = Field(sa_column=Column(JSON), default=None)
