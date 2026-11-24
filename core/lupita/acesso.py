"""Quem pode usar a Lupita: sistema de permissões por módulo do SIA (módulo "lupita").

Liberar ou tirar alguém é em Configurações > Permissões (função ou exceção por usuário), sem deploy.
Sem nenhuma linha configurada só o Admin acessa. Exceção individual "Bloquear" vale até contra Admin
(regra de core.settings.tem_acesso_modulo).

A checagem existe em dois lugares: no menu (app.py) e dentro de cada chamada ao banco (dados.py),
pra uma tela esquecida aberta ou uma rota direta não furar a trava.

Egress: usa os mesmos caches de 60 s que o app.py já consulta a cada rerun (carregar_*_modulos_cache),
então a Lupita não adiciona nenhuma leitura. Se o banco de permissões falhar, só o Admin passa (fecha).
"""
from __future__ import annotations

MODULO = "lupita"


class AcessoNegado(PermissionError):
    pass


def _carregar_permissoes():
    from core.settings import carregar_excecoes_modulos_cache, carregar_permissoes_modulos_cache
    return carregar_permissoes_modulos_cache(), carregar_excecoes_modulos_cache()


def usuario_liberado(usuario_sigo, role=None, usuario_id=None) -> bool:
    """`usuario_sigo` não decide mais nada (a exceção é por `usuario_id`); fica por compatibilidade."""
    from core.settings import tem_acesso_modulo
    try:
        permissoes, excecoes = _carregar_permissoes()
    except Exception:
        return str(role or "").strip().upper() == "ADMIN"
    return tem_acesso_modulo(permissoes, str(role or "").strip().title() or None, MODULO, usuario_id, excecoes)


def exigir_acesso(usuario_sigo, role=None, usuario_id=None) -> None:
    if not usuario_liberado(usuario_sigo, role, usuario_id):
        raise AcessoNegado("A Lupita está liberada só para usuários autorizados.")
