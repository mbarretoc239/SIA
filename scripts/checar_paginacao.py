"""Varre shared/database.py atrás de `requests.get(` que não passam por
_get_paginado()/_get() -- o PostgREST corta em 1000 linhas por padrão, e
esse corte silencioso já causou bug real em produção (guia marcada como
vista sumindo da tela, confirmação de ciência de alinhamento "perdida").
Roda sem argumento, sai com código != 0 se achar alguma chamada suspeita.

Toda chamada de `requests.get(` fora de _get_paginado precisa ter um
comentário `# nao-paginado: <motivo>` na mesma linha ou até 2 linhas acima
-- não é número de linha fixo (quebraria a cada edição do arquivo), é uma
marca no próprio código que sobrevive a qualquer refatoração. Sem essa
marca, o script falha: ou a chamada precisa virar self._get_paginado(...),
ou precisa da marca justificando por que não.
"""
import re
import sys
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "shared" / "database.py"
MARCA = re.compile(r"#\s*nao-paginado:")
CHAMADA = re.compile(r"requests\.get\(")


def main() -> int:
    linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()
    achados = []
    for i, linha in enumerate(linhas):
        if not CHAMADA.search(linha):
            continue
        janela = linhas[max(0, i - 2):i + 1]
        if not any(MARCA.search(l) for l in janela):
            achados.append((i + 1, linha.strip()))

    if achados:
        print(f"Encontradas {len(achados)} chamada(s) requests.get() sem passar por _get_paginado:\n")
        for numero, linha in achados:
            print(f"  {ARQUIVO}:{numero}: {linha}")
        print(
            "\nSe a chamada é de fato segura (filtro por chave única, limit= "
            "explícito, contagem via Content-Range, paginação própria já "
            "implementada), adicione um comentário '# nao-paginado: <motivo>' "
            "na mesma linha ou nas 2 linhas acima. Senão, troque por "
            "self._get_paginado(url) ou self._get(endpoint)."
        )
        return 1

    print("OK -- nenhum requests.get() fora de _get_paginado sem justificativa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
