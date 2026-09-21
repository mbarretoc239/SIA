"""Pipeline do FAROL Mensal no SIA -- portado de farol/processamento.py (pasta
"farol mensal" no Desktop do usuário), que é a FONTE DE VERDADE das regras.

Fidelidade ao original (não "melhorar" sem o usuário pedir):
- _tem_caractere_invalido / _padrao_com_curinga / _resolver_nomes_corrompidos,
  a preparação das ocorrências (descarta linha sem prestador, junta texto
  partido na ORDEM ORIGINAL, classifica por Nu. Ordem, agrega por prestador
  N > PAR > REVISAR > S) e o cruzamento (correção de nome, merge por nome,
  SEM_OCORRENCIA, abas de saída) têm o mesmo corpo do original.
- O que muda é só a ENTRADA (arquivo enviado ou DataFrame, em vez de caminho)
  e o que está listado abaixo -- todo o resto do comportamento é idêntico, e
  tests/test_farol_mensal_paridade.py compara os dois lado a lado.

Acrescentado na integração (pedidos explícitos do usuário):
1. Frase "sem ocorrências para o período auditado/solicitado" -> S (dentro do
   classificador, ver classificacao.py).
2. Opção `incluir_compulsorio_no_sim` (padrão False = comportamento original).
3. Regra dos 100%: processo com a coluna LIBERADO_100_IA verdadeira vai pro S
   por cima do balde do prestador (inclusive SEM_OCORRENCIA), menos PAR. Quem
   calcula a coluna é core/farol_mensal.py (contagem exata, nunca % arredondado).
4. Coluna OBS na saída (glosas do REL5310 + marcas das regras acima).
"""

import io
import re
from dataclasses import dataclass

import pandas as pd

from .classificacao import (
    classificar_texto,
    eh_modelo_fechamento_compulsorio,
    prioridade,
    tem_fechamento_compulsorio,
)
from .erros import ColunasFaltandoError

COL_PRESTADOR_OCORRENCIAS = 'Nome Prestador'
COL_PROCESSO_OCORRENCIAS = 'Nu. Ordem'
COL_TEXTO_OCORRENCIA = 'Desc. Ocorrencia'
COL_DATA_PRODUCAO_OCORRENCIAS = 'Dt. Producao'
COLUNAS_OCORRENCIAS = [COL_PRESTADOR_OCORRENCIAS, COL_PROCESSO_OCORRENCIAS, COL_TEXTO_OCORRENCIA]

COL_PRESTADOR_PRODUCAO = 'PRESTADOR'
COL_PROCESSO_PRODUCAO = 'ORDEM'
COL_QTDE_PROCEDIMENTOS_PRODUCAO = 'QT_PROCEDIMENTO'
COL_OBS = 'OBS'
COL_LIBERADO_100 = 'LIBERADO_100_IA'

ABAS_SAIDA = [
    ("S", "S - Vai pro Farol"),
    ("N", "N - Checagem"),
    ("PAR", "PAR"),
    ("REVISAR", "Revisar"),
    ("SEM_OCORRENCIA", "Ocorrencia nao encontrada"),
    ("SEM_DADO_PROCEDIMENTO", "Sem dado de procedimento"),
]

COLUNAS_SAIDA = [COL_PROCESSO_PRODUCAO, COL_PRESTADOR_PRODUCAO, COL_QTDE_PROCEDIMENTOS_PRODUCAO,
                 "CLASSIFICACAO", "OCORRENCIA", COL_OBS]

NOTA_LIBERADO_100 = "100% liberado pela IA (automático)"
NOTA_COMPULSORIO_SIM = "Fechamento compulsório incluído no SIM (opção marcada)"


@dataclass
class ResultadoFarol:
    planilhas: dict          # {"S - Vai pro Farol": DataFrame, ...}
    total_processos: int
    contagem: dict           # {"S": 1277, "N": 2513, ...}
    sem_ocorrencia: int
    percentual_sem_ocorrencia: float
    nomes_suspeitos: list = None    # [{"ORDEM": ..., "PRESTADOR": ...}, ...] -- ainda sem match, não resolvido
    nomes_corrigidos: list = None   # [{"PRESTADOR": ..., "NOME_ENCONTRADO": ...}, ...] -- resolvido automaticamente
    procedimentos: dict = None      # {"S": soma de QT_PROCEDIMENTO do balde, ...}
    automaticos_100: int = 0        # quantos foram pro S pela regra dos 100%


