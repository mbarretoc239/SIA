import sys
import os
sys.path.append(os.getcwd())
from shared.database import DatabaseManager

db = DatabaseManager()

ids_para_inativar = [
    "fb53f8dd-6b4b-422f-8259-a041882057f4",
    "15aa8949-4b72-40fd-ba90-052a979bc92b",
    "aa8624a9-9abc-487d-ac6c-c7d0f1f9ae2e",
    "2e25bcce-8040-4014-a6b4-ce89e4997245",
    "f1882b04-c3dc-4dba-b933-f10965331a65",
    "fe1f8466-9c3b-4707-8634-9da2ec8d5ebc",
    "4b95ba64-26f0-4753-9557-8d9330e681a5",
    "12f76d3a-046e-4733-9000-b191b1b4ee33",
    "2b9ff90d-010b-453b-afce-0c9275fd8a01",
    "6891507a-603a-4c9b-bb3a-476f445c0b95",
    "68cf45e6-5d59-4bf0-ba36-03a3e9eaa980",
    "da7d7f32-b1a9-4bc7-825d-3c30003a8748",
    "5eafcc1c-2914-4a00-b585-2d5f2447f925"
]

for i in ids_para_inativar:
    sucesso = db.toggle_ativo_alinhamento(i, False)
    if sucesso:
        print(f"✅ Inativado: {i}")
    else:
        print(f"❌ Erro ao inativar: {i}")
