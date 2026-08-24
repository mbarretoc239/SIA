"""Varre o projeto inteiro atrás de leituras do Supabase que podem vir
cortadas -- o PostgREST corta a resposta em 1000 linhas por padrão,
silenciosamente (sem erro), e isso já causou bug real em produção mais de
uma vez nesta sessão (confirmação de ciência "sumindo", guia marcada como
vista reaparecendo como pendente).

Duas regras:

1. Dentro de shared/database.py (o único lugar que deveria falar com o
   Supabase): todo `requests.get(` precisa passar por
   `self._get_paginado(...)` ou ter um comentário `# nao-paginado: <motivo>`
   na mesma linha ou até 2 linhas acima, justificando por que está seguro
   sem paginar (limit= explícito, contagem via Content-Range, filtro por
   chave única).

2. Em QUALQUER outro arquivo .py do projeto: nenhuma linha deveria falar
   com o Supabase direto (`supabase_url` ou `/rest/v1/` num requests.get) --
   isso é o papel do DatabaseManager (shared/database.py). Se algum arquivo
   bater direto, é bug (foi assim que carregar_procedimentos_criticos, em
   core/amostragem.py, escapou da proteção por meses).

Roda sem argumento, sai com código != 0 se achar algo. Não depende de
número de linha (usa marca de comentário, sobrevive a qualquer edição).
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DATABASE = RAIZ / "shared" / "database.py"

MARCA = re.compile(r"#\s*nao-paginado:")
CHAMADA_GET = re.compile(r"requests\.get\(")
FALA_COM_SUPABASE = re.compile(r"supabase_url|/rest/v1/")

# Diretórios que nunca fazem parte do código-fonte do projeto.
IGNORAR_DIRS = {".git", ".githooks", "venv", ".venv", "__pycache__", "node_modules", "scripts", "scratch"}


def _checar_database_py() -> list[tuple[Path, int, str]]:
    """Regra 1: todo requests.get() em shared/database.py precisa de
    _get_paginado ou marca # nao-paginado por perto."""
    linhas = ARQUIVO_DATABASE.read_text(encoding="utf-8").splitlines()
    achados = []
    for i, linha in enumerate(linhas):
        if not CHAMADA_GET.search(linha):
            continue
        janela = linhas[max(0, i - 2):i + 1]
        if not any(MARCA.search(l) for l in janela):
            achados.append((ARQUIVO_DATABASE, i + 1, linha.strip()))
    return achados


def _checar_resto_do_projeto() -> list[tuple[Path, int, str]]:
    """Regra 2: nenhum outro arquivo .py deveria falar com o Supabase
    direto -- isso é papel exclusivo do DatabaseManager."""
    achados = []
    for caminho in RAIZ.rglob("*.py"):
        if caminho == ARQUIVO_DATABASE:
            continue
        if any(parte in IGNORAR_DIRS for parte in caminho.parts):
            continue
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, linha in enumerate(linhas):
            if not CHAMADA_GET.search(linha):
                continue
            janela = linhas[max(0, i - 3):i + 1]
            texto_janela = "\n".join(janela)
            if FALA_COM_SUPABASE.search(texto_janela) and not MARCA.search(texto_janela):
                achados.append((caminho, i + 1, linha.strip()))
    return achados


def main() -> int:
    achados = _checar_database_py() + _checar_resto_do_projeto()

    if achados:
        print(f"Encontrada(s) {len(achados)} leitura(s) do Supabase que podem vir cortada(s):\n")
        for caminho, numero, linha in achados:
            print(f"  {caminho.relative_to(RAIZ)}:{numero}: {linha}")
        print(
            "\nEm shared/database.py: troque por self._get_paginado(url), ou "
            "justifique com '# nao-paginado: <motivo>' se for de fato seguro "
            "(limit= explícito, contagem via Content-Range, chave única).\n"
            "Em qualquer outro arquivo: não fale com o Supabase direto -- "
            "adicione um método em DatabaseManager (shared/database.py) e "
            "chame por ele, que já garante a paginação."
        )
        return 1

    print("OK -- nenhuma leitura do Supabase fora da proteção de paginação.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
