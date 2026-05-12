"""Migration inicial — cria todas as tabelas

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-12 22:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===== usuarios =====
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("nome_completo", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), unique=True, nullable=False, index=True),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("perfil", sa.String(20), nullable=False, server_default="avaliador"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("precisa_trocar_senha", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ultimo_login", sa.DateTime(), nullable=True),
    )

    # ===== configs (key-value) =====
    op.create_table(
        "configs",
        sa.Column("chave", sa.String(100), primary_key=True),
        sa.Column("valor", sa.Text(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ===== indicadores =====
    op.create_table(
        "indicadores",
        sa.Column("codigo", sa.String(20), primary_key=True),
        sa.Column("secao", sa.String(20), nullable=False, index=True),
        sa.Column("dim_key", sa.String(50), nullable=False, index=True),
        sa.Column("dim_nome", sa.String(200), nullable=False),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("peso", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("nota_max", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("opcoes_resposta", postgresql.JSONB(), nullable=True),
        sa.Column("padroes_url_alvo", postgresql.JSONB(), nullable=True),
    )

    # ===== avaliacoes =====
    op.create_table(
        "avaliacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("cidade", sa.String(200), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("ciclo", sa.Integer(), nullable=False, server_default="2026", index=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="rascunho"),
        sa.Column("avaliador_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("nota_geral", sa.Float(), nullable=True),
        sa.Column("classificacao", sa.String(20), nullable=True),
        sa.Column("pontuacoes_dimensao", postgresql.JSONB(), nullable=True),
        sa.Column("dossie_resumo", postgresql.JSONB(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("publicado_em", sa.DateTime(), nullable=True),
        sa.Column("url_publica", sa.String(500), nullable=True),
    )

    # ===== avaliacao_itens =====
    op.create_table(
        "avaliacao_itens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("avaliacao_id", sa.Integer(), sa.ForeignKey("avaliacoes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("codigo", sa.String(20), sa.ForeignKey("indicadores.codigo"), nullable=False, index=True),
        sa.Column("nota", sa.Float(), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("url_evidencia", sa.String(1000), nullable=True),
        sa.Column("fontes_consultadas", postgresql.JSONB(), nullable=True),
        sa.Column("o_que_falta", sa.Text(), nullable=True),
        sa.Column("desconto_motivos", postgresql.JSONB(), nullable=True),
        sa.Column("confianca", sa.Float(), nullable=True),
        sa.Column("ia_modelo", sa.String(80), nullable=True),
        sa.Column("ia_gerado_em", sa.DateTime(), nullable=True),
        sa.Column("revisado_humano", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revisor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("revisado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("avaliacao_id", "codigo", name="uq_avaliacao_indicador"),
    )

    # ===== avaliacao_paginas (dossiê do crawler) =====
    op.create_table(
        "avaliacao_paginas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("avaliacao_id", sa.Integer(), sa.ForeignKey("avaliacoes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("url", sa.String(1000), nullable=False, index=True),
        sa.Column("url_final", sa.String(1000), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="html"),
        sa.Column("titulo", sa.String(500), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("capturado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("profundidade", sa.Integer(), nullable=False, server_default="0"),
    )

    # ===== avaliacao_logs =====
    op.create_table(
        "avaliacao_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("avaliacao_id", sa.Integer(), sa.ForeignKey("avaliacoes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("nivel", sa.String(10), nullable=False, server_default="info"),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("avaliacao_logs")
    op.drop_table("avaliacao_paginas")
    op.drop_table("avaliacao_itens")
    op.drop_table("avaliacoes")
    op.drop_table("indicadores")
    op.drop_table("configs")
    op.drop_table("usuarios")
