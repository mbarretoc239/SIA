import sys
import os
sys.path.append(os.getcwd())
from shared.database import DatabaseManager
db = DatabaseManager()

db.toggle_ativo_alinhamento('3d07e7e2-f968-43d9-b945-617cafee3b93', False)
print('Inativado: 3d07e7e2-f968-43d9-b945-617cafee3b93')
db.toggle_ativo_alinhamento('d45de65a-9a1f-4a89-9a46-405d86ef2d79', False)
print('Inativado: d45de65a-9a1f-4a89-9a46-405d86ef2d79')
db.toggle_ativo_alinhamento('a44058f9-b4ff-422d-9064-2849ee004524', False)
print('Inativado: a44058f9-b4ff-422d-9064-2849ee004524')
db.toggle_ativo_alinhamento('6a347527-6bf9-48da-b780-a9a1f3fce5a5', False)
print('Inativado: 6a347527-6bf9-48da-b780-a9a1f3fce5a5')
db.toggle_ativo_alinhamento('69fba11f-85b8-4a1b-bb2f-0706f78d46e0', False)
print('Inativado: 69fba11f-85b8-4a1b-bb2f-0706f78d46e0')
