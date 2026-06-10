import sys, json
sys.path.append('.')
from shared.database import DatabaseManager

db = DatabaseManager()
textos = db._get('textos_prestadores?select=id,titulo,glosas_relacionadas,texto')

with open('textos_dump.json', 'w', encoding='utf-8') as f:
    json.dump(textos, f, ensure_ascii=False, indent=4)
