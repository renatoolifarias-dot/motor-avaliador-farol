"""Inicializa o banco: roda migrations + seed dos indicadores se vazio + cria admin se vazio."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from alembic.config import Config
from alembic import command
import bcrypt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database import AsyncSessionFactory
from app.models import Usuario, Indicador

# bcrypt direto (passlib quebra)


def run_migrations() -> None:
    """Aplica migrations Alembic (idempotente)."""
    settings = get_settings()
    cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    cfg = Config(str(cfg_path))
    # garante URL sync (alembic não usa asyncpg)
    db_url = settings.database_url.replace("+asyncpg", "+psycopg")
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(cfg_path.parent / "alembic"))
    command.upgrade(cfg, "head")
    print("✓ Migrations aplicadas")


async def seed_indicadores(session: AsyncSession) -> int:
    """Popula tabela indicadores a partir do JSON, se ainda vazia."""
    count = await session.scalar(select(func.count()).select_from(Indicador))
    if count and count > 0:
        print(f"= Indicadores já populados ({count})")
        return 0

    json_path = Path(__file__).parent.parent / "data" / "indicadores.json"
    # fallback: tenta achar em outros lugares
    if not json_path.exists():
        for alt in [
            Path("/app/data/indicadores.json"),
            Path(__file__).parent.parent.parent / "data" / "indicadores.json",
        ]:
            if alt.exists():
                json_path = alt
                break

    if not json_path.exists():
        print(f"⚠ indicadores.json não encontrado (procurou {json_path})")
        return 0

    data = json.loads(json_path.read_text(encoding="utf-8"))
    inds = data.get("indicadores", [])
    inseridos = 0
    for ind in inds:
        novo = Indicador(
            codigo=ind["codigo"],
            secao=ind["secao"],
            dim_key=ind["dim_key"],
            dim_nome=ind["dim_nome"],
            pergunta=ind.get("pergunta", "")[:5000] if ind.get("pergunta") else "",
            peso=int(ind.get("peso", 1)),
            nota_max=float(ind.get("nota_max", 1)),
            opcoes_resposta=ind.get("opcoes_resposta", []),
        )
        session.add(novo)
        inseridos += 1
    await session.commit()
    print(f"✓ {inseridos} indicadores ITGP carregados")
    return inseridos


async def seed_admin(session: AsyncSession) -> bool:
    """Cria usuário admin renato se não existir nenhum admin."""
    count = await session.scalar(
        select(func.count()).select_from(Usuario).where(Usuario.perfil == "admin")
    )
    if count and count > 0:
        print(f"= Admin já existe ({count})")
        return False

    senha_inicial = os.environ.get("ADMIN_INITIAL_PASSWORD", "FarolPublico2026!")
    novo = Usuario(
        username="renato",
        nome_completo="Renato Farias",
        email="renato.oli.farias@gmail.com",
        senha_hash=bcrypt.hashpw(senha_inicial.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8"),
        perfil="admin",
        ativo=True,
        precisa_trocar_senha=True,
    )
    session.add(novo)
    await session.commit()
    print(f"✓ Admin 'renato' criado (senha inicial: {senha_inicial} — TROQUE NO PRIMEIRO LOGIN)")
    return True


async def bootstrap_db() -> None:
    """Entrypoint chamado no startup do app."""
    # Migrations (sync)
    try:
        run_migrations()
    except Exception as e:
        print(f"⚠ migrations falharam (ok se já aplicadas em outra réplica): {e}")

    # Seeds (async)
    async with AsyncSessionFactory() as session:
        await seed_indicadores(session)
        await seed_admin(session)
