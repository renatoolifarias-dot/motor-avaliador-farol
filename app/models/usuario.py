from datetime import datetime
from app.services.tz import now_bahia
from typing import Optional
from sqlmodel import SQLModel, Field

class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=64)
    nome_completo: str = Field(max_length=200)
    email: str = Field(unique=True, index=True, max_length=200)
    senha_hash: str = Field(max_length=255)
    perfil: str = Field(default="avaliador", max_length=20)  # admin | avaliador
    ativo: bool = Field(default=True)
    precisa_trocar_senha: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=now_bahia)
    ultimo_login: Optional[datetime] = None
