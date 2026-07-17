import streamlit as st
import requests
import hashlib
import bcrypt
from datetime import datetime, timezone
from cryptography.fernet import Fernet

class DatabaseManager:
    def __init__(self):
        # Acessa os segredos do Streamlit
        self.supabase_url = st.secrets["supabase"]["url"]
        self.supabase_key = st.secrets["supabase"]["key"]
        # service_role: chave privilegiada usada apenas em operações admin
        # (ex: reset de senha). NUNCA deve sair do servidor.
        self._service_role = st.secrets["supabase"].get("service_role", "")

        # Inicializa a criptografia Fernet
        self.fernet = Fernet(st.secrets["seguranca"]["fernet_key"].encode('utf-8'))

        # Headers padrão para a API REST do Supabase (PostgREST)
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def _admin_headers(self):
        """Headers com service_role para operações que exigem privilégio total.
        Nunca chamado a partir de código que possa ser acionado por usuário
        não-Admin — a checagem de role é feita antes por quem invoca."""
        if not self._service_role:
            raise RuntimeError("service_role não configurada em st.secrets['supabase']")
        return {
            "apikey": self._service_role,
            "Authorization": f"Bearer {self._service_role}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get(self, endpoint: str) -> list:
        url = f"{self.supabase_url}/rest/v1/{endpoint}"
        r = requests.get(url, headers=self.headers)
        return r.json() if r.ok else []

    def buscar_guias_vistas(self, nu_guias: list) -> set:
        """Guias (NU_GUIA) já marcadas como auditadas/vistas, dentre as informadas.

        Sem vínculo a usuário — é uma marcação compartilhada entre todos.
        """
        if not nu_guias:
            return set()
        filtro = ",".join(str(g) for g in nu_guias)
        url = f"{self.supabase_url}/rest/v1/amostragem_guias_vistas?nu_guia=in.({filtro})&select=nu_guia"
        r = requests.get(url, headers=self.headers)
        return {item["nu_guia"] for item in r.json()} if r.ok else set()

    # --- Base IA (Amostragem BETA): guias LIBERACAO=N importadas mensalmente ---
    def buscar_guias_ia_por_processo(self, nu_ordem: str) -> list:
        """Guias com LIBERACAO=N da base IA para um número de processo (NU_ORDEM)."""
        url = (
            f"{self.supabase_url}/rest/v1/base_ia_guias"
            f"?nu_ordem=eq.{nu_ordem}&select=nu_guia,cd_procedimento,ds_grupo"
        )
        r = requests.get(url, headers=self.headers)
        return r.json() if r.ok else []

    def importar_base_ia(self, registros: list, mes_referencia: str, lote: int = 2000) -> int:
        """Substitui os dados do `mes_referencia` informado (reimportação
        idempotente) e mantém só os 2 meses mais recentes na tabela.

        `registros`: lista de dicts com nu_ordem/nu_guia/cd_procedimento/
        ds_grupo/liberacao/mes_referencia já prontos para inserir.
        """
        url = f"{self.supabase_url}/rest/v1/base_ia_guias"
        headers_insert = {**self.headers, "Prefer": "return=minimal"}

        requests.delete(f"{url}?mes_referencia=eq.{mes_referencia}", headers=self.headers).raise_for_status()

        total = 0
        for i in range(0, len(registros), lote):
            pedaco = registros[i:i + lote]
            requests.post(url, headers=headers_insert, json=pedaco).raise_for_status()
            total += len(pedaco)

        r_meses = requests.get(f"{url}?select=mes_referencia", headers=self.headers)
        if r_meses.ok:
            meses = sorted({item["mes_referencia"] for item in r_meses.json()}, reverse=True)
            antigos = meses[2:]
            if antigos:
                filtro = ",".join(antigos)
                requests.delete(f"{url}?mes_referencia=in.({filtro})", headers=self.headers).raise_for_status()

        return total

    def carregar_dicionario_glosas(self) -> dict:
        """Carrega o dicionário de correção de textos de glosas do Supabase"""
        url = f"{self.supabase_url}/rest/v1/glosas_dicionario?select=texto_original,texto_corrigido"
        r = requests.get(url, headers=self.headers)
        if r.status_code == 200:
            return {item["texto_original"].lower().strip(): item["texto_corrigido"] for item in r.json()}
        return {}

    # --- Segurança e Hashing ---
    def criptografar(self, texto: str) -> str:
        if not texto: return ""
        return self.fernet.encrypt(texto.encode('utf-8')).decode('utf-8')

    def descriptografar(self, texto_cifrado: str) -> str:
        if not texto_cifrado: return ""
        try:
            return self.fernet.decrypt(texto_cifrado.encode('utf-8')).decode('utf-8')
        except Exception:
            return "[ERRO: DADO CORROMPIDO OU CHAVE INVÁLIDA]"
            
    _SHA256_SALT_LEGADO = "SIA_SALT_V5_A7B2!"

    def _hash_sha256_legado(self, senha: str) -> str:
        """Hash antigo (sha256 + salt estatico). Mantido APENAS para validar
        senhas de usuarios que ainda nao foram remigrados. Nao usar para novos
        cadastros nem para escrever no banco."""
        return hashlib.sha256((senha + self._SHA256_SALT_LEGADO).encode('utf-8')).hexdigest()

    def _hash_senha(self, senha: str) -> str:
        """Gera hash bcrypt para uso atual (novos cadastros / reset / troca)."""
        return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verificar_senha(self, senha_plain: str, senha_hash: str, algo: str) -> bool:
        """Valida senha respeitando o algoritmo com que ela foi gravada."""
        if algo == "bcrypt":
            try:
                return bcrypt.checkpw(senha_plain.encode('utf-8'), senha_hash.encode('utf-8'))
            except Exception:
                return False
        # Fallback: sha256 legado
        return self._hash_sha256_legado(senha_plain) == senha_hash

    # --- Autenticação e Usuários (SISTEMA DE LOGIN SIGO) ---
    def criar_usuario(self, usuario_sigo, nome_completo, senha, equipe):
        url = f"{self.supabase_url}/rest/v1/usuarios"
        
        # Define o role_interno inicial baseado na equipe, mas tudo nasce 'Pendente'.
        # "Admin" não é uma opção de auto-cadastro: só um Admin existente pode
        # promover alguém na aba "Aprovação de Equipe".
        role_map = {
            "Contas": "Contas",
            "Auditoria": "Auditor",
            "CISO": "CISO",
            "Gestor": "Gestor",
        }
        
        data = {
            "usuario_sigo": usuario_sigo,
            "nome_completo": nome_completo,
            "senha_hash": self._hash_senha(senha),
            "senha_algo": "bcrypt",
            "equipe": equipe,
            "role_interno": role_map.get(equipe, "Contas"),
            "status": "Pendente"
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code not in [200, 201]:
            return False

        try:
            novo_id = response.json()[0]["id"]
            self.marcar_todos_alinhamentos_lidos(novo_id)
        except (IndexError, KeyError):
            pass
        return True

    def marcar_todos_alinhamentos_lidos(self, usuario_id):
        """Marca todo o histórico de alinhamentos existente como lido para um usuário,
        para que apenas alinhamentos publicados após este momento gerem popup obrigatório."""
        existentes = self.carregar_alinhamentos()
        if not existentes:
            return True

        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = [{"alinhamento_id": a["id"], "usuario_id": usuario_id} for a in existentes]
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def autenticar_usuario(self, usuario_sigo, senha):
        url = f"{self.supabase_url}/rest/v1/usuarios?usuario_sigo=eq.{usuario_sigo}&select=*"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return None
        usuarios = response.json()
        if not usuarios:
            return None
        user = usuarios[0]

        algo = user.get("senha_algo") or "sha256_v5"
        if not self._verificar_senha(senha, user["senha_hash"], algo):
            return None

        # Rehash-on-login: se a senha do usuario ainda esta com o hash antigo,
        # regravamos com bcrypt agora (transparente). A senha em texto claro so
        # existe aqui neste request, ja validada.
        if algo != "bcrypt":
            try:
                novo_hash = self._hash_senha(senha)
                patch_url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{user['id']}"
                requests.patch(
                    patch_url,
                    headers=self.headers,
                    json={"senha_hash": novo_hash, "senha_algo": "bcrypt"},
                )
                user["senha_hash"] = novo_hash
                user["senha_algo"] = "bcrypt"
            except Exception:
                # Se o rehash falhar, o login prossegue normalmente com o hash
                # antigo — apenas nao migramos desta vez.
                pass

        return user

    def listar_usuarios(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def atualizar_usuario_admin(self, usuario_id, status, role_interno, equipe):
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        data = {
            "status": status,
            "role_interno": role_interno,
            "equipe": equipe
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def excluir_usuario(self, usuario_id, atuante_role):
        if str(atuante_role) != "Admin":
            return False
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        response = requests.delete(url, headers=self._admin_headers())
        return response.status_code in [200, 204]

    def resetar_senha(self, usuario_alvo_id, nova_senha_temp, atuante_role):
        """Reseta a senha de OUTRO usuário. Só permitido para Admin.
        Grava a flag `senha_temporaria = true` para forçar troca no proximo login.
        Usa service_role para escrever ignorando RLS."""
        if str(atuante_role) != "Admin":
            return False
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_alvo_id}"
        data = {
            "senha_hash": self._hash_senha(nova_senha_temp),
            "senha_algo": "bcrypt",
            "senha_temporaria": True,
        }
        response = requests.patch(url, headers=self._admin_headers(), json=data)
        return response.status_code in [200, 204]

    # --- Links Padrão (institucionais, exibidos na Home) ---
    _ROLES_QUE_GERENCIAM_LINKS = {"Admin", "Gestor"}

    def listar_links_padrao(self, incluir_inativos: bool = False):
        base = f"{self.supabase_url}/rest/v1/links_padrao?select=*&order=categoria.asc,ordem.asc"
        if not incluir_inativos:
            base += "&ativo=eq.true"
        r = requests.get(base, headers=self.headers)
        return r.json() if r.status_code == 200 else []

    def inserir_link_padrao(self, titulo, url, categoria, ordem, atuante_role):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao"
        data = {"titulo": titulo, "url": url, "categoria": categoria or "Geral", "ordem": int(ordem or 100)}
        r = requests.post(endpoint, headers=self._admin_headers(), json=data)
        return r.status_code in (200, 201)

    def atualizar_link_padrao(self, link_id, titulo, url, categoria, ordem, ativo, atuante_role):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao?id=eq.{link_id}"
        data = {"titulo": titulo, "url": url, "categoria": categoria or "Geral", "ordem": int(ordem or 100), "ativo": bool(ativo)}
        r = requests.patch(endpoint, headers=self._admin_headers(), json=data)
        return r.status_code in (200, 204)

    def deletar_link_padrao(self, link_id, atuante_role):
        if str(atuante_role) not in self._ROLES_QUE_GERENCIAM_LINKS:
            return False
        endpoint = f"{self.supabase_url}/rest/v1/links_padrao?id=eq.{link_id}"
        r = requests.delete(endpoint, headers=self._admin_headers())
        return r.status_code in (200, 204)

    def trocar_senha_propria(self, usuario_id, nova_senha):
        """Usuário troca a própria senha. Zera a flag `senha_temporaria`."""
        url = f"{self.supabase_url}/rest/v1/usuarios?id=eq.{usuario_id}"
        data = {
            "senha_hash": self._hash_senha(nova_senha),
            "senha_algo": "bcrypt",
            "senha_temporaria": False,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Tabela Procedimentos) ---
    def carregar_procedimentos(self):
        url = f"{self.supabase_url}/rest/v1/tabela_procedimentos?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def inserir_procedimento(self, codigo_tuss, descricao, valor_unitario):
        url = f"{self.supabase_url}/rest/v1/tabela_procedimentos"
        data = {
            "codigo_tuss": codigo_tuss,
            "descricao": descricao,
            "valor_unitario": valor_unitario
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    # --- Operações de Banco (Textos dos Prestadores) ---
    def carregar_textos_prestador(self):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def inserir_texto_prestador(self, titulo, glosas_relacionadas, texto, updated_by, sub_glosas_relacionadas="", procedimentos_relacionados=""):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by,
            "sub_glosas_relacionadas": sub_glosas_relacionadas,
            "procedimentos_relacionados": procedimentos_relacionados
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    def atualizar_texto_prestador(self, msg_id, titulo, glosas_relacionadas, texto, updated_by, sub_glosas_relacionadas="", procedimentos_relacionados=""):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?id=eq.{msg_id}"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by,
            "sub_glosas_relacionadas": sub_glosas_relacionadas,
            "procedimentos_relacionados": procedimentos_relacionados
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def deletar_texto_prestador(self, msg_id):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?id=eq.{msg_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Glosas Customizadas / Overrides) ---
    def carregar_glosas_customizadas(self):
        url = f"{self.supabase_url}/rest/v1/glosas_customizadas?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []
        
    def upsert_glosa_customizada(self, codigo_glosa, descricao, is_critica, tipo, updated_by):
        url = f"{self.supabase_url}/rest/v1/glosas_customizadas"
        
        # O cabeçalho 'Prefer': 'resolution=merge-duplicates' faz o POST agir como UPSERT no Supabase se houver PK conflict
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        
        data = {
            "codigo_glosa": str(codigo_glosa).strip(),
            "descricao": descricao,
            "is_critica": is_critica,
            "tipo": tipo,
            "updated_by": updated_by
        }
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]
        
    def deletar_glosa_customizada(self, glosa_id):
        url = f"{self.supabase_url}/rest/v1/glosas_customizadas?id=eq.{glosa_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]
        
    # --- Operações de Banco (Usuários / Logins Autorizados) ---
    def carregar_logins_validos(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?select=usuario_sigo"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [str(u.get('usuario_sigo', '')).strip().upper() for u in response.json() if u.get('usuario_sigo')]
        return []

    # --- Operações de Banco (Regras Gramaticais) ---
    def carregar_regras_gramaticais(self):
        url = f"{self.supabase_url}/rest/v1/regras_gramaticais?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    # --- Operações de Banco (Histórico de Glosas - Modulo 5302) ---
    def inserir_glosa_historico(self, auditor_id, codigo_glosa, paciente_nome, numero_guia, justificativa_texto, valor_glosado):
        url = f"{self.supabase_url}/rest/v1/historico_glosas"
        
        # Criptografa dados sensíveis ANTES de mandar para a internet
        paciente_nome_enc = self.criptografar(paciente_nome)
        numero_guia_enc = self.criptografar(numero_guia)

        data = {
            "auditor_id": auditor_id,
            "codigo_glosa": codigo_glosa,
            "paciente_nome_criptografado": paciente_nome_enc,
            "numero_guia_criptografado": numero_guia_enc,
            "justificativa_texto": justificativa_texto,
            "valor_glosado": valor_glosado
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    # --- Operações de Banco (Links Úteis Relacionais) ---
    def inserir_link_util(self, usuario_id, titulo, url):
        # 1. Upsert na tabela links para garantir que a URL exista de forma única
        url_links = f"{self.supabase_url}/rest/v1/links"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "return=representation, resolution=merge-duplicates"
        data_link = {"url": url}
        
        r_link = requests.post(url_links, headers=headers_upsert, json=data_link)
        if r_link.status_code not in [200, 201]:
            return False
            
        try:
            link_id = r_link.json()[0]["id"]
        except (IndexError, KeyError):
            return False
            
        # 2. Inserir a relação na tabela usuario_links
        url_usr = f"{self.supabase_url}/rest/v1/usuario_links"
        data_usr = {
            "usuario_id": usuario_id,
            "link_id": link_id,
            "titulo": titulo
        }
        # Ignora se já existir essa relação exata
        headers_usr = self.headers.copy()
        headers_usr["Prefer"] = "resolution=ignore-duplicates"
        r_usr = requests.post(url_usr, headers=headers_usr, json=data_usr)
        return r_usr.status_code in [200, 201]

    def atualizar_titulo_link_util(self, id_relacao, novo_titulo):
        url = f"{self.supabase_url}/rest/v1/usuario_links?id=eq.{id_relacao}"
        data = {"titulo": novo_titulo}
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def carregar_meus_links(self, usuario_id):
        # O PostgREST suporta Joins através de foreign keys:
        url = f"{self.supabase_url}/rest/v1/usuario_links?usuario_id=eq.{usuario_id}&select=id,titulo,link_id,links(url)"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            dados = response.json()
            resultados = []
            for d in dados:
                url_real = d.get('links', {}).get('url', '') if d.get('links') else ''
                resultados.append({
                    "id": d["id"],
                    "titulo": d["titulo"],
                    "url": url_real
                })
            return resultados
        return []

    def deletar_link_util(self, id_relacao):
        url = f"{self.supabase_url}/rest/v1/usuario_links?id=eq.{id_relacao}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    # --- Operações de Banco (Alinhamentos Internos) ---
    def carregar_alinhamentos(self, incluir_excluidos=False):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?select=*&order=created_at.desc"
        if not incluir_excluidos:
            url += "&excluido=eq.false"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_alinhamentos_excluidos(self):
        """Lista alinhamentos excluídos (soft-delete), mais recentes primeiro.
        Visível apenas na área "Excluídos" da tela de Alinhamentos (Gestor/Admin)."""
        url = f"{self.supabase_url}/rest/v1/alinhamentos?select=*&excluido=eq.true&order=excluido_em.desc"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def excluir_alinhamento_com_motivo(self, alinhamento_id, motivo, usuario_id):
        """Exclusão suave: marca como excluído com motivo obrigatório, autor e
        timestamp, mas mantém o registro (e o histórico de ciência associado)
        no banco para fins de auditoria."""
        if not str(motivo or "").strip():
            return False
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "excluido": True,
            "motivo_exclusao": motivo.strip(),
            "excluido_em": datetime.now(timezone.utc).isoformat(),
            "excluido_por": usuario_id,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in (200, 204)

    def restaurar_alinhamento(self, alinhamento_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "excluido": False,
            "motivo_exclusao": None,
            "excluido_em": None,
            "excluido_por": None,
        }
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in (200, 204)

    def carregar_alinhamentos_visiveis(self, role):
        from core.settings import NIVEL_HIERARQUIA
        nivel_usuario = NIVEL_HIERARQUIA.get(role, 1)
        niveis_visiveis = [n for n, v in NIVEL_HIERARQUIA.items() if v <= nivel_usuario]
        niveis_filtro = ",".join(niveis_visiveis)
        url = (
            f"{self.supabase_url}/rest/v1/alinhamentos"
            f"?nivel_minimo=in.({niveis_filtro})&excluido=eq.false&select=*&order=created_at.desc"
        )
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    # --- Operações de Banco (Changelog / Novidades) ---
    def carregar_changelog(self, limite=5):
        url = f"{self.supabase_url}/rest/v1/changelog?select=*&order=created_at.desc&limit={limite}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_alinhamentos_pendentes(self, usuario_id, role):
        from core.settings import NIVEL_HIERARQUIA, ROLES_CIENCIA_OBRIGATORIA
        if role not in ROLES_CIENCIA_OBRIGATORIA:
            return []

        nivel_usuario = NIVEL_HIERARQUIA.get(role, 1)
        niveis_visiveis = [n for n, v in NIVEL_HIERARQUIA.items() if v <= nivel_usuario]
        niveis_filtro = ",".join(niveis_visiveis)

        url = (
            f"{self.supabase_url}/rest/v1/alinhamentos"
            f"?nivel_minimo=in.({niveis_filtro})&excluido=eq.false&select=*&order=created_at.asc"
        )
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            return []
        todos_visiveis = response.json()
        if not todos_visiveis:
            return []

        url_lidos = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?usuario_id=eq.{usuario_id}&select=alinhamento_id"
        response_lidos = requests.get(url_lidos, headers=self.headers)
        lidos_ids = {item["alinhamento_id"] for item in response_lidos.json()} if response_lidos.status_code == 200 else set()

        url_inativacoes = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?usuario_id=eq.{usuario_id}&select=alinhamento_id"
        response_inat = requests.get(url_inativacoes, headers=self.headers)
        inativacoes_lidas_ids = {item["alinhamento_id"] for item in response_inat.json()} if response_inat.status_code == 200 else set()

        pendentes = []
        for a in todos_visiveis:
            if a.get("ativo", True):
                if a["id"] not in lidos_ids:
                    pendentes.append(a)
            else:
                if a.get("justificativa_inativacao") and a["id"] not in inativacoes_lidas_ids:
                    pendentes.append(a)

        return pendentes

    def inserir_alinhamento(self, titulo, conteudo, categoria, nivel_minimo, autor_id, anexo_url=""):
        url = f"{self.supabase_url}/rest/v1/alinhamentos"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
            "autor_id": autor_id,
            "anexo_url": anexo_url.strip() if anexo_url else None,
        }
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code not in [200, 201]:
            return False

        try:
            novo_id = response.json()[0]["id"]
            self.marcar_alinhamento_lido(novo_id, autor_id)
        except (IndexError, KeyError):
            pass
        return True

    def atualizar_alinhamento(self, alinhamento_id, titulo, conteudo, categoria, nivel_minimo, created_at=None, anexo_url=""):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
            "anexo_url": anexo_url.strip() if anexo_url else None,
        }
        if created_at:
            data["created_at"] = created_at
        response = requests.patch(url, headers=self.headers, json=data)
        return response.status_code in [200, 204]

    def toggle_ativo_alinhamento(self, alinhamento_id, ativo, justificativa=None):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {"ativo": ativo}
        if not ativo:
            data["justificativa_inativacao"] = justificativa
        else:
            data["justificativa_inativacao"] = None
            
        response = requests.patch(url, headers=self.headers, json=data)
        if response.status_code in [200, 204]:
            if ativo:
                requests.delete(f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?alinhamento_id=eq.{alinhamento_id}", headers=self.headers)
            return True
        return False

    # --- Operações de Banco (Permissões de Módulos por Role) ---
    def carregar_permissoes_modulos(self):
        # permissoes_modulos tem RLS habilitado sem nenhuma policy — só
        # service_role (que ignora RLS) consegue ler. Isso é intencional
        # (ver commit "uso de service_role para RLS"); não trocar para
        # self.headers, a chave anon simplesmente não teria acesso.
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?select=*"
        response = requests.get(url, headers=self._admin_headers())
        if response.status_code == 200:
            return response.json()
        return []

    def atualizar_permissao_modulo(self, modulo, role, habilitado):
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?on_conflict=modulo,role"
        headers_upsert = self._admin_headers()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        data = {"modulo": modulo, "role": role, "habilitado": habilitado}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def marcar_alinhamento_lido(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?on_conflict=alinhamento_id,usuario_id"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = {"alinhamento_id": alinhamento_id, "usuario_id": usuario_id}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def marcar_inativacao_lida(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas?on_conflict=alinhamento_id,usuario_id"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = {"alinhamento_id": alinhamento_id, "usuario_id": usuario_id}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def carregar_usuarios_ativos(self):
        url = f"{self.supabase_url}/rest/v1/usuarios?status=eq.Ativo&select=id,nome_completo,role_interno"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_todas_leituras(self):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?select=alinhamento_id,usuario_id,lido_em"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def remover_leitura_alinhamento(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos?alinhamento_id=eq.{alinhamento_id}&usuario_id=eq.{usuario_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]

    def excluir_alinhamento(self, alinhamento_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code in [200, 204]
