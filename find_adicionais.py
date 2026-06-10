import sys
import os
sys.path.append(os.getcwd())
from shared.database import DatabaseManager

db = DatabaseManager()
todos = db.carregar_alinhamentos()

encontrados = []
for a in todos:
    if not a.get("ativo", True):
        continue # Já inativo
    
    conteudo = a.get('conteudo', '').lower()
    titulo = a.get('titulo', '').lower()
    
    if "abonando as glosas de prazo, ou seja, 013 e 043" in conteudo:
        encontrados.append(a)
    elif "glosa 074" in conteudo or "glosa 074" in titulo or "glosa 74" in titulo or "glosa 74" in conteudo:
        encontrados.append(a)

print(f"Total adicionais encontrados: {len(encontrados)}")
for e in encontrados:
    print(f"ID: {e['id']} | Data: {e.get('created_at')} | Titulo: {e.get('titulo')}")

print("\nGerando script para inativar...")
with open("inativar_adicionais.py", "w", encoding="utf-8") as f:
    f.write("import sys\nimport os\nsys.path.append(os.getcwd())\nfrom shared.database import DatabaseManager\ndb = DatabaseManager()\n\n")
    for e in encontrados:
        f.write(f"db.toggle_ativo_alinhamento('{e['id']}', False)\n")
        f.write(f"print('Inativado: {e['id']}')\n")
