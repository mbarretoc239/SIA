"""Importa o JSON exportado pela Lupita do navegador (lupa-forense-dados.json) e treina o 1º modelo.

Guarda só as 56 medidas, o rótulo e o lote. NÃO grava nome de arquivo (campos `n` e `k` parecem
identificadores do sistema de origem) nem a impressão digital 32x32 (`p`).

Uso (na raiz do projeto):
  python scripts/importar_lupita_json.py CAMINHO.json --simular      # só treina e mostra as métricas
  python scripts/importar_lupita_json.py CAMINHO.json --gravar       # importa amostras + ativa o modelo
  python scripts/importar_lupita_json.py CAMINHO.json --so-modelo    # só nova versão do modelo (sem amostras)

`--gravar` usa o Supabase dos secrets (service_role) e exige a migration migrations/lupita.sql aplicada.
Rodar de novo com --gravar duplica as amostras: só use numa tabela vazia.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lupita import motor as L  # noqa: E402
from core.lupita import predicao as P  # noqa: E402


def ler_amostras(caminho: str) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("app") != "lupa-forense" or not isinstance(dados.get("samples"), list):
        raise SystemExit("Este arquivo não parece ser um JSON exportado pela Lupita (navegador).")
    saida = []
    for s in dados["samples"]:
        f = s.get("f")
        if not isinstance(f, dict) or any(k not in f for k in P.CHAVES_TODAS):
            continue
        saida.append({"medidas": P.medidas_em_lista(f), "rotulo": 1 if s.get("l") else 0,
                      "lote": str(s.get("b")) if s.get("b") is not None else None})
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("json")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--simular", action="store_true")
    modo.add_argument("--gravar", action="store_true")
    modo.add_argument("--so-modelo", action="store_true",
                      help="treina com o JSON e grava SÓ uma nova versão do modelo (não importa amostras)")
    args = ap.parse_args()

    amostras = ler_amostras(args.json)
    n_ia = sum(a["rotulo"] for a in amostras)
    print(f"{len(amostras)} amostras lidas ({n_ia} de IA, {len(amostras) - n_ia} reais)")

    modelo = P.treinar_de_linhas([a["medidas"] for a in amostras], [a["rotulo"] for a in amostras])
    v = modelo["validacao_cruzada"]
    print(f"Grupos: {' '.join(modelo['grupos'])} ({len(modelo['chaves'])} medidas) | lambda {modelo['lambda']}")
    print(f"Validação cruzada: AUC {v['auc']:.3f} | acerto {v['acerto']:.1%} | reais acusadas "
          f"{v['fpr_reais']:.1%} | IA detectadas {v['recall_ia']:.1%}")
    if args.simular:
        print("Simulação: nada foi gravado.")
        return 0

    import streamlit as st  # noqa: F401  (DatabaseManager lê st.secrets)
    from core.lupita.dados import LupitaRepo
    from shared.database import DatabaseManager

    repo = LupitaRepo(DatabaseManager(), "MATHBC", acesso_script=True)
    if args.gravar:
        repo.inserir_amostras_importadas(amostras)
    versao = repo.salvar_modelo(modelo, origem=f"importação de {os.path.basename(args.json)}")
    if args.gravar:
        print(f"Gravado: {len(amostras)} amostras e modelo versão {versao} (ativo).")
    else:
        print(f"Gravado só o modelo versão {versao} (ativo); nenhuma amostra foi importada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
