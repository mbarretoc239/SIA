import streamlit as st
import requests
import hashlib
from cryptography.fernet import Fernet

class DatabaseManager:
    def __init__(self):
        # Acessa os segredos do Streamlit
        self.supabase_url = st.secrets["supabase"]["url"]
        self.supabase_key = st.secrets["supabase"]["key"]
        
        # Inicializa a criptografia Fernet
        self.fernet = Fernet(st.secrets["seguranca"]["fernet_key"].encode('utf-8'))
        
        # Headers padrão para a API REST do Supabase (PostgREST)
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def _get(self, endpoint: str) -> list:
        url = f"{self.supabase_url}/rest/v1/{endpoint}"
        r = requests.get(url, headers=self.headers)
        return r.json() if r.ok else []

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
            
    def _hash_senha(self, senha: str) -> str:
        # Usa um salt estático simples embutido no código
        salt = "SIA_SALT_V5_A7B2!"
        return hashlib.sha256((senha + salt).encode('utf-8')).hexdigest()

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
        
        if response.status_code == 200:
            usuarios = response.json()
            if usuarios:
                user = usuarios[0]
                if user["senha_hash"] == self._hash_senha(senha):
                    return user # Retorna os dados do usuário se a senha bater
        return None

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
        
    def inserir_texto_prestador(self, titulo, glosas_relacionadas, texto, updated_by):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.status_code in [200, 201]

    def atualizar_texto_prestador(self, msg_id, titulo, glosas_relacionadas, texto, updated_by):
        url = f"{self.supabase_url}/rest/v1/textos_prestadores?id=eq.{msg_id}"
        data = {
            "titulo": titulo,
            "glosas_relacionadas": glosas_relacionadas,
            "texto": texto,
            "updated_by": updated_by
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
    def carregar_alinhamentos(self):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?select=*&order=created_at.desc"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def carregar_alinhamentos_visiveis(self, role):
        from core.settings import NIVEL_HIERARQUIA
        nivel_usuario = NIVEL_HIERARQUIA.get(role, 1)
        niveis_visiveis = [n for n, v in NIVEL_HIERARQUIA.items() if v <= nivel_usuario]
        niveis_filtro = ",".join(niveis_visiveis)
        url = f"{self.supabase_url}/rest/v1/alinhamentos?nivel_minimo=in.({niveis_filtro})&select=*&order=created_at.desc"
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
            f"?nivel_minimo=in.({niveis_filtro})&select=*&order=created_at.asc"
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

    def inserir_alinhamento(self, titulo, conteudo, categoria, nivel_minimo, autor_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
            "autor_id": autor_id,
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

    def atualizar_alinhamento(self, alinhamento_id, titulo, conteudo, categoria, nivel_minimo, created_at=None):
        url = f"{self.supabase_url}/rest/v1/alinhamentos?id=eq.{alinhamento_id}"
        data = {
            "titulo": titulo,
            "conteudo": conteudo,
            "categoria": categoria,
            "nivel_minimo": nivel_minimo,
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
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?select=*"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return []

    def atualizar_permissao_modulo(self, modulo, role, habilitado):
        url = f"{self.supabase_url}/rest/v1/permissoes_modulos?on_conflict=modulo,role"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        data = {"modulo": modulo, "role": role, "habilitado": habilitado}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def marcar_alinhamento_lido(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_lidos"
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=ignore-duplicates"
        data = {"alinhamento_id": alinhamento_id, "usuario_id": usuario_id}
        response = requests.post(url, headers=headers_upsert, json=data)
        return response.status_code in [200, 201]

    def marcar_inativacao_lida(self, alinhamento_id, usuario_id):
        url = f"{self.supabase_url}/rest/v1/alinhamentos_inativacoes_lidas"
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