@dataclass
class InfoOcorrencias:
    """O que o arquivo de ocorrências revelou, pra tela mostrar/alertar."""
    mes_producao: str = None            # "YYYY-MM" lido de Dt. Producao (None se a coluna não existir)
    total_processos: int = 0            # Nu. Ordem distintos depois de juntar texto partido
    fechamentos_compulsorios: int = 0
    compulsorios_no_sim: int = 0        # texto = modelo padrão, virou S (só com a opção marcada)
    compulsorios_fora_do_padrao: int = 0  # compulsório com texto fora da lista, segue N (só com a opção marcada)


def _tem_caractere_invalido(nome):
    """Detecta caractere de Área de Uso Privado do Unicode (U+E000-U+F8FF) no
    nome -- sintoma de corrupção de exportação (ex: 'Ç' virando um código de
    fonte que não existe do outro lado, então nunca vai casar por nome)."""
    return any(0xE000 <= ord(c) <= 0xF8FF for c in str(nome))


def _padrao_com_curinga(chave):
    """Constrói um regex a partir de uma chave corrompida: cada sequência de
    caractere de área privada vira um curinga (1 a 4 caracteres quaisquer); o
    resto do nome precisa bater exatamente. O contexto ao redor do curinga
    normalmente já é bem específico (nome de empresa inteiro), então isso é
    bem mais seguro que fuzzy matching genérico."""
    partes = ['^']
    i = 0
    while i < len(chave):
        c = chave[i]
        if 0xE000 <= ord(c) <= 0xF8FF:
            while i < len(chave) and 0xE000 <= ord(chave[i]) <= 0xF8FF:
                i += 1
            partes.append('.{1,4}')
        else:
            partes.append(re.escape(c))
            i += 1
    partes.append('$')
    return ''.join(partes)


def _resolver_nomes_corrompidos(chaves_producao, chaves_ocorrencias):
    """Pra cada chave de prestador da produção com caractere corrompido, tenta
    achar o nome certo entre as chaves de ocorrências casando o regex com
    curinga. Só resolve quando existe EXATAMENTE um candidato -- nome ambíguo
    (zero ou mais de um candidato) fica de fora do mapa e continua sinalizado
    em vez de adivinhado."""
    candidatas = set(chaves_ocorrencias)
    mapa = {}
    for chave in {c for c in chaves_producao if _tem_caractere_invalido(c)}:
        padrao = re.compile(_padrao_com_curinga(chave))
        achados = {c for c in candidatas if padrao.match(c)}
        if len(achados) == 1:
            mapa[chave] = next(iter(achados))
    return mapa


def _validar_colunas(df, colunas_esperadas, nome_planilha):
    faltando = [c for c in colunas_esperadas if c not in df.columns]
    if faltando:
        raise ColunasFaltandoError(
            f"A planilha de {nome_planilha} não tem a(s) coluna(s) esperada(s): "
            f"{', '.join(faltando)}.\n\nColunas encontradas: {', '.join(map(str, df.columns))}"
        )


# --- Leitura do arquivo de ocorrências (5307): upload, sem gravar em banco ---

def _bytes_da_fonte(fonte):
    """Aceita caminho, bytes ou objeto de arquivo (ex: UploadedFile do
    Streamlit) e devolve os bytes -- cada leitura abre um BytesIO novo, então
    não depende da posição do cursor do arquivo enviado."""
    if isinstance(fonte, (bytes, bytearray)):
        return bytes(fonte)
    if hasattr(fonte, "getvalue"):
        return fonte.getvalue()
    if hasattr(fonte, "read"):
        if hasattr(fonte, "seek"):
            fonte.seek(0)
        return fonte.read()
    with open(fonte, "rb") as arquivo:
        return arquivo.read()


def _e_csv(fonte):
    if isinstance(fonte, (bytes, bytearray)):
        return False
    nome = getattr(fonte, "name", fonte)
    return str(nome).lower().endswith(".csv")


def listar_abas(fonte):
    """Todas as abas do .xlsx ([] pra .csv, que não tem abas)."""
    if _e_csv(fonte):
        return []
    return pd.ExcelFile(io.BytesIO(_bytes_da_fonte(fonte))).sheet_names


def abas_de_ocorrencias(fonte):
    """Abas do .xlsx que têm as 3 colunas de ocorrência (o nome da aba varia
    entre meses: '5307', 'Planilha2'...; uma aba de cabeçalho de relatório,
    sem essas colunas, é ignorada)."""
    if _e_csv(fonte):
        return []
    planilha = pd.ExcelFile(io.BytesIO(_bytes_da_fonte(fonte)))
    return [
        aba for aba in planilha.sheet_names
        if all(coluna in planilha.parse(aba, nrows=0).columns for coluna in COLUNAS_OCORRENCIAS)
    ]


