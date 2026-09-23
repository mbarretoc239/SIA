"""Métricas locais de tráfego PostgREST para diagnóstico de egress.

Integração prevista em shared/database.py: substituir o requests.get usado
pelo _get_paginado por supabase_get e fornecer o rótulo da operação. Este
módulo deliberadamente não persiste métricas no banco: usa logging (stdout)
para não gerar tráfego adicional no Supabase.

Importante: bytes_body é o tamanho do corpo recebido pelo cliente, não uma
reprodução exata do egress faturado (headers, compressão e contabilização do
provedor podem diferir). Nunca registra URL completa, query string, headers,
tokens, nem conteúdo dos registros.
"""

import logging
import time
from urllib.parse import urlsplit

import requests

_LOG = logging.getLogger("sia.egress")


def _endpoint_label(url: str) -> str:
    """Retorna apenas o segmento do recurso REST, sem host ou parâmetros."""
    path = urlsplit(url).path
    marker = "/rest/v1/"
    if marker in path:
        return path.split(marker, 1)[1].strip("/") or "root"
    return "non_postgrest"


def supabase_get(url: str, *, operation: str = "unspecified", **kwargs):
    """Executa GET e emite uma linha JSON de métricas agregáveis no log.

    `operation` deve ser um rótulo estático de código (não dado do usuário).
    A contagem de linhas é obtida do JSON já necessário à aplicação, sem uma
    segunda leitura ou chamada de rede. Para respostas não-JSON, fica nula.
    """
    started = time.monotonic()
    response = requests.get(url, **kwargs)
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    body_size = len(response.content or b"")
    rows = None
    if response.status_code in (200, 206):
        try:
            payload = response.json()
            if isinstance(payload, list):
                rows = len(payload)
        except (ValueError, requests.exceptions.JSONDecodeError):
            pass
    _LOG.info(
        "supabase_egress operation=%s endpoint=%s status=%s bytes_body=%d rows=%s duration_ms=%s",
        str(operation)[:80], _endpoint_label(url), response.status_code,
        body_size, rows if rows is not None else "na", elapsed_ms,
    )
    return response
