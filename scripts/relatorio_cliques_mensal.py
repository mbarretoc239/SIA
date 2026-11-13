"""Relatório mensal de rastreabilidade: guias clicadas (Amostragem) por processo.

Gera uma planilha com as guias que os auditores clicaram (ficaram "verdes" na
Amostragem) em UM mês fechado, agrupadas por processo. Pensado pra rodar todo
dia 1 e salvar o mês anterior inteiro (dia 1 ao último dia, horário de
Brasília) no Desktop.

Uso:
    python scripts/relatorio_cliques_mensal.py                # mês anterior
    python scripts/relatorio_cliques_mensal.py --mes 2026-11  # mês específico
    python scripts/relatorio_cliques_mensal.py --ate 2026-11-11T16:46  # parcial (teste)

Fontes:
  - Cliques: Supabase `amostragem_guias_vistas` (nu_guia, marcado_em). Só tem
    1 data por guia e não guarda quem clicou.
  - Itens da guia: `base_ia_guias` no Turso, do mês ANTERIOR ao do clique
    (produção N é auditada em N+1). Resolve sozinho as guias que existem em
    duas bases, porque só lê a base do mês certo.
  - Processo/prestador/tipo/status/auditor: REL5201 mais recente do banco.
  - Críticos: ferramentas/dados_farol_offline.json (especialidade crítica OU
    procedimento crítico).

A base IA do mês é guardada em cache local (pasta de saída/_cache) logo após a
1ª leitura. Se o app apagar o mês antigo do Turso (ele só retém os 2 meses mais
recentes), as próximas execuções ainda conseguem rodar.
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .streamlit/secrets.toml

import pandas as pd

BRT = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
PASTA_PADRAO = os.path.join(DESKTOP, "cliques mensais")
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
            "agosto", "setembro", "outubro", "novembro", "dezembro"]


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def limites_do_mes(mes: str) -> tuple[datetime, datetime]:
    """[início, fim) do mês em BRT: dia 1 00:00 até dia 1 do mês seguinte 00:00."""
    ano, m = (int(p) for p in mes.split("-"))
    ini = datetime(ano, m, 1, tzinfo=BRT)
    ano_f, m_f = (ano + 1, 1) if m == 12 else (ano, m + 1)
    return ini, datetime(ano_f, m_f, 1, tzinfo=BRT)


def buscar_cliques(db, ini: datetime, fim: datetime) -> pd.DataFrame:
    url = (
        f"{db.supabase_url}/rest/v1/amostragem_guias_vistas?select=nu_guia,marcado_em"
        f"&marcado_em=gte.{ini.isoformat()}&marcado_em=lt.{fim.isoformat()}&order=nu_guia"
    )
    linhas = db._get_paginado(url)
    df = pd.DataFrame(linhas, columns=["nu_guia", "marcado_em"])
    df["nu_guia"] = df["nu_guia"].astype(str).str.strip()
    df["marcado_em"] = (
        pd.to_datetime(df["marcado_em"], utc=True, format="ISO8601")
        .dt.tz_convert(BRT).dt.tz_localize(None)
    )
    return df


def buscar_base_ia(db, mes_ia: str, pasta_cache: str) -> pd.DataFrame:
    """Todos os itens (liberados e não liberados) da base IA do mês."""
    os.makedirs(pasta_cache, exist_ok=True)
    cache = os.path.join(pasta_cache, f"base_ia_{mes_ia}.pkl")
    if os.path.exists(cache):
        print(f"Base IA {mes_ia}: usando cache {cache}")
        return pd.read_pickle(cache)

    print(f"Base IA {mes_ia}: lendo do Turso...")
    registros, ultimo_rowid = [], 0
    while True:
        resultado = db._turso_pipeline([{
            "sql": "SELECT rowid AS rid, nu_ordem, nu_guia, cd_procedimento, ds_grupo "
                   "FROM base_ia_guias WHERE mes_referencia = ? AND rowid > ? "
                   "ORDER BY rowid LIMIT 50000",
            "args": [db._turso_arg(mes_ia), db._turso_arg(ultimo_rowid)],
        }], db._turso_token_leitura)[0]
        lote = db._turso_linhas(resultado)
        if not lote:
            break
        registros.extend(lote)
        ultimo_rowid = int(lote[-1]["rid"])
    if not registros:
        raise RuntimeError(
            f"Base IA de {mes_ia} está vazia no Turso (o app só retém os 2 meses mais "
            f"recentes) e não há cache local em {cache}."
        )
    df = pd.DataFrame(registros).drop(columns="rid")
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    df.to_pickle(cache)
    print(f"Base IA {mes_ia}: {len(df):,} itens (cache salvo).")
    return df


def carregar_5201(db) -> pd.DataFrame:
    from core.relatorio_5201 import registros_para_df
    df = registros_para_df(db.carregar_relatorio_5201())
    df["ORDEM"] = df["ORDEM"].astype(str).str.strip()
    # mesmo critério do md: fechamento, ou consistência quando fechamento vazio
    fech = df.get("LOGIN_FECHAMENTO", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    cons = df.get("LOGIN_CONSISTENCIA", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    df["_auditor"] = fech.where(fech != "", cons)
    if "_importado_em" in df.columns:  # se o mesmo processo aparecer em 2 meses, fica o mais recente
        df = df.sort_values("_importado_em").drop_duplicates("ORDEM", keep="last")
    return df.set_index("ORDEM")


def montar(cliques: pd.DataFrame, ia: pd.DataFrame, r5201: pd.DataFrame, crit: dict):
    ia = ia.copy()
    ia["critico"] = ia["ds_grupo"].isin(set(crit["especialidades_criticas"])) | \
        ia["cd_procedimento"].isin(set(crit["procedimentos_criticos"]))

    tot = ia.groupby("nu_ordem").agg(
        guias_tot=("nu_guia", "nunique"), itens_tot=("nu_guia", "size"), crit_tot=("critico", "sum"))
    guias_crit_tot = ia[ia["critico"]].groupby("nu_ordem")["nu_guia"].nunique().rename("guias_crit_tot")

    # 1 linha por item das guias clicadas (a guia só existe em 1 processo na base do mês)
    itens = cliques.merge(ia, on="nu_guia", how="left")
    sem_ia = int(itens["nu_ordem"].isna().groupby(itens["nu_guia"]).all().sum())
    itens = itens.dropna(subset=["nu_ordem"])

    cl = itens.groupby("nu_ordem").agg(
        guias_clic=("nu_guia", "nunique"), itens_clic=("nu_guia", "size"),
        crit_clic=("critico", "sum"), primeiro=("marcado_em", "min"), ultimo=("marcado_em", "max"))
    guias_crit_clic = itens[itens["critico"]].groupby("nu_ordem")["nu_guia"].nunique().rename("guias_crit_clic")

    proc = cl.join(tot).join(guias_crit_tot).join(guias_crit_clic).fillna({"guias_crit_tot": 0, "guias_crit_clic": 0})
    info = r5201.reindex(proc.index)
    tipo = info.get("TIPO_PRESTADOR", pd.Series(index=proc.index, dtype=object))
    por_proc = pd.DataFrame({
        "Processo": pd.to_numeric(proc.index),
        "Prestador": info["PRESTADOR"].values if "PRESTADOR" in info else "",
        "TIPO": tipo.values,
        "Execução": info["EXECUCAO"].values if "EXECUCAO" in info else "",
        "Status 5201": info["STATUS"].values,
        "Auditor (fechamento/consistência)": info["_auditor"].values,
        "Guias (total)": proc["guias_tot"].values,
        "Guias clicadas": proc["guias_clic"].values,
        "% guias clicadas": (100 * proc["guias_clic"] / proc["guias_tot"]).round(1).values,
        "Itens (total)": proc["itens_tot"].values,
        "Itens nas guias clicadas": proc["itens_clic"].values,
        "% itens clicados": (100 * proc["itens_clic"] / proc["itens_tot"]).round(1).values,
        "Guias com item crítico (total)": proc["guias_crit_tot"].astype(int).values,
        "Guias com item crítico clicadas": proc["guias_crit_clic"].astype(int).values,
        "Itens críticos (total)": proc["crit_tot"].astype(int).values,
        "Itens críticos nas guias clicadas": proc["crit_clic"].astype(int).values,
        "Primeiro clique": proc["primeiro"].values,
        "Último clique": proc["ultimo"].values,
    }).sort_values("Itens nas guias clicadas", ascending=False)

    detalhe = itens.rename(columns={
        "nu_guia": "Guia", "nu_ordem": "Processo", "marcado_em": "Data/hora do clique",
        "cd_procedimento": "Código do procedimento", "ds_grupo": "Especialidade",
        "critico": "Item crítico"})[
        ["Guia", "Processo", "Data/hora do clique", "Código do procedimento", "Especialidade", "Item crítico"]]
    detalhe["Item crítico"] = detalhe["Item crítico"].map({True: "Sim", False: "Não"})
    for col in ("Guia", "Processo"):  # número quando der (Excel), texto se tiver prefixo de letra
        numerico = pd.to_numeric(detalhe[col], errors="coerce")
        detalhe[col] = numerico.where(numerico.notna(), detalhe[col])
    detalhe = detalhe.sort_values(["Processo", "Data/hora do clique", "Guia"])
    return por_proc, detalhe, sem_ia, int(proc["itens_tot"].isna().sum()), int(info["STATUS"].isna().sum())


def notificar(titulo: str, mensagem: str) -> None:
    """Aviso na bandeja do Windows (balão). Falha de notificação nunca derruba o relatório."""
    if os.name != "nt":
        return
    try:
        import subprocess
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
            f"$n.ShowBalloonTip(15000,'{titulo}','{mensagem}',[System.Windows.Forms.ToolTipIcon]::Info);"
            "Start-Sleep -Seconds 16;$n.Dispose()"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])
    except Exception:
        pass


def gerar(mes: str, pasta: str, ate: datetime | None = None) -> str:
    from shared.database import DatabaseManager
    db = DatabaseManager()
    ini, fim = limites_do_mes(mes)
    if ate:
        fim = min(fim, ate)
    ano, m = (int(p) for p in mes.split("-"))
    ano_ia, m_ia = mes_anterior(ano, m)
    mes_ia = f"{ano_ia:04d}-{m_ia:02d}"

    cliques = buscar_cliques(db, ini, fim)
    print(f"Cliques de {ini:%d/%m/%Y} a {(fim - timedelta(seconds=1)):%d/%m/%Y %H:%M}: {len(cliques):,}")
    if cliques.empty:
        raise RuntimeError(f"Nenhum clique encontrado em {mes} — conferir se o filtro/tabela estão certos.")

    ia = buscar_base_ia(db, mes_ia, os.path.join(pasta, "_cache"))
    r5201 = carregar_5201(db)
    with open(os.path.join(RAIZ, "ferramentas", "dados_farol_offline.json"), encoding="utf-8") as f:
        crit = json.load(f)

    por_proc, detalhe, sem_ia, _, sem_5201 = montar(cliques, ia, r5201, crit)

    resumo = pd.DataFrame([
        ("Período", f"{ini:%Y-%m-%d} a {(fim - timedelta(seconds=1)):%Y-%m-%d}" + (" (parcial)" if ate else "")),
        ("Base IA usada", mes_ia),
        ("Cliques no período", len(cliques)),
        (f"Cliques sem correspondência na base IA ({mes_ia})", sem_ia),
        ("Processos com pelo menos 1 clique", len(por_proc)),
        ("Guias clicadas", int(por_proc["Guias clicadas"].sum())),
        ("Itens nas guias clicadas", int(por_proc["Itens nas guias clicadas"].sum())),
        ("Itens críticos nas guias clicadas", int(por_proc["Itens críticos nas guias clicadas"].sum())),
        ("Processos sem dado no 5201", sem_5201),
        ("% médio de itens clicados por processo", round(float(por_proc["% itens clicados"].mean()), 1)),
        ("Gerado em", datetime.now(BRT).strftime("%d/%m/%Y %H:%M (BRT)")),
    ], columns=["Indicador", "Valor"])

    os.makedirs(pasta, exist_ok=True)
    sufixo = "_parcial" if ate else ""
    destino = os.path.join(pasta, f"cliques_por_processo_{MESES_PT[m - 1]}_{ano}{sufixo}.xlsx")
    with pd.ExcelWriter(destino, engine="openpyxl", datetime_format="DD/MM/YYYY HH:MM:SS") as xw:
        por_proc.to_excel(xw, sheet_name="Por processo", index=False)
        detalhe.to_excel(xw, sheet_name="Guias clicadas", index=False)
        resumo.to_excel(xw, sheet_name="Resumo", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(12, largura + 2), 45)
    print(f"Salvo: {destino}")
    print(resumo.to_string(index=False))
    return destino


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", help="YYYY-MM (padrão: mês anterior, em BRT)")
    ap.add_argument("--saida", default=PASTA_PADRAO)
    ap.add_argument("--ate", help="limita o fim (BRT, ISO) — só pra teste/parcial")
    ap.add_argument("--sem-aviso", action="store_true")
    args = ap.parse_args()

    hoje = datetime.now(BRT)
    mes = args.mes or "{:04d}-{:02d}".format(*mes_anterior(hoje.year, hoje.month))
    ate = datetime.fromisoformat(args.ate).replace(tzinfo=BRT) if args.ate else None
    try:
        destino = gerar(mes, args.saida, ate)
    except Exception as e:
        traceback.print_exc()
        if not args.sem_aviso:
            notificar("SIA: relatório de cliques FALHOU", f"Mês {mes}: {str(e)[:120]}".replace("'", ""))
        return 1
    if not args.sem_aviso:
        notificar("SIA: relatório de cliques pronto", f"Mês {mes} salvo em {os.path.basename(os.path.dirname(destino))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
