import sys
import os
sys.path.append(os.getcwd())
from shared.database import DatabaseManager

db = DatabaseManager()
todos = db.carregar_alinhamentos()

textos_procurar = [
    "Acrescentado coluna na planilha de ocorrências (IMAGENS ANEXADAS)",
    "lembrar de preencher a aba de IMAGENS ANEXADAS",
    "Em casos que a guia estiver datada com mês posterior gerando a glosa 013, esta deve ser mantida",
    "Para glosa 013 assim como as outras vamos manter a glosa",
    "A partir dessa produção de agosto iremos autorizar pagamento para glosa 013",
    "Para glosa 013 e glosa 043, assim como as outras, vamos manter a glosa",
    "vamos AUTORIZAR pagamento das glosas 013",
    "não será mais autorizado pg de glosa 074",
    "Deliberado continuar autorização de pagamento para prestadores SFo",
    "Atividade inativada em 01/11, seguir com sinalização em capa",
    "definido manter regras de procedimento para prestadores SFo até segunda ordem",
    "CONSIDERAR REGRA ATÉ PRODUÇÃO DEZ/21",
    "Parametrização de HOJE SOMENTE"
]

encontrados = []
for a in todos:
    for txt in textos_procurar:
        if txt.lower() in a.get('conteudo', '').lower() or txt.lower() in a.get('titulo', '').lower():
            if a not in encontrados:
                encontrados.append(a)

print(f"Total encontrados no banco para inativar: {len(encontrados)}")
for e in encontrados:
    print(f"ID: {e['id']} | Data: {e.get('created_at')} | Titulo: {e.get('titulo')}")
