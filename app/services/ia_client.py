"""Cliente Anthropic para o motor de avaliação.

Encapsula:
- Leitura da api_key e modelo da tabela `configs` (fallback pra env)
- Chamada async com Tool Use
- Retry exponencial em RateLimitError/APIError
- Log estruturado de uso (tokens in/out, custo estimado)

Custos (US$ por 1M tokens, valores aproximados maio/2026):
  claude-haiku-4-5-20251001:  in=0.80   out=4.00
  claude-sonnet-4-6:          in=3.00   out=15.00
  claude-opus-4-6:            in=15.00  out=75.00
"""
from __future__ import annotations
import os
from typing import Any, Optional
import anthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

logger = structlog.get_logger()

PRECOS_USD_POR_MTOK = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
    "claude-opus-4-6":           (15.00, 75.00),
}

MODELO_DEFAULT = "claude-haiku-4-5-20251001"


async def ler_config(session: AsyncSession, chave: str, default: str = "") -> str:
    r = await session.execute(text("SELECT valor FROM configs WHERE chave=:k"), {"k": chave})
    row = r.first()
    return (row[0] if row else default) or default


async def obter_credenciais(session: AsyncSession) -> tuple[str, str]:
    """Retorna (api_key, modelo). Prioriza configs do DB, depois env."""
    api_key = await ler_config(session, "anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
    modelo = await ler_config(session, "modelo_padrao", os.environ.get("ANTHROPIC_MODEL_DEFAULT", MODELO_DEFAULT))
    return api_key, modelo or MODELO_DEFAULT


def estimar_custo_usd(modelo: str, in_tokens: int, out_tokens: int) -> float:
    p_in, p_out = PRECOS_USD_POR_MTOK.get(modelo, (0.0, 0.0))
    return (in_tokens / 1_000_000) * p_in + (out_tokens / 1_000_000) * p_out


class ClienteIA:
    """Wrapper async sobre anthropic SDK com retry e accounting."""

    def __init__(self, api_key: str, modelo: str = MODELO_DEFAULT):
        if not api_key:
            raise ValueError("api_key vazia — configure em /configuracoes/")
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.modelo = modelo
        self.total_in = 0
        self.total_out = 0
        self.total_chamadas = 0

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        )),
        reraise=True,
    )
    async def chamar(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Any:
        """Faz uma chamada à API com Tool Use. Retorna o objeto Message."""
        kwargs = {
            "model": self.modelo,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        resp = await self.client.messages.create(**kwargs)

        # accounting
        self.total_chamadas += 1
        self.total_in += resp.usage.input_tokens
        self.total_out += resp.usage.output_tokens
        logger.info(
            "ia_chamada",
            modelo=self.modelo,
            in_tokens=resp.usage.input_tokens,
            out_tokens=resp.usage.output_tokens,
            stop_reason=resp.stop_reason,
        )
        return resp

    def custo_acumulado_usd(self) -> float:
        return estimar_custo_usd(self.modelo, self.total_in, self.total_out)

    def resumo_uso(self) -> str:
        return (
            f"{self.total_chamadas} chamada(s) ao {self.modelo} · "
            f"{self.total_in:,} tokens entrada + {self.total_out:,} saída · "
            f"~US$ {self.custo_acumulado_usd():.4f}"
        )


async def cliente_da_sessao(session: AsyncSession) -> ClienteIA:
    api_key, modelo = await obter_credenciais(session)
    return ClienteIA(api_key=api_key, modelo=modelo)
