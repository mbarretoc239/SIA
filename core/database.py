import sqlite3
from shared.utils import registrar_erro

def conectar_sqlite(caminho_banco, row_factory=False):
    conn = sqlite3.connect(caminho_banco, timeout=15)
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception as erro:
        registrar_erro(f"Falha ao configurar SQLite: {caminho_banco}", erro)
    return conn
