"""Exporta pro JSON local que o Farol Mensal offline usa (ver
ferramentas/farol_mensal_offline.py) os 3 dados pequenos que hoje só existem
no Supabase e que a classificação de "crítica"/cruzamento do REL5310
precisa:

- especialidades_criticas: regra de amostragem (amostragem_regras_amostra)
- procedimentos_criticos: tabela de procedimentos críticos
- mapa_procedimentos: {codigo_curto: descricao} (tabela_procedimentos) --
  usado pra cruzar o REL5310 pelo nome do procedimento

O Farol Mensal offline roda sem NENHUMA conexão de rede, de propósito (foi
pra isso que ele foi criado -- não bater no Turso de novo). Rode este script
de novo sempre que mudar especialidades/procedimentos críticos em
Configurações, ou se um procedimento novo entrar no catálogo.

Uso (precisa do .streamlit/secrets.toml do projeto, só pra ESTE export):
    python scripts/exportar_dados_farol_offline.py
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.amostragem import carregar_regras_amostragem_cache, carregar_procedimentos_criticos  # noqa: E402
from services.relatorio_5302.glosa_matcher import carregar_mapa_procedimentos  # noqa: E402

DESTINO = RAIZ / "ferramentas" / "dados_farol_offline.json"


def main():
    _, ordem_criticas = carregar_regras_amostragem_cache()
    procedimentos_criticos = carregar_procedimentos_criticos()
    mapa_procedimentos = carregar_mapa_procedimentos()

    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(
        json.dumps({
            "especialidades_criticas": sorted(ordem_criticas),
            "procedimentos_criticos": sorted(procedimentos_criticos),
            "mapa_procedimentos": mapa_procedimentos,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Exportado em {DESTINO}\n"
        f"  {len(ordem_criticas)} especialidade(s) crítica(s)\n"
        f"  {len(procedimentos_criticos)} procedimento(s) crítico(s)\n"
        f"  {len(mapa_procedimentos)} procedimento(s) no catálogo (pro cruzamento do REL5310)"
    )


if __name__ == "__main__":
    main()
