import streamlit as st
import requests
import hashlib
import json
import bcrypt
from datetime import datetime, timezone
from cryptography.fernet import Fernet

# Dado bruto mensal (base_ia_guias, base_imagem_procedimentos) mora no Turso,
# não no Supabase -- são as 2 maiores tabelas e não têm dado sensível (nunca
# tiveram nome de prestador/CPF/CNPJ, só guia/procedimento/operador). Listas
# abaixo são a ÚNICA porta de entrada pro Turso: qualquer campo fora dessas
# listas é rejeitado em vez de ignorado silenciosamente (ver
# _importar_por_mes_turso) -- trava contra um campo sensível entrar por
# engano numa edição futura.
TURSO_CAMPOS_BASE_IA = (
    "nu_ordem", "nu_guia", "cd_procedimento", "ds_grupo",
    "liberacao", "mes_referencia", "total_guias_processo", "cd_operador_atend",
)
TURSO_CAMPOS_BASE_IMAGEM = (
    "nu_guia", "cd_procedimento", "dente_inicial", "status_proced",
    "tem_imagem", "mes_referencia",
)


class DatabaseManager:
    def __init__(self):
        # Acessa os segredos do Streamlit
        self.supabase_url = st.secrets["supabase"]["url"]
        self.supabase_key = st.secrets["supabase"]["key"]
        # service_role: chave privilegiada usada apenas em operações admin
        # (ex: reset de senha). NUNCA deve sair do servidor.
        self._service_role = st.secrets["supabase"].get("service_role", "")

        # Inicializa a criptografia Fernet
        self.fernet = Fernet(st.secrets["seguranca"]["fernet_key"].encode('utf-8'))

        # Headers padrão para a API REST do Supabase (PostgREST)
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        # Turso: só as tabelas de dado bruto mensal (ver TURSO_CAMPOS_* acima).
        # URL vem como libsql://..., a API HTTP usa https://.
        turso_cfg = st.secrets.get("turso", {})
        self.turso_url = turso_cfg.get("url", "").replace("libsql://", "https://")
        self._turso_token_leitura = turso_cfg.get("token_leitura", "")
        self._turso_token_escrita = turso_cfg.get("token_escrita", "")

    def _admin_headers(self):
        """Headers com service_role para operações que exigem privilégio total.
        Nunca chamado a partir de código que possa ser acionado por usuário
        não-Admin — a checagem de role é feita antes por quem invoca."""
        if not self._service_role:
            raise RuntimeError("service_role não configurada em st.secrets['supabase']")
        return {
            "apikey": self._service_role,
            "Authorization": f"Bearer {self._service_role}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get(self, endpoint: str) -> list:
        url = f"{self.supabase_url}/rest/v1/{endpoint}"
        r = requests.get(url, headers=self.headers)
        return r.json() if r.ok else []

    # --- Turso (API HTTP /v2/pipeline) -- só base_ia_guias/base_imagem_procedimentos ---
    @staticmethod
    def _turso_arg(valor):
        """Converte um valor Python pro formato tipado que a API do Turso espera em `args`."""
        if valor is None:
            return {"type": "null"}
        if isinstance(valor, bool):
            return {"type": "integer", "value": "1" if valor else "0"}
        if isinstance(valor, int):
            return {"type": "integer", "value": str(valor)}
        if isinstance(valor, float):
            return {"type": "float", "value": valor}
        return {"type": "text", "value": str(valor)}

    @staticmethod
    def _turso_valor(celula: dict):
        """Converte uma célula tipada do resultado do Turso de volta pra Python."""
        tipo = celula.get("type")
        if tipo == "null":
            return None
        if tipo == "integer":
            return int(celula["value"])
        if tipo == "float":
            return float(celula["value"])
        return celula.get("value")

    def _turso_linhas(self, resultado: dict) -> list:
        """Converte {cols, rows} do Turso numa lista de dicts (mesmo formato
        que os métodos do Supabase já devolvem)."""
        colunas = [c["name"] for c in resultado.get("cols", [])]
        return [
            {col: self._turso_valor(cel) for col, cel in zip(colunas, linha)}
            for linha in resultado.get("rows", [])
        ]

    def _turso_pipeline(self, statements: list, token: str) -> list:
        """Executa uma lista de statements SQL ({"sql":..., "args":[...]})
        numa única requisição HTTP ao Turso. Retorna a lista de `result`,
        um por statement, na mesma ordem."""
        if not token:
            raise RuntimeError("Token do Turso não configurado em st.secrets['turso']")
        body = {"requests": [{"type": "execute", "stmt": s} for s in statements] + [{"type": "close"}]}
        resp = requests.post(
            f"{self.turso_url}/v2/pipeline",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"Falha no Turso: HTTP {resp.status_code} — {resp.text[:500]}")
        data = resp.json()
        resultados = []
        for item in data["results"][:-1]:  # último item é sempre o "close"
            if item["type"] == "error":
                raise RuntimeError(f"Falha no Turso (SQL): {item.get('error')}")
            resultados.append(item["response"]["result"])
        return resultados

    def _importar_por_mes_turso(
        self, tabela: str, registros: list, mes_referencia: str,
        campos_permitidos: tuple, manter_meses: int = 2, lote: int = 500,
        ao_progredir=None, retomar: bool = False,
    ) -> int:
        """Equivalente ao _importar_por_mes (Supabase), mas pro Turso: apaga
        o mês informado, insere os novos registros em lotes (multi-row
        INSERT) e mantém só `manter_meses` mais recentes. Só aceita campos
        em `campos_permitidos` -- ver comentário nas constantes TURSO_CAMPOS_*
        no topo do arquivo. `ao_progredir(enviados, total)`, se informado, é
        chamado a cada lote inserido -- pra UI mostrar barra de progresso.

        `retomar=True`: pula o DELETE e conta quantas linhas desse mês já
        existem na tabela, pulando essa quantidade no INÍCIO de `registros`
        antes de inserir o resto -- retoma um import que caiu no meio sem
        reenviar tudo de novo. Só é seguro se `registros` vier do MESMO
        arquivo/mesma ordem do import interrompido (a leitura do xlsx é
        sempre na mesma ordem, então reenviar o mesmo arquivo é seguro)."""
        permitidos = set(campos_permitidos)
        for reg in registros:
            extras = set(reg.keys()) - permitidos
            if extras:
                raise ValueError(
                    f"Campo(s) não permitido(s) pro Turso ({tabela}): {sorted(extras)}. "
                    f"Só {sorted(permitidos)} são aceitos."
                )

        token = self._turso_token_escrita

        def _apagar_em_lotes(mes: str, lote_delete: int = 20000):
            # Mesmo cuidado do Supabase: apaga em páginas em vez de um DELETE
            # só, pra nunca arriscar estourar timeout num mês com centenas de
            # milhares de linhas.
            while True:
                resultado = self._turso_pipeline([{
                    "sql": f"DELETE FROM {tabela} WHERE id IN "
                           f"(SELECT id FROM {tabela} WHERE mes_referencia = ? LIMIT ?)",
                    "args": [self._turso_arg(mes), self._turso_arg(lote_delete)],
                }], token)[0]
                if int(resultado.get("affected_row_count") or 0) == 0:
                    break

        total_registros = len(registros)
        ja_inseridas = 0
        if retomar:
            resultado_count = self._turso_pipeline([{
                "sql": f"SELECT COUNT(*) AS n FROM {tabela} WHERE mes_referencia = ?",
                "args": [self._turso_arg(mes_referencia)],
            }], token)[0]
            ja_inseridas = int(resultado_count["rows"][0][0]["value"])
        else:
            _apagar_em_lotes(mes_referencia)

        colunas = list(campos_permitidos)
        pendentes = registros[ja_inseridas:]
        total = ja_inseridas
        if ao_progredir and ja_inseridas:
            ao_progredir(total, total_registros)
        for i in range(0, len(pendentes), lote):
            pedaco = pendentes[i:i + lote]
            placeholder_linha = "(" + ",".join("?" * len(colunas)) + ")"
            sql = (
                f"INSERT INTO {tabela} ({','.join(colunas)}) VALUES "
                + ",".join([placeholder_linha] * len(pedaco))
            )
            args = [self._turso_arg(reg.get(col)) for reg in pedaco for col in colunas]
            self._turso_pipeline([{"sql": sql, "args": args}], token)
            total += len(pedaco)
            if ao_progredir:
                ao_progredir(total, total_registros)

        # Quais meses existem, pra decidir o que apagar: consulta a
        # _controle_meses (poucas linhas) em vez de "SELECT DISTINCT
        # mes_referencia FROM tabela", que varreria a tabela inteira
        # (centenas de milhares de linhas) só pra achar 1-2 valores --
        # desperdício de read/write no Turso.
        self._turso_pipeline([{
            "sql": "INSERT INTO _controle_meses (tabela, mes_referencia) VALUES (?, ?) "
                   "ON CONFLICT(tabela, mes_referencia) DO NOTHING",
            "args": [self._turso_arg(tabela), self._turso_arg(mes_referencia)],
        }], token)
        resultado_meses = self._turso_pipeline([{
            "sql": "SELECT mes_referencia FROM _controle_meses WHERE tabela = ?",
            "args": [self._turso_arg(tabela)],
        }], token)[0]
        meses = sorted({linha[0]["value"] for linha in resultado_meses.get("rows", [])}, reverse=True)
        for mes_antigo in meses[manter_meses:]:
            _apagar_em_lotes(mes_antigo)
            self._turso_pipeline([{
                "sql": "DELETE FROM _controle_meses WHERE tabela = ? AND mes_referencia = ?",
                "args": [self._turso_arg(tabela), self._turso_arg(mes_antigo)],
            }], token)

        return total

    def buscar_guias_vistas(self, nu_guias: list) -> set:
        """Guias (NU_GUIA) já marcadas como auditadas/vistas, dentre as informadas.

        Sem vínculo a usuário — é uma marcação compartilhada entre todos.
        """
        if not nu_guias:
            return set()
        filtro = ",".join(str(g) for g in nu_guias)
        url = f"{self.supabase_url}/rest/v1/amostragem_guias_vistas?nu_guia=in.({filtro})&select=nu_guia"
        r = requests.get(url, headers=self.headers)
        return {item["nu_guia"] for item in r.json()} if r.ok else set()

    # --- Base IA (Amostragem BETA): guias LIBERACAO=N importadas mensalmente ---
    # Tabela vive no Turso (dado bruto, sem informação sensível) -- ver
    # TURSO_CAMPOS_BASE_IA no topo do arquivo.
    def buscar_guias_ia_por_processo(self, nu_ordem: str) -> list:
        """Guias com LIBERACAO=N da base IA para um número de processo (NU_ORDEM)."""
        resultado = self._turso_pipeline([{
            "sql": "SELECT nu_guia, cd_procedimento, ds_grupo, total_guias_processo, cd_operador_atend "
                   "FROM base_ia_guias WHERE nu_ordem = ?",
            "args": [self._turso_arg(str(nu_ordem))],
        }], self._turso_token_leitura)[0]
        return self._turso_linhas(resultado)

    def listar_processos_agregado(self) -> list:
        """Um registro por NU_ORDEM (processo) do mês mais recente em
        base_ia_guias, com as especialidades e procedimentos distintos entre
        as guias sem liberação desse processo -- agregado em SQL (uma query
        só), não puxa as centenas de milhares de linhas cruas pro Python.

        Usado pela lista de processos do mês (Amostragem). Guia individual
        e contagens oficiais (total de guias, procedimentos) vêm de outro
        lugar -- aqui é só o que dá pra saber a partir da base IA: quais
        especialidades/procedimentos aparecem em cada processo, pra decidir
        se tem crítica."""
        resultado = self._turso_pipeline([{
            "sql": "SELECT nu_ordem, "
                   "GROUP_CONCAT(DISTINCT ds_grupo) AS especialidades, "
                   "GROUP_CONCAT(DISTINCT cd_procedimento) AS procedimentos "
                   "FROM base_ia_guias "
                   "WHERE mes_referencia = (SELECT MAX(mes_referencia) FROM base_ia_guias) "
                   "GROUP BY nu_ordem",
        }], self._turso_token_leitura)[0]
        return self._turso_linhas(resultado)

    def _importar_por_mes(
        self, tabela: str, registros: list, mes_referencia: str, lote: int = 2000, manter_meses: int = 2
    ) -> int:
        """Substitui os dados do `mes_referencia` informado numa tabela com
        coluna `mes_referencia` (reimportação idempotente) e mantém só os
        `manter_meses` mais recentes. Usado por importar_relatorio_5201 --
        base_ia_guias/base_imagem_procedimentos migraram pro Turso, ver
        _importar_por_mes_turso."""
        def _garantir_ok(response, contexto: str):
            if not response.ok:
                raise RuntimeError(
                    f"Falha no Supabase ({contexto}): HTTP {response.status_code} — "
                    f"{response.text[:500]}"
                )

        url = f"{self.supabase_url}/rest/v1/{tabela}"
        # A role anon tem statement_timeout de 3s — insuficiente pra apagar/inserir
        # centenas de milhares de linhas dessas tabelas mensais. Usa service_role
        # (sem override de timeout, cai no padrão do banco de 2min) só aqui, nas
        # operações de escrita em massa; leituras continuam com self.headers.
        headers_admin = self._admin_headers()
        headers_insert = {**headers_admin, "Prefer": "return=minimal"}

        def _apagar_em_lotes(filtro_query: str, contexto: str, lote_delete: int = 5000):
            # Um DELETE só cobrindo o mês inteiro estoura o statement_timeout
            # de 2min em tabelas grandes (ex: base_imagem_procedimentos, ~900k
            # linhas/mês). Pega o maior id de uma página ordenada e apaga tudo
            # até ali -- URL curta (não depende de listar todos os ids no
            # filtro) e cada lote rápido o bastante pra nunca chegar perto do
            # timeout.
            while True:
                r_pagina = requests.get(
                    f"{url}?{filtro_query}&select=id&order=id.asc&limit={lote_delete}",
                    headers=self.headers,
                )
                _garantir_ok(r_pagina, f"listar ids antigos para apagar ({contexto})")
                pagina = r_pagina.json()
                if not pagina:
                    break
                maior_id = pagina[-1]["id"]
                r_delete = requests.delete(
                    f"{url}?{filtro_query}&id=lte.{maior_id}", headers=headers_admin
                )
                _garantir_ok(r_delete, f"apagar lote antigo ({contexto})")

        _apagar_em_lotes(f"mes_referencia=eq.{mes_referencia}", f"mês {mes_referencia} em {tabela}")

        total = 0
        for i in range(0, len(registros), lote):
            pedaco = registros[i:i + lote]
            r_insert = requests.post(url, headers=headers_insert, json=pedaco)
            _garantir_ok(r_insert, f"inserir lote {i}-{i + len(pedaco)} do mês {mes_referencia} em {tabela}")
            total += len(pedaco)

        r_meses = requests.get(f"{url}?select=mes_referencia", headers=self.headers)
        if r_meses.ok:
            meses = sorted({item["mes_referencia"] for item in r_meses.json()}, reverse=True)
            antigos = meses[manter_meses:]
            if antigos:
                filtro = ",".join(antigos)
                _apagar_em_lotes(f"mes_referencia=in.({filtro})", f"meses antigos ({', '.join(antigos)}) em {tabela}")

        return total

    def importar_base_ia(
        self, registros: list, mes_referencia: str, lote: int = 500, ao_progredir=None, retomar: bool = False
    ) -> int:
        """Substitui os dados do `mes_referencia` informado no Turso
        (reimportação idempotente) e mantém só os 2 meses mais recentes.

        `registros`: lista de dicts com nu_ordem/nu_guia/cd_procedimento/
        ds_grupo/liberacao/mes_referencia já prontos para inserir.
        `ao_progredir(enviados, total)`: chamado a cada lote, opcional.
        `retomar`: retoma um import interrompido em vez de apagar e reinserir
        tudo -- ver docstring de _importar_por_mes_turso.
        """
        return self._importar_por_mes_turso(
            "base_ia_guias", registros, mes_referencia, TURSO_CAMPOS_BASE_IA,
            manter_meses=2, lote=lote, ao_progredir=ao_progredir, retomar=retomar,
        )

    def importar_base_imagem(
        self, registros: list, mes_referencia: str, lote: int = 500, ao_progredir=None, retomar: bool = False
    ) -> int:
        """Substitui os dados do `mes_referencia` informado no Turso
        (reimportação idempotente) e mantém só o mês mais recente -- essa é
        a maior tabela (era ~193MB, 91% do banco Supabase antes de migrar),
        então guarda só 1 mês em vez de 2 pra conter o espaço.

        `registros`: lista de dicts com nu_guia/cd_procedimento/dente_inicial/
        status_proced/tem_imagem/mes_referencia já prontos para inserir.
        `ao_progredir(enviados, total)`: chamado a cada lote, opcional.
        `retomar`: retoma um import interrompido em vez de apagar e reinserir
        tudo -- ver docstring de _importar_por_mes_turso.
        """
        # tem_imagem é bool em Python; Turso/SQLite guarda como INTEGER 0/1.
        registros = [{**r, "tem_imagem": 1 if r.get("tem_imagem") else 0} for r in registros]
        return self._importar_por_mes_turso(
            "base_imagem_procedimentos", registros, mes_referencia, TURSO_CAMPOS_BASE_IMAGEM,
            manter_meses=1, lote=lote, ao_progredir=ao_progredir, retomar=retomar,
        )

    def buscar_imagem_por_guias(self, nu_guias: list) -> list:
        """Registros de imagem (guia, procedimento, dente, status, tem_imagem)
        para as guias informadas."""
        if not nu_guias:
            return []
        placeholders = ",".join("?" * len(nu_guias))
        resultado = self._turso_pipeline([{
            "sql": "SELECT nu_guia, cd_procedimento, dente_inicial, status_proced, tem_imagem "
                   f"FROM base_imagem_procedimentos WHERE nu_guia IN ({placeholders})",
            "args": [self._turso_arg(str(g)) for g in nu_guias],
        }], self._turso_token_leitura)[0]
        linhas = self._turso_linhas(resultado)
        for linha in linhas:
            linha["tem_imagem"] = bool(linha["tem_imagem"])
        return linhas

    # --- Procedimentos ignorados na Amostragem (persistente, por especialidade) ---
    def carregar_procs_ignorados(self) -> dict:
        """Retorna {especialidade: set(codigos)} com tudo que já foi salvo
        como 'não precisa analisar' em qualquer sessão anterior."""
        url = f"{self.supabase_url}/rest/v1/amostragem_procs_ignorados?select=especialidade,cd_procedimento"
        r = requests.get(url, headers=self.headers)
        resultado = {}
        if r.ok:
            for item in r.json():
                resultado.setdefault(item["especialidade"], set()).add(item["cd_procedimento"])
        return resultado

    def salvar_procs_ignorados(self, pares: list) -> bool:
        """Insere pares (especialidade, cd_procedimento) como padrão a ignorar
        dali em diante. Pares já existentes são ignorados (idempotente)."""
        if not pares:
            return True
        url = f"{self.supabase_url}/rest/v1/amostragem_procs_ignorados?on_conflict=especialidade,cd_procedimento"
        headers_insert = {**self.headers, "Prefer": "resolution=ignore-duplicates,return=minimal"}
        data = [{"especialidade": esp, "cd_procedimento": cod} for esp, cod in pares]
        r = requests.post(url, headers=headers_insert, json=data)
        return r.ok

    # --- Histórico de glosas por prestador (risco/desvio na Amostragem) ---
    def salvar_historico_glosas(self, registros: list, lote: int = 500) -> int:
        """Insere ocorrências de glosa no histórico por prestador --
        idempotente via UNIQUE(guia, procedimento, glosa, subglosa):
        reprocessar o mesmo 5302/5310 não duplica, só ignora o que já
        existe (Prefer: resolution=ignore-duplicates, mesmo padrão de
        salvar_procs_ignorados).

        `registros`: lista de dicts com processo/prestador/mes_referencia/
        procedimento/glosa/subglosa/justificativa/guia/origem já prontos.
        Retorna quantos registros foram enviados (não necessariamente todos
        novos -- duplicatas são silenciosamente ignoradas pelo Postgres)."""
        if not registros:
            return 0
        url = (
            f"{self.supabase_url}/rest/v1/historico_glosas_prestador"
            "?on_conflict=guia,procedimento,glosa,subglosa"
        )
        headers_insert = {**self.headers, "Prefer": "resolution=ignore-duplicates,return=minimal"}
        total = 0
        for i in range(0, len(registros), lote):
            pedaco = registros[i:i + lote]
            r = requests.post(url, headers=headers_insert, json=pedaco)
            if not r.ok:
                raise RuntimeError(f"Falha ao salvar histórico de glosas: HTTP {r.status_code} — {r.text[:500]}")
            total += len(pedaco)
        return total

    def salvar_historico_procedimentos(self, registros: list, lote: int = 1000) -> int:
        """Guarda o QT_PROCEDIMENTO de cada processo por prestador -- é o
        denominador usado em obter_risco_prestador (glosas / total de
        procedimentos). Upsert por `processo` (merge-duplicates, não
        ignore): ao contrário da glosa, aqui queremos sempre o valor mais
        recente se o mesmo processo aparecer de novo num REL5201 futuro,
        não o primeiro visto. Chamado silenciosamente a cada importação do
        REL5201 (ver views/1_Configuracoes.py)."""
        if not registros:
            return 0
        url = (
            f"{self.supabase_url}/rest/v1/historico_procedimentos_prestador"
            "?on_conflict=processo"
        )
        headers_upsert = {**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
        total = 0
        for i in range(0, len(registros), lote):
            pedaco = registros[i:i + lote]
            r = requests.post(url, headers=headers_upsert, json=pedaco)
            if not r.ok:
                raise RuntimeError(f"Falha ao salvar histórico de procedimentos: HTTP {r.status_code} — {r.text[:500]}")
            total += len(pedaco)
        return total

    def obter_risco_prestador(self, prestador: str) -> dict:
        """Estatística de risco do prestador pro card da Amostragem (Fase 2):
        quantas glosas ele já teve no histórico, em quantos processos, e a
        média de glosas por processo -- métrica principal, porque "% dos
        procedimentos" dilui demais em prestadores de alto volume (ver
        discussão que levou a essa mudança). O %% continua disponível como
        dado secundário. Campos ficam None quando não há base de
        procedimentos pra calcular (prestador sem nenhum REL5201 importado
        ainda com essa captura)."""
        prestador = (prestador or "").strip()
        if not prestador:
            return {
                "total_glosas": 0, "total_procedimentos": 0, "total_processos": 0,
                "pct_glosa": None, "media_glosas_por_processo": None,
            }

        headers_count = {**self.headers, "Prefer": "count=exact"}

        url_glosas = f"{self.supabase_url}/rest/v1/historico_glosas_prestador"
        params_glosas = {"prestador": f"eq.{prestador}", "select": "id", "limit": "1"}
        r_glosas = requests.get(url_glosas, headers=headers_count, params=params_glosas)
        total_glosas = self._extrair_content_range(r_glosas)

        url_proc = f"{self.supabase_url}/rest/v1/historico_procedimentos_prestador"
        params_proc_count = {"prestador": f"eq.{prestador}", "select": "id", "limit": "1"}
        r_proc_count = requests.get(url_proc, headers=headers_count, params=params_proc_count)
        total_processos = self._extrair_content_range(r_proc_count)

        params_proc_soma = {"prestador": f"eq.{prestador}", "select": "qt_procedimento"}
        r_proc_soma = requests.get(url_proc, headers=self.headers, params=params_proc_soma)
        total_procedimentos = sum(row.get("qt_procedimento") or 0 for row in r_proc_soma.json()) if r_proc_soma.ok else 0

        pct_glosa = round(total_glosas / total_procedimentos * 100, 1) if total_procedimentos > 0 else None
        media_glosas_por_processo = round(total_glosas / total_processos, 1) if total_processos > 0 else None
        return {
            "total_glosas": total_glosas,
            "total_procedimentos": total_procedimentos,
            "total_processos": total_processos,
            "pct_glosa": pct_glosa,
            "media_glosas_por_processo": media_glosas_por_processo,
        }

    def _extrair_content_range(self, response) -> int:
        """Lê o total exato de um GET com `Prefer: count=exact` no header
        Content-Range (ex: '0-0/153') -- evita baixar as linhas só pra
        contar."""
        if not response.ok:
            return 0
        content_range = response.headers.get("Content-Range", "")
        if "/" not in content_range:
            return 0
        try:
            return int(content_range.split("/")[-1])
        except ValueError:
            return 0

    def obter_detalhe_glosas_prestador(self, prestador: str, limite: int = 8) -> dict:
        """Rankings das glosas mais frequentes desse prestador no histórico --
        por (código + justificativa) e por procedimento -- pro expander de
        detalhe no card da Amostragem. Uma única busca, duas agregações
        client-side (volume por prestador é pequeno o bastante pra isso ser
        mais simples que duas queries)."""
        prestador = (prestador or "").strip()
        if not prestador:
            return {"por_glosa": [], "por_procedimento": [], "por_mes": []}
        url = f"{self.supabase_url}/rest/v1/historico_glosas_prestador"
        params = {"prestador": f"eq.{prestador}", "select": "glosa,justificativa,procedimento,mes_referencia"}
        r = requests.get(url, headers=self.headers, params=params)
        if not r.ok:
            return {"por_glosa": [], "por_procedimento": [], "por_mes": []}

        linhas = r.json()

        contagem_glosa = {}
        contagem_procedimento = {}
        contagem_mes = {}
        for linha in linhas:
            chave_glosa = (linha.get("glosa") or "—", linha.get("justificativa") or "—")
            contagem_glosa[chave_glosa] = contagem_glosa.get(chave_glosa, 0) + 1
            cod_proc = linha.get("procedimento") or "—"
            contagem_procedimento[cod_proc] = contagem_procedimento.get(cod_proc, 0) + 1
            mes = linha.get("mes_referencia") or "—"
            contagem_mes[mes] = contagem_mes.get(mes, 0) + 1

        ranking_glosa = sorted(contagem_glosa.items(), key=lambda item: item[1], reverse=True)[:limite]
        ranking_procedimento = sorted(contagem_procedimento.items(), key=lambda item: item[1], reverse=True)[:limite]
        # Por mês é linha do tempo, não ranking -- ordena cronologicamente,
        # não por quantidade.
        serie_mes = sorted(contagem_mes.items(), key=lambda item: item[0])

        return {
            "por_glosa": [
                {"glosa": glosa, "justificativa": justificativa, "quantidade": qtd}
                for (glosa, justificativa), qtd in ranking_glosa
            ],
            "por_procedimento": [
                {"procedimento": cod, "quantidade": qtd} for cod, qtd in ranking_procedimento
            ],
            "por_mes": [{"mes_referencia": mes, "quantidade": qtd} for mes, qtd in serie_mes],
        }

    def remover_procs_ignorados(self, pares: list) -> bool:
        """Remove pares (especialidade, cd_procedimento) da lista salva —
        volta a considerar o procedimento na análise por padrão."""
        ok = True
        for esp, cod in pares:
            url = (
                f"{self.supabase_url}/rest/v1/amostragem_procs_ignorados"
                f"?especialidade=eq.{esp}&cd_procedimento=eq.{cod}"
            )
            r = requests.delete(url, headers=self.headers)
            ok = ok and r.ok
        return ok

    def carregar_dicionario_glosas(self) -> dict:
        """Carrega o dicionário de correção de textos de glosas do Supabase"""
        url = f"{self.supabase_url}/rest/v1/glosas_dicionario?select=texto_original,texto_corrigido"
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            return {item["texto_original"].lower().strip(): item["texto_corrigido"] for item in r.json()}
        return {}

    # --- Segurança e Hashing ---
    def criptografar(self, texto: str) -> str:
        if not texto: return ""
        return self.fernet.encrypt(texto.encode('utf-8')).decode('utf-8')

    def descriptografar(self, texto_cifrado: str) -> str:
        if not texto_cifrado: return ""
        try:
            return self.fernet.decrypt(texto_cifrado.encode('utf-8')).decode('utf-8')
        except Exception:
            return "[ERRO: DADO CORROMPIDO OU CHAVE INVÁLIDA]"
            
    _SHA256_SALT_LEGADO = "SIA_SALT_V5_A7B2!"

    def _hash_sha256_legado(self, senha: str) -> str:
        """Hash antigo (sha256 + salt estatico). Mantido APENAS para validar
        senhas de usuarios que ainda nao foram remigrados. Nao usar para novos
        cadastros nem para escrever no banco."""
        return hashlib.sha256((senha + self._SHA256_SALT_LEGADO).encode('utf-8')).hexdigest()

    def _hash_senha(self, senha: str) -> str:
        """Gera hash bcrypt para uso atual (novos cadastros / reset / troca)."""
        return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verificar_senha(self, senha_plain: str, senha_hash: str, algo: str) -> bool:
        """Valida senha respeitando o algoritmo com que ela foi gravada."""
        if algo == "bcrypt":
            try:
                return bcrypt.checkpw(senha_plain.encode('utf-8'), senha_hash.encode('utf-8'))
            except Exception:
                return False
        # Fallback: sha256 legado
        return self._hash_sha256_legado(senha_plain) == senha_hash

    # --- Autenticação e Usuários (SISTEMA DE LOGIN SIGO) ---
    def criar_usuario(self, usuario_sigo, nome_completo, senha, equipe):
        url = f"{self.supabase_url}/rest/v1/usuarios"
        
        # Define o role_interno inicial baseado na equipe, mas tudo nasce 'Pendente'.
        # "Admin" não é uma opção de auto-cadastro: só um Admin existente pode
        # promover alguém na aba "Aprovação de Equipe".
        role_map = {
            "Contas": "Contas",
            "Auditoria": "Auditor",
            "CISO": "CISO",
            "Gestor": "Gestor",
        }
        
        data = {
            "usuario_sigo": usuario_sigo,
            "nome_completo": nome_completo,
            "senha_hash": self._hash_senha(senha),
            "senha_algo": "bcrypt",
            "equipe": equipe,
            "role_interno": role_map.get(equipe, "Contas"),
            "status": "Pendente"
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code not in [200, 201]:
            return False

        try:
            novo_id = response.json()[0]["id"]
            self.marcar_todos_alinhamentos_lidos(novo_id)
        except (IndexError, KeyError):
            pass
        return True

    def marcar_todos_alinhamentos_lidos(self, usuario_id):
        """Marca todo o histórico de alinhamentos existente como lido (e toda
        inativação existente como ciente) para um usuário recém-criado, para
        que só alinhamentos publicados ou inativados após este momento gerem
        popup obrigatório — o histórico já é conhecimento geral da equipe."""
        existentes = self.carregar_alinhamentos()
        if not existentes:
            return True

        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = [{"alinhamento_id": a["id"], "usuario_id": usuario_id} for a in existentes]
        response = requests.post(url, headers=headers_upsert, json=data)
        ok = response.status_code in [200, 201]

        inativos_com_motivo = [a for a in existentes if not a.get("ativo", True) and a.get("justificativa_inativacao")]
        if inativos_com_motivo:
            url_inat = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas"
            data_inat = [{"alinhamento_id": a["id"], "usuario_id": usuario_id} for a in inativos_com_motivo]
            response_inat = requests.post(url_inat, headers=headers_upsert, json=data_inat)
            ok = ok and response_inat.status_code in [200, 201]

        return ok

    def autenticar_usuario(self, usuario_sigo, senha):
        url = f"{self.supabase_url}/rest/v1/usuarios?usuario_sigo=eq.{usuario_sigo}&select=*"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return None
        usuarios = response.json()
        if not usuarios:
            return None
        user = usuarios[0]

        algo = user.get("senha_algo") or "sha256_v5"
        if not self._verificar_senha(senha, user["senha_hash"], algo):
            return None

        # Rehash-on-login: se a senha do usuario ainda esta com o hash antigo,
        # regravamos com bcrypt agora (transparente). A senha em texto claro so
        # existe aqui neste request, ja validada.
        if algo != "bcrypt":
            try:
                novo_hash = self._hash_senha(senha)
                patch_url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{user['id']}"
                requests.patch(
                    patch_url,
                    headers=self.headers,
                    json={"senha_hash": novo_hash, "senha_algo": "bcrypt"},
                )
                user["senha_hash"] = novo_hash
                user["senha_algo"] = "bcrypt"
            except Exception:
                # Se o rehash falhar, o login prossegue normalmente com o hash
                # antigo — apenas nao migramos desta vez.
                pass

        return user

    def listar_usuarios(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def atualizar_usuario_admin(self, usuario_id, status, role_interno, equipe):
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        data = {
            "status": status,
            "role_interno": role_interno,
            "equipe": equipe
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def excluir_usuario(self, usuario_id, atuante_role):
        if str(atuante_role) != "Admin":
            return False
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        response = requests.delete(url, headers=self._admin_headers())
        return response.status_code in [200, 204]

    def resetar_senha(self, usuario_alvo_id, nova_senha_temp, atuante_role):
        """Reseta a senha de OUTRO usuário. Só permitido para Admin.
        Grava a flag `senha_temporaria = true` para forçar troca no proximo login.
        Usa service_role para escrever ignorando RLS."""
        if str(atuante_role) != "Admin":
            return False
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_alvo_id}"
        data = {
            "senha_hash": self._hash_senha(nova_senha_temp),
            "senha_algo": "bcrypt",
            "senha_temporaria": True,
        }
        response = requests.patch(url, headers=self._admin_headers(), json=data)
        return response.status_code in [200, 204]

    # --- Links Padrão (institucionais, exibidos na Home) ---
    _ROLES_QUE_GERENCIAM_LINKS = {"Admin", "Gestor"}
    # Gestor e Admin sempre veem todos os links, independente de
    # niveis_visiveis — mesma convenção de "acesso total" já usada em
    # core/settings.py::tem_acesso_modulo para o Admin.
    _ROLES_QUE_VEEM_TUDO = {"Admin", "Gestor"}

    def listar_links_padrao(self, incluir_inativos: bool = False, role: str = None):
        base = f"{self.supabase_url}/rest/v1/links_padrao?select=*&order=categoria.asc,ordem.asc"
        if not incluir_inativos:
            base += "&ativo=eq.true"
        if role and role not in self._ROLES_QUE_VEEM_TUDO:
            base += f"&niveis_visiveis=cs.{{{role}}}"
        r = requests.get(base, headers=self.headers)
        return r.json() if r.status_code == 200 else []

    def inserir_link_padrao(self, titulo, url, categoria, ordem, atuante_role, niveis_visiveis=None):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao"
        data = {
            "titulo": titulo,
            "url": url,
            "categoria": categoria or "Geral",
            "ordem": int(ordem or 100),
            "niveis_visiveis": niveis_visiveis or ["Contas", "Auditor", "CISO"],
        }
        r = requests.post(endpoint, headers=self._admin_headers(), json=data)
        return r.status_code in (200, 201)

    def atualizar_link_padrao(self, link_id, titulo, url, categoria, ordem, ativo, atuante_role, niveis_visiveis=None):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao?id=eq.{link_id}"
        data = {
            "titulo": titulo,
            "url": url,
            "categoria": categoria or "Geral",
            "ordem": int(ordem or 100),
            "ativo": bool(ativo),
            "niveis_visiveis": niveis_visiveis or ["Contas", "Auditor", "CISO"],
        }
        r = requests.patch(endpoint, headers=self._admin_headers(), json=data)
        return r.status_code in (200, 204)

    def deletar_link_padrao(self, link_id, atuante_role):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao?id=eq.{link_id}"
        r = requests.delete(endpoint, headers=self._admin_headers())
        return r.status_code in (200, 204)

    def trocar_senha_propria(self, usuario_id, nova_senha):
        """Usuário troca a própria senha. Zera a flag `senha_temporaria`."""
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        data = {
            "senha_hash": self._hash_senha(nova_senha),
            "senha_algo": "bcrypt",
            "senha_temporaria": False,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Tabela Procedimentos) ---
    def inserir_procedimento(self, codigo_tuss, descricao, valor_unitario):
        url = f"{self.supabase_url}/rest/v1/tabela_procedimentos"
        data = {
            "codigo_tuss": codigo_tuss,
            "descricao": descricao,
            "valor_unitario": valor_unitario
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    # --- Operações de Banco (Textos dos Prestadores) ---
    def carregar_textos_prestador(self):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def inserir_texto_prestador(self, titulo, glosas_relacionadas, texto, updated_by, sub_glosas_relacionadas="", procedimentos_relacionados=""):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by,
            "sub_glosas_relacionadas": sub_glosas_relacionadas,
            "procedimentos_relacionados": procedimentos_relacionados
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    def atualizar_texto_prestador(self, msg_id, titulo, glosas_relacionadas, texto, updated_by, sub_glosas_relacionadas="", procedimentos_relacionados=""):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?id=eq.{msg_id}"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by,
            "sub_glosas_relacionadas": sub_glosas_relacionadas,
            "procedimentos_relacionados": procedimentos_relacionados
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def deletar_texto_prestador(self, msg_id):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?id=eq.{msg_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Glosas Customizadas / Overrides) ---
    def carregar_glosas_customizadas(self):
        url = f"{self.supabase_url}/rest/v1/glosas_customizadas?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def upsert_glosa_customizada(self, codigo_glosa, descricao, is_critica, tipo, updated_by):
        url = f"{self.supabase_url}/rest/v1/glosas_customizadas"
        
        # O cabeçalho 'Prefer': 'resolution=merge-duplicates' faz o POST agir como UPSERT no Supabase se houver PK conflict
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        
        data = {
            "codigo_glosa": str(codigo_glosa).strip(),
            "descricao": descricao,
            "is_critica": is_critica,
            "tipo": tipo,
            "updated_by": updated_by
        }
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    # --- Operações de Banco (Usuários / Logins Autorizados) ---
    def carregar_logins_validos(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?select=usuario_sigo"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [str(u.get('usuario_sigo', '')).strip().upper() for u in response.json() if u.get('usuario_sigo')]
        return []

    # --- Operações de Banco (Links Úteis Relacionais) ---
    def inserir_link_util(self, usuario_id, titulo, url):
        # 1. Upsert na tabela links para garantir que a URL exista de forma única
        url_links = f"{self.supabase_url}/rest/v1/links"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "return=representation, resolution=merge-duplicates"
        data_link = {"url": url}
        
        r_link = requests.post(url_links, headers=headers_upsert, json=data_link)
        if r_link.status_code not in [200, 201]:
            return False
            
        try:
            link_id = r_link.json()[0]["id"]
        except (IndexError, KeyError):
            return False
            
        # 2. Inserir a relação na tabela usuario_links
        url_usr = f"{self.supabase_url}/rest/v1/usuario_links"
        data_usr = {
            "usuario_id": usuario_id,
            "link_id": link_id,
            "titulo": titulo
        }
        # Ignora se já existir essa relação exata
        headers_usr = self.headers.copy()
        headers_usr["Prefer"] = "resolution=ignore-duplicates"
        r_usr = requests.post(url_usr, headers=headers_usr, json=data_usr)
        return r_usr.status_code in [200, 201]

    def atualizar_titulo_link_util(self, id_relacao, novo_titulo):
        url = f"{self.supabase_url}/rest/v1/usuario_links?id=eq.{id_relacao}"
        data = {"titulo": novo_titulo}
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def carregar_meus_links(self, usuario_id):
        # O PostgREST suporta Joins através de foreign keys:
        url = f"{self.supabase_url}/rest/v1/usuario_links?usuario_id=eq.{usuario_id}&select=id,titulo,link_id,links(url)"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            dados = response.json()
            resultados = []
            for d in dados:
                url_real = d.get('links', {}).get('url', '') if d.get('links') else ''
                resultados.append({
                    "id": d["id"],
                    "titulo": d["titulo"],
                    "url": url_real
                })
            return resultados
        return []

    def deletar_link_util(self, id_relacao):
        url = f"{self.supabase_url}/rest/v1/usuario_links?id=eq.{id_relacao}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Alinhamentos Internos) ---
    def carregar_alinhamentos(self, incluir_excluidos=False):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?select=*&order=created_at.desc"
        if not incluir_excluidos:
            url += "&excluido=eq.false"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_alinhamentos_excluidos(self):
        """Lista alinhamentos excluídos (soft-delete), mais recentes primeiro.
        Visível apenas na área "Excluídos" da tela de Alinhamentos (Gestor/Admin)."""
        url = f"{self.supabase_url}/rest/v1/alinhamentos?select=*&excluido=eq.true&order=excluido_em.desc"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def excluir_alinhamento_com_motivo(self, alinhamento_id, motivo, usuario_id):
        """Exclusão suave: marca como excluído com motivo obrigatório, autor e
        timestamp, mas mantém o registro (e o histórico de ciência associado)
        no banco para fins de auditoria."""
        if not str(motivo or "").strip():
            return False
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "excluido": True,
            "motivo_exclusao": motivo.strip(),
            "excluido_em": datetime.now(timezone.utc).isoformat(),
            "excluido_por": usuario_id,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in (200, 204)

    def restaurar_alinhamento(self, alinhamento_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "excluido": False,
            "motivo_exclusao": None,
            "excluido_em": None,
            "excluido_por": None,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in (200, 204)

    def carregar_alinhamentos_visiveis(self, role):
        from core.settings import NIVEL_HIERARQUIA
        nivel_usuario = NIVEL_HIERARQUIA.get(role, 1)
        niveis_visiveis = [n for n, v in NIVEL_HIERARQUIA.items() if v <= nivel_usuario]
        niveis_filtro = ",".join(niveis_visiveis)
        url = (
            f"{self.supabase_url}/rest/v1/alinhamentos"
            f"?nivel_minimo=in.({niveis_filtro})&excluido=eq.false&select=*&order=created_at.desc"
        )
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_alinhamentos_pendentes(self, usuario_id, role):
        from core.settings import NIVEL_HIERARQUIA, ROLES_CIENCIA_OBRIGATORIA
        if role not in ROLES_CIENCIA_OBRIGATORIA:
            return []

        nivel_usuario = NIVEL_HIERARQUIA.get(role, 1)
        niveis_visiveis = [n for n, v in NIVEL_HIERARQUIA.items() if v <= nivel_usuario]
        niveis_filtro = ",".join(niveis_visiveis)

        url = (
            f"{self.supabase_url}/rest/v1/alinhamentos"
            f"?nivel_minimo=in.({niveis_filtro})&excluido=eq.false&select=*&order=created_at.asc"
        )
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            return []
        todos_visiveis = response.json()
        if not todos_visiveis:
            return []

        url_lidos = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?usuario_id=eq.{usuario_id}&select=alinhamento_id"
        response_lidos = requests.get(url_lidos, headers=self.headers)
        lidos_ids = {item["alinhamento_id"] for item in response_lidos.json()} if response_lidos.status_code == 200 else set()

        url_inativacoes = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?usuario_id=eq.{usuario_id}&select=alinhamento_id"
        response_inat = requests.get(url_inativacoes, headers=self.headers)
        inativacoes_lidas_ids = {item["alinhamento_id"] for item in response_inat.json()} if response_inat.status_code == 200 else set()

        pendentes = []
        for a in todos_visiveis:
            if a.get("ativo", True):
                if a["id"] not in lidos_ids:
                    pendentes.append(a)
            else:
                if a.get("justificativa_inativacao") and a["id"] not in inativacoes_lidas_ids:
                    pendentes.append(a)

        return pendentes

    def inserir_alinhamento(self, titulo, conteudo, categoria, nivel_minimo, autor_id, anexo_url=""):
        url = f"{self.supabase_url}/rest/v1/alinhamentos"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
            "autor_id": autor_id,
            "anexo_url": anexo_url.strip() if anexo_url else None,
        }
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code not in [200, 201]:
            return False

        try:
            novo_id = response.json()[0]["id"]
            self.marcar_alinhamento_lido(novo_id, autor_id)
        except (IndexError, KeyError):
            pass
        return True

    def atualizar_alinhamento(self, alinhamento_id, titulo, conteudo, categoria, nivel_minimo, created_at=None, anexo_url=""):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
            "anexo_url": anexo_url.strip() if anexo_url else None,
        }
        if created_at:
            data["created_at"] = created_at
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def toggle_ativo_alinhamento(self, alinhamento_id, ativo, justificativa=None):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {"ativo": ativo}
        if not ativo:
            data["justificativa_inativacao"] = justificativa
        else:
            data["justificativa_inativacao"] = None
            
        response = requests.patch(url, headers=self.headers, json=data)
        if response.status_code in [200, 204]:
            if ativo:
                requests.delete(f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?alinhamento_id=eq.{alinhamento_id}", headers=self.headers)
            return True
        return False

    # --- Operações de Banco (Permissões de Módulos por Role) ---
    def carregar_permissoes_modulos(self):
        # permissoes_modulos tem RLS habilitado sem nenhuma policy — só
        # service_role (que ignora RLS) consegue ler. Isso é intencional
        # (ver commit "uso de service_role para RLS"); não trocar para
        # self.headers, a chave anon simplesmente não teria acesso.
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?select=*"
        response = requests.get(url, headers=self._admin_headers())
        if response.status_code == 200:
            return response.json()
        return []

    def atualizar_permissao_modulo(self, modulo, role, habilitado):
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?on_conflict=modulo,role"
        headers_upsert = self._admin_headers()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        data = {"modulo": modulo, "role": role, "habilitado": habilitado}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    # --- Operações de Banco (Exceções de Acesso por Usuário) ---
    def carregar_excecoes_modulos(self):
        # Mesmo padrão de permissoes_modulos: RLS habilitado sem policy,
        # só service_role consegue ler.
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos_excecoes?select=*"
        response = requests.get(url, headers=self._admin_headers())
        if response.status_code == 200:
            return response.json()
        return []

    def atualizar_excecao_modulo(self, usuario_id, modulo, habilitado):
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos_excecoes?on_conflict=usuario_id,modulo"
        headers_upsert = self._admin_headers()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        data = {"usuario_id": usuario_id, "modulo": modulo, "habilitado": habilitado}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def remover_excecao_modulo(self, usuario_id, modulo):
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos_excecoes?usuario_id=eq.{usuario_id}&modulo=eq.{modulo}"
        response = requests.delete(url, headers=self._admin_headers())
        return response.status_code in [200, 204]

    def marcar_alinhamento_lido(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?on_conflict=alinhamento_id,usuario_id"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = {"alinhamento_id": alinhamento_id, "usuario_id": usuario_id}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def marcar_inativacao_lida(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?on_conflict=alinhamento_id,usuario_id"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = {"alinhamento_id": alinhamento_id, "usuario_id": usuario_id}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def carregar_usuarios_ativos(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?status=eq.Ativo&select=id,nome_completo,role_interno"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_todas_leituras(self):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?select=alinhamento_id,usuario_id,lido_em"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def remover_leitura_alinhamento(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?alinhamento_id=eq.{alinhamento_id}&usuario_id=eq.{usuario_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    def excluir_alinhamento(self, alinhamento_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Relatório 5201 - Status e Produtividade) ---
    # Cada linha do relatório vira UM registro com o conteúdo inteiro
    # (ORDEM/STATUS/auditor/datas) cifrado num único blob JSON (Fernet) —
    # ninguém com acesso direto ao Supabase (dashboard, chave anon vazada)
    # consegue ler o conteúdo; só o app, que tem a chave em st.secrets.
    def importar_relatorio_5201(self, registros: list, importado_por, mes_referencia: str, lote: int = 1000) -> int:
        """Substitui os dados do `mes_referencia` informado (reimportação
        idempotente) e mantém só os 2 meses mais recentes na tabela — mesmo
        padrão de importar_base_ia/importar_base_imagem (_importar_por_mes).
        Assim, subir o REL5201 de um mês não sobrescreve outro mês já
        importado, e o 3º mês mais antigo é descartado automaticamente."""
        linhas = [
            {
                "payload_cifrado": self.criptografar(json.dumps(reg, ensure_ascii=False)),
                "importado_por": importado_por,
                "mes_referencia": mes_referencia,
                # Plano (não cifrado) só pra permitir busca direta por processo
                # sem precisar decifrar a tabela inteira (ver
                # buscar_status_processo) — número de processo não é dado
                # sensível de paciente, mesma categoria de NU_GUIA.
                "ordem": reg.get("ORDEM"),
            }
            for reg in registros
        ]
        return self._importar_por_mes("relatorio_5201_processos", linhas, mes_referencia, lote)

    def buscar_status_processo(self, nu_ordem: str) -> dict | None:
        """Busca e decifra só o registro do processo informado, nos 2 meses
        mantidos na tabela — evita ler e decifrar todo o snapshot (milhares
        de linhas) só pra checar o status de UM processo."""
        ordem = str(nu_ordem).strip()
        url = f"{self.supabase_url}/rest/v1/relatorio_5201_processos"
        params = {
            "ordem": f"eq.{ordem}",
            "select": "payload_cifrado,mes_referencia",
            "order": "mes_referencia.desc",
            "limit": "1",
        }
        response = requests.get(url, headers=self.headers, params=params)
        if not response.ok:
            return None
        linhas = response.json()
        if not linhas:
            return None
        try:
            registro = json.loads(self.descriptografar(linhas[0]["payload_cifrado"]))
        except (ValueError, TypeError):
            return None
        registro["_mes_referencia"] = linhas[0].get("mes_referencia")
        return registro

    def carregar_relatorio_5201(self) -> list:
        """Busca e decifra o snapshot atual do REL5201. Cada item retornado
        é o dict original (ORDEM, STATUS, LOGIN_FECHAMENTO etc.) gravado no
        último upload."""
        url = f"{self.supabase_url}/rest/v1/relatorio_5201_processos?select=payload_cifrado,importado_em,importado_por,mes_referencia"

        # PostgREST devolve no máximo 1000 linhas por padrão (db-max-rows) —
        # sem paginar por Range, um relatório com mais de 1000 processos vinha
        # cortado (o snapshot completo era gravado certo, só a leitura que
        # ficava incompleta). Pagina até a última página vir menor que o
        # tamanho pedido.
        tamanho_pagina = 1000
        offset = 0
        linhas = []
        while True:
            headers_paginado = {**self.headers, "Range-Unit": "items", "Range": f"{offset}-{offset + tamanho_pagina - 1}"}
            r = requests.get(url, headers=headers_paginado)
            if not r.ok:
                break
            pagina = r.json()
            linhas.extend(pagina)
            if len(pagina) < tamanho_pagina:
                break
            offset += tamanho_pagina

        registros = []
        for item in linhas:
            texto = self.descriptografar(item["payload_cifrado"])
            try:
                registro = json.loads(texto)
            except (ValueError, TypeError):
                continue
            registro["_importado_em"] = item.get("importado_em")
            registro["_importado_por"] = item.get("importado_por")
            registro["_mes_referencia"] = item.get("mes_referencia")
            registros.append(registro)
        return registros