def ler_ocorrencias(fonte, aba=None):
    """Lê o arquivo de ocorrências (.xlsx na aba `aba`, ou .csv) sem tratar
    nada ainda -- CSV tem separador e codificação variáveis, então detecta
    (mesma ordem de tentativas do Relatório da IA no script original)."""
    dados = _bytes_da_fonte(fonte)
    if _e_csv(fonte):
        ultimo_erro = None
        for encoding in ("utf-8-sig", "utf-8", "latin1", "cp1252"):
            try:
                return pd.read_csv(io.BytesIO(dados), sep=None, engine="python", encoding=encoding)
            except UnicodeError as erro:
                ultimo_erro = erro
        raise ValueError("Não foi possível ler o CSV de ocorrências com nenhuma codificação testada.") from ultimo_erro
    return pd.read_excel(io.BytesIO(dados), sheet_name=aba if aba is not None else 0)


def mes_producao_ocorrencias(bruto):
    """Mês ('YYYY-MM') mais frequente de Dt. Producao -- pra tela mostrar de
    qual período são as ocorrências (o Excel pode trazer a data como número
    serial, ex: 46204 = 2026-07-01, ou já como data)."""
    if COL_DATA_PRODUCAO_OCORRENCIAS not in bruto.columns:
        return None
    serie = bruto[COL_DATA_PRODUCAO_OCORRENCIAS].dropna()
    if serie.empty:
        return None
    if pd.api.types.is_datetime64_any_dtype(serie):
        datas = serie
    else:
        numerica = pd.to_numeric(serie, errors="coerce")
        datas = pd.concat([
            pd.to_datetime(numerica.dropna(), unit="D", origin="1899-12-30", errors="coerce"),
            pd.to_datetime(serie[numerica.isna()], errors="coerce", dayfirst=True),
        ])
    datas = datas.dropna()
    if datas.empty:
        return None
    return datas.dt.strftime("%Y-%m").mode().iloc[0]


def _preparar_ocorrencias(ocorrencias):
    """Corpo idêntico ao início de _carregar_ocorrencias do original: valida
    colunas, descarta linha sem prestador, monta a chave, junta o texto
    partido na ordem original e fica com uma linha por Nu. Ordem."""
    _validar_colunas(ocorrencias, COLUNAS_OCORRENCIAS, "ocorrências")

    # Linha sem Nome Prestador não é uma ocorrência de verdade -- é lixo de
    # exportação (ex: uma anotação solta que vazou pra linha própria, com o
    # texto caindo até na coluna de Nu. Ordem por engano). Sem prestador não
    # tem como vincular a processo nenhum, então descarta antes de agregar
    # pra não formar um grupo fantasma "_chave == 'NAN'".
    ocorrencias = ocorrencias[ocorrencias[COL_PRESTADOR_OCORRENCIAS].notna()].copy()

    ocorrencias["_chave"] = ocorrencias[COL_PRESTADOR_OCORRENCIAS].astype(str).str.strip().str.upper()

    # Quando o mesmo Nu. Ordem aparece em mais de uma linha seguida, o texto da
    # ocorrência foi partido ao meio -> junta na ORDEM ORIGINAL das linhas (não
    # alfabética) antes de classificar, senão a frase sai embaralhada.
    texto_completo = ocorrencias.groupby(COL_PROCESSO_OCORRENCIAS, sort=False)[COL_TEXTO_OCORRENCIA].transform(
        lambda x: " ".join(str(v).strip() for v in x if pd.notna(v))
    )
    ocorrencias[COL_TEXTO_OCORRENCIA] = texto_completo
    return ocorrencias.drop_duplicates(subset=[COL_PROCESSO_OCORRENCIAS], keep="first")


def _agregar_ocorrencias(ocorrencias, incluir_compulsorio_no_sim=False):
    """Classifica cada Nu. Ordem e agrega por prestador (pior prevalece:
    N > PAR > REVISAR > S). Com `incluir_compulsorio_no_sim=False` é o
    comportamento original."""
    if ocorrencias.empty:
        return pd.DataFrame(columns=["_chave", "CLASSIFICACAO", "OCORRENCIA", "COMPULSORIO_SIM"])

    ocorrencias = ocorrencias.copy()
    ocorrencias["_classificacao"] = ocorrencias[COL_TEXTO_OCORRENCIA].apply(
        lambda texto: classificar_texto(texto, incluir_compulsorio_no_sim)
    )
    ocorrencias["_compulsorio_sim"] = ocorrencias[COL_TEXTO_OCORRENCIA].apply(
        lambda texto: bool(incluir_compulsorio_no_sim and eh_modelo_fechamento_compulsorio(texto))
    )

    return ocorrencias.groupby("_chave").agg(
        CLASSIFICACAO=("_classificacao", lambda x: prioridade(list(x))),
        OCORRENCIA=(COL_TEXTO_OCORRENCIA, lambda x: " | ".join(dict.fromkeys(str(v) for v in x if pd.notna(v)))),
        COMPULSORIO_SIM=("_compulsorio_sim", "any"),
    ).reset_index()


