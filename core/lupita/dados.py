"""Acesso da Lupita ao Supabase, com travas contra estouro de egress.

Regras (ver docs/turso_bloqueado_2026-09-23.md, o estouro de cota de 23/09):
  * toda leitura passa por `_ler`: sem select de todas as colunas e sempre com `limit` explícito;
  * escritas usam `return=minimal` (devolver a linha conta como egress);
  * a lista de análises nunca traz `medidas`/`contrib` (as colunas pesadas);
  * `medidas` só é lida em `amostras_treino`, por clique explícito, com teto de linhas;
  * nada aqui roda no topo do app.py nem em rerun: quem chama deve cachear (ver views/10_Lupita.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from core.lupita.acesso import exigir_acesso

TABELA_MODELOS = "lupita_modelos"
TABELA_IMAGENS = "lupita_imagens"

LIMITE_MAXIMO_POR_LEITURA = 1000     # teto de qualquer leitura que não seja a de treino
TETO_AMOSTRAS_TREINO = 20000         # ~10 MB de tráfego por retreino (≈0,5 KB por amostra)
BYTES_POR_AMOSTRA_APROX = 500
TIMEOUT = 20


class LupitaDadosErro(RuntimeError):
    pass


class LeituraNaoPermitida(ValueError):
    """Leitura sem limit, pedindo todas as colunas ou acima do teto: barrada antes de ir ao banco."""


def _validar_leitura(select: str, limite: int, teto: int) -> None:
    if not select or select.strip() == "*" or "*" in select.split(","):
        raise LeituraNaoPermitida("Pedir todas as colunas não é permitido: liste só as necessárias.")
    if not isinstance(limite, int) or limite < 1:
        raise LeituraNaoPermitida("Toda leitura precisa de um limit explícito (>= 1).")
    if limite > teto:
        raise LeituraNaoPermitida(f"limit {limite} acima do teto {teto} desta leitura.")


class LupitaRepo:
    """`db` é o DatabaseManager (st.session_state.db); `usuario_sigo` e `role` são de quem está logado."""

    def __init__(self, db, usuario_sigo: str, role: str | None = None, usuario_id=None,
                 acesso_script: bool = False):
        self.db = db
        self.usuario = str(usuario_sigo or "").strip().upper()
        self.role = role
        self.usuario_id = usuario_id
        self.acesso_script = acesso_script   # só scripts de linha de comando (sem sessão do app)

    # ------------------------------------------------------------ infraestrutura
    def _headers(self, **extra) -> dict:
        if not self.acesso_script:
            exigir_acesso(self.usuario, self.role, self.usuario_id)
        return {**self.db._admin_headers(), **extra}

    def _url(self, tabela: str) -> str:
        return f"{self.db.supabase_url}/rest/v1/{tabela}"

    def _checar(self, r: requests.Response, o_que: str) -> None:
        if r.status_code not in (200, 201, 204, 206):
            raise LupitaDadosErro(f"{o_que}: HTTP {r.status_code} -- {r.text[:200]}")

    def _ler(self, tabela: str, select: str, filtros: dict | None = None, *, limite: int,
             ordem: str | None = None, teto: int = LIMITE_MAXIMO_POR_LEITURA) -> list[dict]:
        _validar_leitura(select, limite, teto)
        params = {"select": select, "limit": str(limite), **(filtros or {})}
        if ordem:
            params["order"] = ordem
        r = requests.get(self._url(tabela), headers=self._headers(), params=params, timeout=TIMEOUT)
        self._checar(r, f"Leitura de {tabela}")
        return r.json()

    # ------------------------------------------------------------ modelo
    def versao_ativa(self) -> int | None:
        linhas = self._ler(TABELA_MODELOS, "versao", {"ativo": "eq.true"}, limite=1)
        return linhas[0]["versao"] if linhas else None

    def modelo_da_versao(self, versao: int) -> dict | None:
        linhas = self._ler(TABELA_MODELOS, "versao,modelo,metricas,origem,criado_em",
                           {"versao": f"eq.{int(versao)}"}, limite=1)
        return linhas[0] if linhas else None

    def salvar_modelo(self, modelo: dict, origem: str) -> int:
        """Grava como nova versão e ativa. Devolve o número da versão."""
        ultima = self._ler(TABELA_MODELOS, "versao", ordem="versao.desc", limite=1)
        versao = (ultima[0]["versao"] if ultima else 0) + 1
        metricas = modelo.get("validacao_cruzada")
        corpo = {"versao": versao, "ativo": False, "modelo": modelo, "metricas": metricas,
                 "origem": origem, "criado_por": self.usuario}
        r = requests.post(self._url(TABELA_MODELOS), headers=self._headers(Prefer="return=minimal"),
                          json=corpo, timeout=TIMEOUT)
        self._checar(r, "Gravar modelo")
        # índice único parcial: desativa o atual antes de ativar o novo
        r = requests.patch(self._url(TABELA_MODELOS), params={"ativo": "eq.true"},
                           headers=self._headers(Prefer="return=minimal"), json={"ativo": False}, timeout=TIMEOUT)
        self._checar(r, "Desativar modelo anterior")
        r = requests.patch(self._url(TABELA_MODELOS), params={"versao": f"eq.{versao}"},
                           headers=self._headers(Prefer="return=minimal"), json={"ativo": True}, timeout=TIMEOUT)
        self._checar(r, "Ativar modelo novo")
        return versao

    # ------------------------------------------------------------ análises
    def registrar_analise(self, hash_img: str, medidas: list[float], score: float, fora_padrao: bool,
                          contrib: dict, modelo_versao: int | None) -> None:
        """Insere sem ler antes: hash repetido é ignorado pelo banco (0 egress, sem duplicar)."""
        corpo = {"hash_imagem": hash_img, "medidas": medidas, "score": round(score, 5),
                 "fora_padrao": fora_padrao, "contrib": contrib, "modelo_versao": modelo_versao,
                 "usuario": self.usuario, "origem": "upload"}
        r = requests.post(self._url(TABELA_IMAGENS), params={"on_conflict": "hash_imagem"},
                          headers=self._headers(Prefer="resolution=ignore-duplicates,return=minimal"),
                          json=corpo, timeout=TIMEOUT)
        self._checar(r, "Registrar análise")

    def rotular(self, hash_img: str, rotulo: int | None, incerto: bool = False) -> None:
        """Revisão do auditor: 1 = IA, 0 = real, incerto=True = "não sei ao certo". Sem nada desfaz.

        Incerta grava rotulo nulo, então fica fora do treino (que só lê rotulo is not null)."""
        if incerto:
            rotulo = None
        revisada = incerto or rotulo is not None
        corpo = {"rotulo": rotulo, "incerto": bool(incerto),
                 "rotulado_por": self.usuario if revisada else None,
                 "rotulado_em": datetime.now(timezone.utc).isoformat() if revisada else None}
        r = requests.patch(self._url(TABELA_IMAGENS), params={"hash_imagem": f"eq.{hash_img}"},
                           headers=self._headers(Prefer="return=minimal"), json=corpo, timeout=TIMEOUT)
        self._checar(r, "Rotular imagem")

    def historico(self, limite: int = 50) -> list[dict]:
        """Só colunas leves (sem medidas nem contrib). Quem chama deve cachear."""
        return self._ler(TABELA_IMAGENS, "hash_imagem,criado_em,score,fora_padrao,rotulo,incerto,usuario,modelo_versao",
                         {"origem": "eq.upload"}, ordem="criado_em.desc", limite=min(limite, 200))

    # ------------------------------------------------------------ treino
    def contar_rotuladas(self) -> dict:
        """Contagem barata (HEAD, sem corpo): {'ia': n, 'reais': n}."""
        saida = {}
        for nome, valor in (("ia", 1), ("reais", 0)):
            r = requests.head(self._url(TABELA_IMAGENS), params={"rotulo": f"eq.{valor}"},
                              headers=self._headers(Prefer="count=exact"), timeout=TIMEOUT)
            self._checar(r, "Contar amostras")
            saida[nome] = int(r.headers.get("Content-Range", "*/0").split("/")[-1] or 0)
        return saida

    def estimar_mb_treino(self, total: int) -> float:
        return total * BYTES_POR_AMOSTRA_APROX / 1_000_000

    def amostras_treino(self, teto: int = TETO_AMOSTRAS_TREINO) -> tuple[list[list[float]], list[int]]:
        """Lê medidas+rótulo de todas as amostras rotuladas, paginando de 1000 em 1000, até `teto`.

        ÚNICA leitura de `medidas`. Chamar só por ação explícita (botão), nunca em rerun.
        """
        _validar_leitura("rotulo,medidas", 1, TETO_AMOSTRAS_TREINO)
        if teto > TETO_AMOSTRAS_TREINO:
            raise LeituraNaoPermitida(f"teto {teto} acima de {TETO_AMOSTRAS_TREINO}.")
        medidas, rotulos, inicio = [], [], 0
        while inicio < teto:
            fim = min(inicio + 1000, teto) - 1
            r = requests.get(self._url(TABELA_IMAGENS),
                             params={"select": "rotulo,medidas", "rotulo": "not.is.null", "order": "id"},
                             headers=self._headers(**{"Range-Unit": "items", "Range": f"{inicio}-{fim}"}),
                             timeout=60)
            self._checar(r, "Ler amostras de treino")
            lote = r.json()
            medidas += [linha["medidas"] for linha in lote]
            rotulos += [int(linha["rotulo"]) for linha in lote]
            if len(lote) < fim - inicio + 1:
                break
            inicio = fim + 1
        return medidas[:teto], rotulos[:teto]

    def inserir_amostras_importadas(self, linhas: list[dict]) -> None:
        """Importação em massa (script): linhas {medidas, rotulo, lote}. Sem nomes de arquivo."""
        for i in range(0, len(linhas), 500):
            bloco = [{**linha, "origem": "importacao"} for linha in linhas[i:i + 500]]
            r = requests.post(self._url(TABELA_IMAGENS), headers=self._headers(Prefer="return=minimal"),
                              json=bloco, timeout=60)
            self._checar(r, "Importar amostras")
