"""Quem pode usar a Lupita: cargo Admin (role_interno) ou um usuário da lista fechada (usuario_sigo).

Para liberar ou tirar alguém, edite USUARIOS_LIBERADOS / ROLES_LIBERADOS. A checagem existe em dois lugares:
no menu (app.py) e dentro de cada chamada ao banco (dados.py), pra uma tela esquecida
aberta ou uma rota direta não furar a trava.
"""
from __future__ import annotations

USUARIOS_LIBERADOS = frozenset({"EJ43058", "LCASTROA", "MATHBC"})
ROLES_LIBERADOS = frozenset({"ADMIN"})


class AcessoNegado(PermissionError):
    pass


def usuario_liberado(usuario_sigo, role=None) -> bool:
    if str(role or "").strip().upper() in ROLES_LIBERADOS:
        return True
    return str(usuario_sigo or "").strip().upper() in USUARIOS_LIBERADOS


def exigir_acesso(usuario_sigo, role=None) -> None:
    if not usuario_liberado(usuario_sigo, role):
        raise AcessoNegado("A Lupita está liberada só para usuários autorizados.")