def carregar_ocorrencias(fonte, aba=None, incluir_compulsorio_no_sim=False):
    """Lê + prepara + classifica + agrega o arquivo de ocorrências.
    Devolve (agregado por prestador, InfoOcorrencias)."""
    bruto = ler_ocorrencias(fonte, aba)
    ocorrencias = _preparar_ocorrencias(bruto)
    agregado = _agregar_ocorrencias(ocorrencias, incluir_compulsorio_no_sim)

    textos = ocorrencias[COL_TEXTO_OCORRENCIA]
    compulsorio = textos.apply(tem_fechamento_compulsorio).astype(bool)
    modelo_padrao = textos.apply(eh_modelo_fechamento_compulsorio).astype(bool)
    info = InfoOcorrencias(
        mes_producao=mes_producao_ocorrencias(bruto),
        total_processos=len(ocorrencias),
        fechamentos_compulsorios=int(compulsorio.sum()),
        compulsorios_no_sim=int((compulsorio & modelo_padrao).sum()) if incluir_compulsorio_no_sim else 0,
        compulsorios_fora_do_padrao=int((compulsorio & ~modelo_padrao).sum()) if incluir_compulsorio_no_sim else 0,
    )
    return agregado, info


# --- Cruzamento produção x ocorrências ---

def preparar_sem_dado(sem_dado):
    """Aba 'Sem dado de procedimento': processos sem nenhuma linha na base IA.
    `sem_dado` é um DataFrame com ORDEM/PRESTADOR/QT_PROCEDIMENTO (e OBS,
    opcional); esses processos NÃO passam pelo filtro de crítica nem pela
    classificação por ocorrência (revisão manual, como no original)."""
    if sem_dado is None or sem_dado.empty:
        return pd.DataFrame(columns=COLUNAS_SAIDA)
    df = sem_dado.copy()
    if COL_OBS not in df.columns:
        df[COL_OBS] = ""
    df["CLASSIFICACAO"] = "SEM_DADO_PROCEDIMENTO"
    df["OCORRENCIA"] = "SEM DADO DE PROCEDIMENTO NO RELATÓRIO DA IA"
    return df[COLUNAS_SAIDA].reset_index(drop=True)


def cruzar(producao, agregado, sem_dado=None):
    """Cruza a produção (já filtrada) com as ocorrências por nome de prestador
    e monta os 6 baldes. Mesma lógica do trecho final de processar() do
    original, mais a regra dos 100% e a coluna OBS (ver docstring do módulo).

    `producao`: ORDEM, PRESTADOR, QT_PROCEDIMENTO e, opcionais, OBS (texto
    livre, ex: glosas do REL5310) e LIBERADO_100_IA (bool).
    `agregado`: retorno de carregar_ocorrencias()[0].
    `sem_dado`: processos sem dado de procedimento (ver preparar_sem_dado)."""
    producao = producao.copy()
    producao["_chave"] = producao[COL_PRESTADOR_PRODUCAO].astype(str).str.strip().str.upper()

    # nome de prestador da produção com caractere corrompido (ex: "Ç" virado
    # em código de fonte inválido) nunca bate por igualdade de string -- tenta
    # resolver por casamento único com curinga antes de desistir e mandar pra
    # "sem ocorrência"
    nomes_producao_originais = producao[COL_PRESTADOR_PRODUCAO].astype(str).str.strip().str.upper()
    mapa_correcao = _resolver_nomes_corrompidos(producao["_chave"], agregado["_chave"])
    nomes_corrigidos = []
    if mapa_correcao:
        chave_original = producao["_chave"].copy()
        producao["_chave"] = producao["_chave"].replace(mapa_correcao)
        for chave_corrompida, chave_resolvida in mapa_correcao.items():
            nomes_corrigidos.append({
                "PRESTADOR": nomes_producao_originais[chave_original == chave_corrompida].iloc[0],
                "NOME_ENCONTRADO": chave_resolvida,
            })

    resultado = producao.merge(agregado, on="_chave", how="left")

    sem_match = resultado["CLASSIFICACAO"].isna()

    # entre os "sem ocorrência", separa quem tem nome de prestador com
    # caractere corrompido -- não é falta de dado de verdade, é a exportação
    # da produção estragando um caractere (normalmente "Ç") e por isso nunca
    # vai bater com o nome (corretamente escrito) da planilha de ocorrências
    nome_suspeito = resultado[COL_PRESTADOR_PRODUCAO].apply(_tem_caractere_invalido)
    nomes_suspeitos = resultado.loc[sem_match & nome_suspeito, [COL_PROCESSO_PRODUCAO, COL_PRESTADOR_PRODUCAO]]
    nomes_suspeitos = nomes_suspeitos.rename(
        columns={COL_PROCESSO_PRODUCAO: "ORDEM", COL_PRESTADOR_PRODUCAO: "PRESTADOR"}
    ).to_dict("records")

    resultado.loc[sem_match, "CLASSIFICACAO"] = "SEM_OCORRENCIA"
    resultado.loc[sem_match, "OCORRENCIA"] = "OCORRÊNCIA NÃO ENCONTRADA NA PLANILHA"

    # --- acrescentado na integração: regra dos 100% + OBS ---
    if COL_LIBERADO_100 in resultado.columns:
        liberado_100 = resultado[COL_LIBERADO_100].fillna(False).astype(bool)
    else:
        liberado_100 = pd.Series(False, index=resultado.index)
    # PAR nunca é 100% liberado pela IA (palavra do usuário); se acontecer,
    # continua PAR -- análise de padrão/fraude não se resolve pela liberação.
    automatico_100 = liberado_100 & (resultado["CLASSIFICACAO"] != "PAR")
    compulsorio_sim = (
        resultado["COMPULSORIO_SIM"].fillna(False).astype(bool) & (resultado["CLASSIFICACAO"] == "S")
    )

    obs_base = resultado[COL_OBS].fillna("").astype(str) if COL_OBS in resultado.columns else pd.Series("", index=resultado.index)
    partes = pd.DataFrame({
        "a": pd.Series("", index=resultado.index).mask(automatico_100, NOTA_LIBERADO_100),
        "b": pd.Series("", index=resultado.index).mask(compulsorio_sim, NOTA_COMPULSORIO_SIM),
        "c": obs_base,
    })
    resultado[COL_OBS] = partes.apply(lambda linha: " | ".join(p for p in linha if p), axis=1) if len(partes) else ""
    resultado.loc[automatico_100, "CLASSIFICACAO"] = "S"

    planilhas = {}
    contagem = {}
    procedimentos = {}
    for chave, nome_aba in ABAS_SAIDA:
        if chave == "SEM_DADO_PROCEDIMENTO":
            df = preparar_sem_dado(sem_dado)
        else:
            df = resultado[resultado["CLASSIFICACAO"] == chave][COLUNAS_SAIDA].reset_index(drop=True)
        planilhas[nome_aba] = df
        contagem[chave] = len(df)
        procedimentos[chave] = int(pd.to_numeric(df[COL_QTDE_PROCEDIMENTOS_PRODUCAO], errors="coerce").fillna(0).sum())

    total = sum(contagem.values())
    sem_ocorrencia = contagem.get("SEM_OCORRENCIA", 0)
    percentual = (sem_ocorrencia / total * 100) if total else 0.0

    return ResultadoFarol(
        planilhas=planilhas,
        total_processos=total,
        contagem=contagem,
        sem_ocorrencia=sem_ocorrencia,
        percentual_sem_ocorrencia=percentual,
        nomes_suspeitos=nomes_suspeitos,
        nomes_corrigidos=nomes_corrigidos,
        procedimentos=procedimentos,
        automaticos_100=int(automatico_100.sum()),
    )


def _com_ordem_numerica(df):
    """ORDEM como número no Excel (é assim que o original grava) -- só
    converte se TODAS as ordens forem numéricas, senão deixa como está."""
    if df.empty:
        return df
    ordem = pd.to_numeric(df[COL_PROCESSO_PRODUCAO], errors="coerce")
    if ordem.isna().any():
        return df
    return df.assign(**{COL_PROCESSO_PRODUCAO: ordem.astype("int64")})


def salvar(resultado, destino):
    """Grava as 6 abas (mesmos nomes do original). `destino`: caminho ou
    buffer."""
    with pd.ExcelWriter(destino, engine="openpyxl") as writer:
        for _, nome_aba in ABAS_SAIDA:
            _com_ordem_numerica(resultado.planilhas[nome_aba]).to_excel(writer, sheet_name=nome_aba, index=False)


def para_bytes(resultado):
    buffer = io.BytesIO()
    salvar(resultado, buffer)
    return buffer.getvalue()
