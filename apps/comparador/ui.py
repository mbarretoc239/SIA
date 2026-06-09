import os
import time
import io
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import customtkinter as ctk
from PIL import Image, ImageTk, ImageChops, ImageOps

from core.settings import TEMA
from core.database import conectar_sqlite
from shared.utils import remover_arquivo_seguro, registrar_erro, abrir_url_padrao
from shared.image_utils import salvar_webp as _salvar_webp, thumb as _thumb, resize_equilibrio as _resize_equilibrio, sha1_imagem as _sha1_imagem
from components.painel_forense import PainelImagemForense

# O Lazy Import de OpenCV evita travar a UI na inicializacao
cv2 = None
np = None

def _agora_str():
    return datetime.now().strftime('%d/%m/%Y %H:%M:%S')

class FrameComparadorImagens(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master
        self.historico_imagens = []
        self.ultima_origem_lens = None
        self._tokens_busca_acervo = {"P1": 0, "P2": 0}
        self._inicializar_repositorio_imagens()

        frame_esquerda = ctk.CTkFrame(self, fg_color="transparent")
        frame_esquerda.pack(side="left", fill="both", expand=True)
        self.frame_direita = ctk.CTkFrame(self, fg_color=TEMA["bg_surface"], width=220, corner_radius=0)
        self.frame_direita.pack(side="right", fill="y")
        self.frame_direita.pack_propagate(False)

        frame_top = ctk.CTkFrame(frame_esquerda, fg_color="transparent")
        frame_top.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(frame_top, text="Comparador Anti-Fraude de Imagens", font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(side="left")
        self.lbl_resultado = ctk.CTkLabel(frame_top, text="Aguardando imagens...", font=("Segoe UI", 15, "bold"), corner_radius=8, fg_color=TEMA["bg_surface_3"], padx=20, pady=8)
        self.lbl_resultado.pack(side="right")
        self.lbl_memoria = ctk.CTkLabel(frame_esquerda, text="Memoria visual local: aguardando imagem...", font=("Segoe UI", 12, "bold"), corner_radius=8, fg_color=TEMA["bg_surface_2"], text_color=TEMA["texto_secundario"], padx=14, pady=6)
        self.lbl_memoria.pack(fill="x", padx=20, pady=(0, 10))

        frame_centro = ctk.CTkFrame(frame_esquerda, fg_color="transparent")
        frame_centro.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.painel_1 = PainelImagemForense(frame_centro, "Imagem 1 (Base)", self.analisar_semelhanca, app_master, self.adicionar_ao_historico, on_update_guia=self.atualizar_guia_db)
        self.painel_1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.painel_2 = PainelImagemForense(frame_centro, "Imagem 2 (Analise)", self.analisar_semelhanca, app_master, self.adicionar_ao_historico, on_update_guia=self.atualizar_guia_db)
        self.painel_2.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ctk.CTkLabel(self.frame_direita, text="Memoria Sessao", font=("Segoe UI", 16, "bold"), text_color="white").pack(pady=(20, 5))
        ctk.CTkLabel(self.frame_direita, text="Ultimas 10 imagens", font=("Segoe UI", 12), text_color="#D6E2F2").pack(pady=(0, 15))
        self.container_historico = ctk.CTkScrollableFrame(self.frame_direita, fg_color="transparent")
        self.container_historico.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        barra_acoes = ctk.CTkFrame(self.frame_direita, fg_color="transparent")
        barra_acoes.pack(fill="x", padx=10, pady=(0, 15))
        ctk.CTkButton(barra_acoes, text="Registrar Auditoria", command=self.abrir_registro_auditoria, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(barra_acoes, text="Google Lens", command=self.abrir_google_lens_da_imagem_ativa, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(barra_acoes, text="Limpar Temporarios", command=self.limpar_temporarios, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(barra_acoes, text="Limpar Sessao Atual", command=self.limpar_sessao_comparador, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["borda_forte"], text_color=TEMA["texto_claro"]).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(barra_acoes, text="Limpar Paineis", command=self.limpar_paineis, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(fill="x", pady=(0, 8))
        
        try:
            self.app_master.bind("<Control-v>", self.atalho_colar_global, add="+")
            self.app_master.bind("<Control-V>", self.atalho_colar_global, add="+")
        except TypeError:
            self.app_master.bind("<Control-v>", self.atalho_colar_global)
            self.app_master.bind("<Control-V>", self.atalho_colar_global)

    def _lazy_import_cv(self):
        global cv2, np
        if cv2 is None:
            import cv2 as _cv2  # type: ignore
            cv2 = _cv2
        if np is None:
            import numpy as _np
            np = _np
        return cv2, np

    def _inicializar_repositorio_imagens(self):
        pasta_base = getattr(self.app_master, 'pasta_dados', str(Path.home()))
        self.pasta_imagens_forense = os.path.join(pasta_base, 'imagens_forense')
        self.pasta_thumbs = os.path.join(self.pasta_imagens_forense, 'thumbs')
        self.pasta_lens_temp = os.path.join(pasta_base, 'lens_temp')

        for pasta in (self.pasta_imagens_forense, self.pasta_thumbs, self.pasta_lens_temp):
            os.makedirs(pasta, exist_ok=True)

        self.arq_db_imagens = os.path.join(self.pasta_imagens_forense, 'memoria_imagens.sqlite3')
        self.session_id = str(datetime.now().timestamp())

        with conectar_sqlite(self.arq_db_imagens) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS imagens ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "dhash TEXT NOT NULL DEFAULT '', "
                "sha1 TEXT NOT NULL DEFAULT '', "
                "guia TEXT, "
                "origem TEXT, "
                "arquivo TEXT NOT NULL, "
                "thumbnail_arquivo TEXT, "
                "status TEXT DEFAULT 'pendente', "
                "painel_origem TEXT, "
                "session_id TEXT, "
                "observacao TEXT, "
                "data_inclusao TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS auditoria_historico ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "data_registro TEXT, "
                "login TEXT, "
                "guia TEXT, "
                "resultado TEXT, "
                "classificacao TEXT, "
                "observacao TEXT)"
            )
            colunas = {r[1] for r in conn.execute("PRAGMA table_info(imagens)").fetchall()}
            needed = {
                'thumbnail_arquivo': "ALTER TABLE imagens ADD COLUMN thumbnail_arquivo TEXT",
                'status': "ALTER TABLE imagens ADD COLUMN status TEXT DEFAULT 'pendente'",
                'painel_origem': "ALTER TABLE imagens ADD COLUMN painel_origem TEXT",
                'session_id': "ALTER TABLE imagens ADD COLUMN session_id TEXT",
                'observacao': "ALTER TABLE imagens ADD COLUMN observacao TEXT",
                'sha1': "ALTER TABLE imagens ADD COLUMN sha1 TEXT NOT NULL DEFAULT ''",
            }
            for col, ddl in needed.items():
                if col not in colunas:
                    conn.execute(ddl)
            conn.commit()

    def _gerar_dhash(self, imagem_pil, hash_size=8):
        img = ImageOps.exif_transpose(imagem_pil.convert('L'))
        img = ImageOps.autocontrast(img)
        img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(img.getdata())
        diff_bits = []
        for row in range(hash_size):
            row_start = row * (hash_size + 1)
            for col in range(hash_size):
                diff_bits.append('1' if pixels[row_start + col] > pixels[row_start + col + 1] else '0')
        return f"{int(''.join(diff_bits), 2):016x}"

    def _novo_token_busca_acervo(self, painel_origem):
        token_atual = self._tokens_busca_acervo.get(painel_origem, 0) + 1
        self._tokens_busca_acervo[painel_origem] = token_atual
        return token_atual

    def _busca_acervo_ainda_valida(self, painel_origem, token_busca, sha1_esperado=None):
        if painel_origem not in ("P1", "P2"):
            return True
        if self._tokens_busca_acervo.get(painel_origem) != token_busca:
            return False
        painel = self.painel_1 if painel_origem == "P1" else self.painel_2
        imagem_ativa = painel.imagem_original
        if imagem_ativa is None:
            return False
        if sha1_esperado:
            sha1_atual = _sha1_imagem(_resize_equilibrio(imagem_ativa, max_lado=1600))
            if sha1_atual != sha1_esperado:
                return False
        return True

    def _calcular_similaridade_transformada(self, imagem_a, imagem_b, lado=256):
        i1 = imagem_a.convert("RGB").convert("L").resize((lado, lado), Image.Resampling.LANCZOS)
        i2 = imagem_b.convert("RGB").convert("L").resize((lado, lado), Image.Resampling.LANCZOS)
        try:
            i1 = ImageOps.autocontrast(i1)
            i2 = ImageOps.autocontrast(i2)
        except Exception:
            pass

        variacoes = {
            "Normal/Editada": i2,
            "Espelhada (Lado Trocado)": i2.transpose(Image.FLIP_LEFT_RIGHT),
            "Invertida (Cima p/ Baixo)": i2.transpose(Image.FLIP_TOP_BOTTOM),
            "Rotacionada 180º": i2.rotate(180)
        }

        maior_similaridade = 0.0
        melhor_tipo = ""
        for tipo, img_var in variacoes.items():
            diff = ImageChops.difference(i1, img_var)
            soma_diff = sum(val * cnt for val, cnt in enumerate(diff.histogram()))
            similaridade = 100.0 - ((soma_diff / (255 * lado * lado)) * 100.0)
            if similaridade > maior_similaridade:
                maior_similaridade = similaridade
                melhor_tipo = tipo
        return maior_similaridade, melhor_tipo

    def atualizar_guia_db(self, imagem_pil, nova_guia):
        if not imagem_pil or not nova_guia:
            return
        img_eq = _resize_equilibrio(imagem_pil, max_lado=1600)
        sha1 = _sha1_imagem(img_eq)
        with conectar_sqlite(self.arq_db_imagens, row_factory=True) as conn:
            alvo = conn.execute(
                "SELECT * FROM imagens WHERE sha1 = ? AND session_id = ? ORDER BY id DESC LIMIT 1",
                (sha1, self.session_id)
            ).fetchone()
            if alvo is None:
                alvo = conn.execute(
                    "SELECT * FROM imagens WHERE sha1 = ? AND status = 'pendente' ORDER BY id DESC LIMIT 1",
                    (sha1,)
                ).fetchone()
            if alvo is not None:
                conn.execute("UPDATE imagens SET guia = ?, status = 'confirmada' WHERE id = ?", (nova_guia, alvo['id']))
                conn.commit()
        if alvo is None:
            self.lbl_memoria.configure(text="⚠️ Guia aplicada apenas nesta sessão. O acervo histórico foi preservado.", fg_color='#E67E22', text_color='white')
        else:
            self.lbl_memoria.configure(text=f"✅ Guia atualizada para {nova_guia} no acervo.", fg_color='#27AE60', text_color='white')
        
        for i, (img, old_guia) in enumerate(self.historico_imagens):
            if _sha1_imagem(_resize_equilibrio(img, 1600)) == sha1:
                self.historico_imagens[i] = (img, nova_guia)
        self.atualizar_ui_historico()
        
        if getattr(self.app_master, 'frame_galeria', None): self.app_master.frame_galeria.carregar_imagens()
        if getattr(self.app_master, 'frame_pendencias', None): self.app_master.frame_pendencias.carregar_imagens()

    def _persistir_imagem_otimizada(self, imagem_pil, guia, origem='manual', painel_origem='N/A'):
        if imagem_pil is None:
            return None, False
        img_eq = _resize_equilibrio(imagem_pil, max_lado=1600)
        sha1 = _sha1_imagem(img_eq)
        dhash = self._gerar_dhash(img_eq)
        guia_limpa = (guia or '').strip()
        status = 'confirmada' if guia_limpa else 'pendente'

        with conectar_sqlite(self.arq_db_imagens, row_factory=True) as conn:
            existente = conn.execute("SELECT * FROM imagens WHERE sha1 = ? ORDER BY id DESC LIMIT 1", (sha1,)).fetchone()
            if existente is not None:
                if (existente['status'] == 'pendente') and guia_limpa:
                    conn.execute(
                        "UPDATE imagens SET guia = ?, status = 'confirmada', origem = COALESCE(origem, ?), painel_origem = COALESCE(painel_origem, ?) WHERE id = ?",
                        (guia_limpa, origem, painel_origem, existente['id'])
                    )
                    conn.commit()
                    atualizado = conn.execute("SELECT * FROM imagens WHERE id = ?", (existente['id'],)).fetchone()
                    return dict(atualizado), True
                return dict(existente), True

            carimbo = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            nome_base = f'imagem_{carimbo}_{sha1[:10]}'
            arq_webp = os.path.join(self.pasta_imagens_forense, nome_base + '.webp')
            arq_thumb = os.path.join(self.pasta_thumbs, nome_base + '_thumb.webp')

            _salvar_webp(img_eq, arq_webp, quality=82)
            _salvar_webp(_thumb(img_eq, 256), arq_thumb, quality=80)

            conn.execute(
                "INSERT INTO imagens (dhash, sha1, guia, origem, arquivo, thumbnail_arquivo, status, painel_origem, session_id, data_inclusao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (dhash, sha1, guia_limpa if guia_limpa else None, origem, arq_webp, arq_thumb, status, painel_origem, self.session_id, _agora_str())
            )
            conn.commit()
            criado = conn.execute("SELECT * FROM imagens WHERE sha1 = ? ORDER BY id DESC LIMIT 1", (sha1,)).fetchone()
            return dict(criado), False

    def adicionar_ao_historico(self, imagem_pil, guia, painel_origem='N/A'):
        salvo_db, is_duplicada = self._persistir_imagem_otimizada(imagem_pil, guia, origem='clipboard_ou_captura', painel_origem=painel_origem)
        
        if is_duplicada and salvo_db:
            if salvo_db.get('session_id') == self.session_id:
                self.lbl_memoria.configure(text="🧠 Esta imagem já foi carregada nesta sessão.", fg_color='#E67E22', text_color='white')
            else:
                self.lbl_memoria.configure(text=f"🧠 Memória: imagem repetida! Vista na guia {salvo_db.get('guia') or 'N/A'}.", fg_color='#E74C3C', text_color='white')
                self._mostrar_popup_imagem_antiga(salvo_db)
        elif salvo_db:
            if salvo_db.get('status') == 'confirmada':
                self.lbl_memoria.configure(text=f"💾 Autosave: Confirmada na guia {salvo_db['guia']}. Buscando fraudes ocultas...", fg_color='#27AE60', text_color='white')
                mensagem_sucesso = f"💾 Autosave: Confirmada na guia {salvo_db['guia']}."
                cor_sucesso = '#27AE60'
                cor_texto_sucesso = 'white'
            else:
                self.lbl_memoria.configure(text='⏳ Autosave: Pendente. Buscando fraudes ocultas...', fg_color='#F39C12', text_color='black')
                mensagem_sucesso = 'Autosave: Nova imagem guardada no acervo.'
                cor_sucesso = '#27AE60'
                cor_texto_sucesso = 'white'
            novo_id = salvo_db['id'] if salvo_db else None
            img_thread = imagem_pil.copy()
            token_busca = self._novo_token_busca_acervo(painel_origem)
            sha1_esperado = salvo_db.get('sha1') if isinstance(salvo_db, dict) else None
            if hasattr(self.app_master, '_executar_em_thread'):
                self.app_master._executar_em_thread(
                    self._busca_profunda_acervo,
                    img_thread,
                    novo_id,
                    painel_origem=painel_origem,
                    token_busca=token_busca,
                    sha1_esperado=sha1_esperado,
                    mensagem_sucesso=mensagem_sucesso,
                    cor_sucesso=cor_sucesso,
                    cor_texto_sucesso=cor_texto_sucesso
                )

        encontrou = False
        for i, (img, old_guia) in enumerate(self.historico_imagens):
            if img == imagem_pil:
                self.historico_imagens[i] = (img, guia if guia else 'Pendente')
                encontrou = True
                break
        if not encontrou:
            self.historico_imagens.append((imagem_pil.copy(), guia if guia else 'Pendente'))
            if len(self.historico_imagens) > 10: self.historico_imagens.pop(0)
        self.atualizar_ui_historico()

    def _busca_profunda_acervo(self, imagem_pil, exclude_id=None, painel_origem='N/A', token_busca=None, sha1_esperado=None, mensagem_sucesso='Autosave: Nova imagem guardada no acervo.', cor_sucesso='#27AE60', cor_texto_sucesso='white'):
        cv2, np = self._lazy_import_cv()
        img_eq = _resize_equilibrio(imagem_pil, max_lado=1600)

        conn = conectar_sqlite(self.arq_db_imagens, row_factory=True)

        hashes_var = [
            self._gerar_dhash(img_eq),
            self._gerar_dhash(img_eq.transpose(Image.FLIP_LEFT_RIGHT)),
            self._gerar_dhash(img_eq.transpose(Image.FLIP_TOP_BOTTOM)),
            self._gerar_dhash(img_eq.rotate(180))
        ]
        
        query_cond = " WHERE id != ?" if exclude_id else ""
        params = (exclude_id,) if exclude_id else ()
        
        encontrado_dict = None
        tipo_match = ""

        # 1. Espelhamento Rápido
        rows = conn.execute(f"SELECT * FROM imagens{query_cond} ORDER BY id DESC LIMIT 200", params).fetchall()
        for row in rows:
            db_dhash = row['dhash']
            if db_dhash:
                for h_var in hashes_var:
                    try:
                        if bin(int(h_var, 16) ^ int(db_dhash, 16)).count('1') <= 6:
                            arquivo_referencia = row['thumbnail_arquivo'] or row['arquivo']
                            if not arquivo_referencia or not os.path.exists(arquivo_referencia):
                                continue
                            try:
                                with Image.open(arquivo_referencia) as img_ref:
                                    similaridade, tipo_detectado = self._calcular_similaridade_transformada(img_eq, img_ref)
                                if similaridade >= 92.0:
                                    encontrado_dict = dict(row)
                                    tipo_match = f"Imagem {tipo_detectado.lower()}"
                                    break
                            except Exception as erro:
                                registrar_erro('Falha ao validar hash profundo', erro)
                    except Exception as erro:
                        registrar_erro('Falha ao comparar hash profundo', erro)
            if encontrado_dict: break

        # 2. Template matching multiescala (recorte exato ou redimensionado dentro de imagem maior)
        if not encontrado_dict:
            try:
                rows = conn.execute(f"SELECT * FROM imagens{query_cond} ORDER BY id DESC LIMIT 80", params).fetchall()
                for row in rows:
                    arquivo_referencia = row['arquivo']
                    if not arquivo_referencia or not os.path.exists(arquivo_referencia):
                        continue
                    try:
                        with Image.open(arquivo_referencia) as img_ref_aberta:
                            img_ref = img_ref_aberta.convert("RGB")
                        recorte = self._detectar_recorte_template(img_eq, img_ref)
                        if recorte and recorte["score"] >= 0.86:
                            encontrado_dict = dict(row)
                            tipo_match = f"RECORTE ESCONDIDO ({recorte['score'] * 100.0:.1f}%)"
                            break
                    except Exception as erro:
                        registrar_erro('Falha ao validar recorte no acervo', erro)
            except Exception as erro:
                registrar_erro('Erro no template matching do acervo', erro)

        # 3. Features geometricas com fallback SIFT/ORB
        if not encontrado_dict:
            try:
                rows = conn.execute(f"SELECT * FROM imagens{query_cond} ORDER BY id DESC LIMIT 120", params).fetchall()
                for row in rows:
                    arquivo_referencia = row['arquivo']
                    if not arquivo_referencia or not os.path.exists(arquivo_referencia):
                        continue
                    try:
                        with Image.open(arquivo_referencia) as img_ref_aberta:
                            img_ref = img_ref_aberta.convert("RGB")
                        features = self._comparar_features_geometricas(img_eq, img_ref)
                        if features:
                            encontrado_dict = dict(row)
                            tipo_match = f"SEMELHANCA ESTRUTURAL ({features['detector']} {features['inliers']} pts)"
                            break
                    except Exception as erro:
                        registrar_erro('Falha ao validar features no acervo', erro)
            except Exception as erro:
                registrar_erro('Erro nas features do acervo', erro)

        # 4. SIFT/RANSAC legado (Cortes complexos)
        if not encontrado_dict:
            try:
                cv_img1 = cv2.cvtColor(np.array(img_eq), cv2.COLOR_RGB2GRAY)
                sift = cv2.SIFT_create()
                kp1, des1 = sift.detectAndCompute(cv_img1, None)
                
                if des1 is not None and len(des1) > 10:
                    index_params = dict(algorithm=1, trees=5)
                    search_params = dict(checks=50)
                    flann = cv2.FlannBasedMatcher(index_params, search_params)
                    
                    rows = conn.execute(f"SELECT * FROM imagens{query_cond} ORDER BY id DESC LIMIT 150", params).fetchall()
                    for row in rows:
                        if not os.path.exists(row['arquivo']): continue
                        img_db = cv2.imread(row['arquivo'], cv2.IMREAD_GRAYSCALE)
                        if img_db is None: continue
                        
                        kp2, des2 = sift.detectAndCompute(img_db, None)
                        if des2 is not None and len(des2) > 10:
                            matches = flann.knnMatch(des1, des2, k=2)
                            good = [m for match_set in matches if len(match_set) == 2 for m, n in [match_set] if m.distance < 0.75 * n.distance]
                            if len(good) >= 12:
                                src_pts = np.float32([ kp1[m.queryIdx].pt for m in good ]).reshape(-1,1,2)
                                dst_pts = np.float32([ kp2[m.trainIdx].pt for m in good ]).reshape(-1,1,2)
                                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                                if mask is not None and int(np.sum(mask)) >= 10:
                                    encontrado_dict = dict(row)
                                    tipo_match = "RECORTE ESCONDIDO"
                                    break
            except Exception as e:
                registrar_erro("Erro na busca profunda do acervo", e)

        conn.close()

        if not self._busca_acervo_ainda_valida(painel_origem, token_busca, sha1_esperado):
            return

        if (
            encontrado_dict
            and sha1_esperado
            and encontrado_dict.get('sha1') == sha1_esperado
            and encontrado_dict.get('session_id') == self.session_id
        ):
            encontrado_dict = None

        if encontrado_dict:
            msg = f"Atencao: {tipo_match} no acervo. Vista na guia {encontrado_dict.get('guia') or 'N/A'}."
            self.app_master.after(0, lambda: self.lbl_memoria.configure(text=msg, fg_color='#E74C3C', text_color='white'))
            self.app_master.after(0, lambda: self._mostrar_popup_imagem_antiga(encontrado_dict))
        else:
            self.app_master.after(0, lambda: self.lbl_memoria.configure(text=mensagem_sucesso, fg_color=cor_sucesso, text_color=cor_texto_sucesso))

    def _mostrar_popup_imagem_antiga(self, encontrado):
        popup = ctk.CTkToplevel(self.app_master)
        popup.title("Alerta: Imagem Já Auditada!")
        popup.geometry("450x550")
        popup.attributes('-topmost', True)
        
        ctk.CTkLabel(popup, text="Possível Repetição Detectada", font=("Segoe UI", 18, "bold"), text_color="#E74C3C").pack(pady=(20, 5))
        ctk.CTkLabel(popup, text=f"Vista na Guia: {encontrado['guia'] or 'N/A'}\nData de inclusão: {encontrado['data_inclusao']}", font=("Segoe UI", 12)).pack(pady=5)

        try:
            img = Image.open(encontrado['thumbnail_arquivo'] or encontrado['arquivo'])
            img.thumbnail((250, 250))
            tk_img = ImageTk.PhotoImage(img)
            lbl_img = ctk.CTkLabel(popup, image=tk_img, text="")
            lbl_img.image = tk_img
            lbl_img.pack(pady=15)
        except Exception:
            ctk.CTkLabel(popup, text="Erro ao carregar miniatura.").pack()
            
        ctk.CTkButton(popup, text="Fechar", fg_color="#34495E", hover_color="#1E2B3C", command=popup.destroy).pack(pady=10)
        if hasattr(self.app_master, '_tematizar_popup'):
            self.app_master._tematizar_popup(popup)

    def abrir_registro_auditoria(self):
        popup = ctk.CTkToplevel(self.app_master)
        popup.title("Registrar Auditoria")
        popup.geometry("400x500")
        popup.attributes('-topmost', True)
        
        ctk.CTkLabel(popup, text="Classificação Final", font=("Segoe UI", 14, "bold")).pack(pady=(10, 5))
        combo_classificacao = ctk.CTkComboBox(popup, values=["Suspeita Confirmada", "Sem Indício", "Revisar Depois", "Duplicidade Administrativa", "Imagem Sem Contexto"], width=300)
        combo_classificacao.pack(pady=5)
        
        ctk.CTkLabel(popup, text="Guia Referência", font=("Segoe UI", 14, "bold")).pack(pady=(10, 5))
        entry_guia_aud = ctk.CTkEntry(popup, width=300)
        entry_guia_aud.pack(pady=5)
        
        guia_sugerida = self.painel_1.entry_guia.get() or self.painel_2.entry_guia.get()
        if guia_sugerida: entry_guia_aud.insert(0, guia_sugerida)

        ctk.CTkLabel(popup, text="Observação", font=("Segoe UI", 14, "bold")).pack(pady=(10, 5))
        text_obs = ctk.CTkTextbox(popup, height=100, width=300)
        text_obs.pack(pady=5)
        
        def salvar():
            with conectar_sqlite(self.arq_db_imagens) as conn:
                conn.execute(
                    "INSERT INTO auditoria_historico (data_registro, login, guia, resultado, classificacao, observacao) VALUES (?, ?, ?, ?, ?, ?)",
                    (_agora_str(), getattr(self.app_master, 'login_auditor', 'N/A'), entry_guia_aud.get().strip(), self.lbl_resultado.cget("text"), combo_classificacao.get(), text_obs.get("0.0", "end").strip())
                )
                conn.commit()
            popup.destroy()
            self.lbl_memoria.configure(text="✅ Auditoria registrada no histórico local com sucesso.", fg_color="#27AE60", text_color="white")

        ctk.CTkButton(popup, text="Salvar Registro", command=salvar, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]).pack(pady=20)
        if hasattr(self.app_master, '_tematizar_popup'):
            self.app_master._tematizar_popup(popup)

    def limpar_sessao_comparador(self):
        removidos = 0
        try:
            with conectar_sqlite(self.arq_db_imagens, row_factory=True) as conn:
                rows = conn.execute(
                    "SELECT id, arquivo, thumbnail_arquivo FROM imagens WHERE session_id = ?",
                    (self.session_id,)
                ).fetchall()
                for row in rows:
                    for campo in ('arquivo', 'thumbnail_arquivo'):
                        caminho = row[campo]
                        if caminho:
                            remover_arquivo_seguro(caminho)
                conn.execute("DELETE FROM imagens WHERE session_id = ?", (self.session_id,))
                conn.commit()
                removidos = len(rows)
        except Exception as erro:
            registrar_erro("Falha ao limpar sessão do comparador", erro)

        self.session_id = str(datetime.now().timestamp())
        self.historico_imagens.clear()
        self.atualizar_ui_historico()
        self.limpar_paineis()
        self.lbl_memoria.configure(text=f"Sessão atual limpa ({removidos} registro(s)). O acervo histórico foi preservado.", fg_color='#22313F', text_color='#BDC3C7')
        if getattr(self.app_master, 'frame_galeria', None): self.app_master.frame_galeria.carregar_imagens()
        if getattr(self.app_master, 'frame_pendencias', None): self.app_master.frame_pendencias.carregar_imagens()

    def limpar_temporarios(self, dias=7):
        limite = datetime.now() - timedelta(days=dias)
        removidos = 0
        for nome in os.listdir(self.pasta_lens_temp):
            arq = os.path.join(self.pasta_lens_temp, nome)
            try:
                if datetime.fromtimestamp(os.path.getmtime(arq)) < limite:
                    if remover_arquivo_seguro(arq):
                        removidos += 1
            except Exception as erro:
                registrar_erro(f'Falha ao limpar temporário: {arq}', erro)
        self.lbl_memoria.configure(text=f'🧹 Temporários limpos: {removidos} arquivo(s).', fg_color='#145A32', text_color='white')

    def _copiar_imagem_para_clipboard_windows(self, imagem_pil):
        try:
            import win32clipboard  # type: ignore
            output = io.BytesIO()
            imagem_pil.convert('RGB').save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            for _ in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    break
                except Exception:
                    time.sleep(0.08)
            else:
                return False
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
            return True
        except Exception as erro:
            registrar_erro("Falha ao copiar imagem para a área de transferência", erro)
            return False

    def abrir_google_lens_da_imagem(self, imagem_pil, origem='Painel'):
        url = 'https://www.google.com/imghp?hl=pt-BR'
        if imagem_pil is None:
            self.lbl_memoria.configure(text='🔎 Google Lens aberto. Envie o arquivo no navegador.', fg_color='#1F618D', text_color='white')
            abrir_url_padrao(url)
            return

        self.ultima_origem_lens = origem
        carimbo = datetime.now().strftime('%Y%m%d_%H%M%S')
        arquivo_temp = os.path.join(self.pasta_lens_temp, f'google_img_{origem.replace(" ", "_").lower()}_{carimbo}.webp')
        _salvar_webp(_resize_equilibrio(imagem_pil, 1600), arquivo_temp, quality=82)
        
        copiado = self._copiar_imagem_para_clipboard_windows(imagem_pil)
        abrir_url_padrao(url)
        
        if copiado:
            self.lbl_memoria.configure(text=f'🔎 Imagem copiada para Ctrl+V no Google. Arquivo reserva: {arquivo_temp}', fg_color='#1F618D', text_color='white')
        else:
            self.lbl_memoria.configure(text=f'🔎 Imagem salva para envio no Google em: {arquivo_temp}', fg_color='#1F618D', text_color='white')

    def abrir_google_lens_da_imagem_ativa(self):
        imagem = self.painel_2.imagem_original or self.painel_1.imagem_original
        origem = 'Painel 2' if self.painel_2.imagem_original else ('Painel 1' if self.painel_1.imagem_original else 'App')
        self.abrir_google_lens_da_imagem(imagem, origem)

    def limpar_paineis(self):
        self._novo_token_busca_acervo("P1")
        self._novo_token_busca_acervo("P2")
        self.painel_1.limpar()
        self.painel_2.limpar()
        self.lbl_resultado.configure(text="Aguardando imagens...", fg_color="#34495E", text_color="white")

    def atualizar_ui_historico(self):
        for widget in self.container_historico.winfo_children(): widget.destroy()
        for img, guia in reversed(self.historico_imagens):
            frame_item = ctk.CTkFrame(self.container_historico, fg_color="#31455C", corner_radius=8)
            frame_item.pack(fill="x", pady=5, padx=2)
            thumb = img.copy()
            thumb.thumbnail((120, 120))
            tk_thumb = ImageTk.PhotoImage(thumb)
            lbl_img = ctk.CTkLabel(frame_item, image=tk_thumb, text="")
            lbl_img.image = tk_thumb
            lbl_img.pack(pady=(10, 5))
            guia_texto = guia if len(guia) <= 15 else guia[:12] + ".."
            ctk.CTkLabel(frame_item, text=guia_texto, font=("Segoe UI", 11, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(0, 5))
            btn_frame = ctk.CTkFrame(frame_item, fg_color="transparent")
            btn_frame.pack(pady=(0, 10))
            ctk.CTkButton(btn_frame, text="Ao P1", width=55, height=28, fg_color="#34495E", hover_color="#1E2B3C", command=lambda img_copy=img, guia_copy=guia: self.resgatar_historico("P1", img_copy, guia_copy)).pack(side="left", padx=3)
            ctk.CTkButton(btn_frame, text="Ao P2", width=55, height=28, fg_color="#34495E", hover_color="#1E2B3C", command=lambda img_copy=img, guia_copy=guia: self.resgatar_historico("P2", img_copy, guia_copy)).pack(side="left", padx=3)

    def resgatar_historico(self, painel_alvo, imagem, guia):
        if painel_alvo == "P1": self.painel_1.carregar_do_historico(imagem, guia)
        else: self.painel_2.carregar_do_historico(imagem, guia)

    def _preparar_gray_forense(self, imagem_pil, max_lado=1300):
        cv2, np = self._lazy_import_cv()
        img = ImageOps.exif_transpose(imagem_pil.convert("RGB"))
        w, h = img.size
        maior = max(w, h)
        if maior > max_lado:
            fator = max_lado / float(maior)
            img = img.resize((max(1, int(w * fator)), max(1, int(h * fator))), Image.Resampling.LANCZOS)
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        try:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        except Exception:
            pass
        return gray

    def _variacoes_gray_forense(self, gray):
        cv2, _ = self._lazy_import_cv()
        return {
            "Normal/Editada": gray,
            "Espelhada (Lado Trocado)": cv2.flip(gray, 1),
            "Invertida (Cima p/ Baixo)": cv2.flip(gray, 0),
            "Rotacionada 180": cv2.flip(gray, -1),
        }

    def _distancia_dhash_minima(self, img1, img2):
        try:
            base_hash = self._gerar_dhash(_resize_equilibrio(img1, max_lado=1600))
            img2_eq = _resize_equilibrio(img2, max_lado=1600)
            variacoes = {
                "Normal/Editada": img2_eq,
                "Espelhada (Lado Trocado)": img2_eq.transpose(Image.FLIP_LEFT_RIGHT),
                "Invertida (Cima p/ Baixo)": img2_eq.transpose(Image.FLIP_TOP_BOTTOM),
                "Rotacionada 180": img2_eq.rotate(180),
            }
            menor_distancia = 65
            melhor_tipo = ""
            for tipo, imagem in variacoes.items():
                h_var = self._gerar_dhash(imagem)
                distancia = bin(int(base_hash, 16) ^ int(h_var, 16)).count("1")
                if distancia < menor_distancia:
                    menor_distancia = distancia
                    melhor_tipo = tipo
            return menor_distancia, melhor_tipo
        except Exception as erro:
            registrar_erro("Falha ao calcular dHash perceptual", erro)
            return 65, ""

    def _detectar_recorte_template(self, img1, img2):
        cv2, np = self._lazy_import_cv()
        img1_rgb = ImageOps.exif_transpose(img1.convert("RGB"))
        img2_rgb = ImageOps.exif_transpose(img2.convert("RGB"))
        max_lado = 1300
        base_scales = [
            0.18, 0.22, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70,
            0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20, 1.35, 1.50,
            1.75, 2.00, 2.40, 2.80, 3.20,
        ]

        def _fator_resize(imagem):
            maior = max(imagem.size)
            return 1.0 if maior <= max_lado else max_lado / float(maior)

        def _avaliar(search_img, template_img, origem):
            area_search = search_img.size[0] * search_img.size[1]
            area_template = template_img.size[0] * template_img.size[1]
            if area_template > area_search * 16:
                return None
            if min(template_img.size) < 35 or min(search_img.size) < 45:
                return None

            search_gray = self._preparar_gray_forense(search_img, max_lado=max_lado)
            template_gray = self._preparar_gray_forense(template_img, max_lado=max_lado)
            if min(template_gray.shape[:2]) < 25:
                return None

            textura = float(np.std(template_gray))
            if textura < 4.5:
                return None

            escala_hint = _fator_resize(search_img) / max(_fator_resize(template_img), 0.0001)
            escalas = set(base_scales)
            for mult in (0.70, 0.80, 0.90, 0.96, 1.00, 1.04, 1.10, 1.20, 1.35):
                escala = escala_hint * mult
                if 0.12 <= escala <= 3.50:
                    escalas.add(round(escala, 3))
            escalas = sorted(escalas)

            try:
                search_edges = cv2.Canny(search_gray, 50, 150)
            except Exception:
                search_edges = None

            melhor = None
            h_search, w_search = search_gray.shape[:2]
            for orientacao, template_var in self._variacoes_gray_forense(template_gray).items():
                h_template, w_template = template_var.shape[:2]
                for escala in escalas:
                    novo_w = int(w_template * escala)
                    novo_h = int(h_template * escala)
                    if novo_w < 25 or novo_h < 25:
                        continue
                    if novo_w > w_search or novo_h > h_search:
                        continue
                    interp = cv2.INTER_AREA if escala < 1 else cv2.INTER_CUBIC
                    template_resized = cv2.resize(template_var, (novo_w, novo_h), interpolation=interp)
                    if float(np.std(template_resized)) < 3.5:
                        continue

                    try:
                        mapa = cv2.matchTemplate(search_gray, template_resized, cv2.TM_CCOEFF_NORMED)
                        _, score, _, loc = cv2.minMaxLoc(mapa)
                        score = float(score)
                    except Exception:
                        continue
                    if not np.isfinite(score):
                        continue

                    edge_score = 0.0
                    score_final = score
                    if search_edges is not None:
                        try:
                            template_edges = cv2.Canny(template_resized, 50, 150)
                            densidade_borda = float(np.mean(template_edges > 0))
                            if densidade_borda >= 0.012:
                                mapa_edge = cv2.matchTemplate(search_edges, template_edges, cv2.TM_CCOEFF_NORMED)
                                _, edge_score, _, _ = cv2.minMaxLoc(mapa_edge)
                                edge_score = float(edge_score)
                                if np.isfinite(edge_score):
                                    score_final = (score * 0.85) + (max(edge_score, 0.0) * 0.15)
                        except Exception:
                            edge_score = 0.0

                    if melhor is None or score_final > melhor["score"]:
                        melhor = {
                            "score": score_final,
                            "score_template": score,
                            "score_borda": edge_score,
                            "escala": escala,
                            "orientacao": orientacao,
                            "origem": origem,
                            "posicao": loc,
                            "textura": textura,
                        }
            return melhor

        candidatos = [
            _avaliar(img1_rgb, img2_rgb, "Imagem 2 encontrada dentro da Imagem 1"),
            _avaliar(img2_rgb, img1_rgb, "Imagem 1 encontrada dentro da Imagem 2"),
        ]
        candidatos = [c for c in candidatos if c]
        if not candidatos:
            return None
        melhor = max(candidatos, key=lambda item: item["score"])
        if melhor["score"] >= 0.86:
            return melhor
        if melhor["score"] >= 0.80 and melhor["textura"] >= 14.0 and melhor["score_borda"] >= 0.25:
            return melhor
        return None

    def _comparar_features_geometricas(self, img1, img2):
        cv2, np = self._lazy_import_cv()
        gray1 = self._preparar_gray_forense(img1, max_lado=1400)
        gray2 = self._preparar_gray_forense(img2, max_lado=1400)

        detector = None
        nome_detector = ""
        norma = None
        ratio = 0.75
        try:
            if hasattr(cv2, "SIFT_create"):
                detector = cv2.SIFT_create(nfeatures=2500)
                nome_detector = "SIFT"
                norma = cv2.NORM_L2
                ratio = 0.74
        except Exception:
            detector = None
        if detector is None:
            try:
                detector = cv2.ORB_create(nfeatures=3500, scaleFactor=1.2, nlevels=8)
                nome_detector = "ORB"
                norma = cv2.NORM_HAMMING
                ratio = 0.78
            except Exception:
                return None

        kp1, des1 = detector.detectAndCompute(gray1, None)
        if des1 is None or kp1 is None or len(kp1) < 8:
            return None

        matcher = cv2.BFMatcher(norma)
        melhor = None
        for orientacao, gray2_var in self._variacoes_gray_forense(gray2).items():
            kp2, des2 = detector.detectAndCompute(gray2_var, None)
            if des2 is None or kp2 is None or len(kp2) < 8:
                continue
            try:
                matches = matcher.knnMatch(des1, des2, k=2)
            except Exception:
                continue
            bons = []
            for match_set in matches:
                if len(match_set) != 2:
                    continue
                m, n = match_set
                if m.distance < ratio * n.distance:
                    bons.append(m)

            if len(bons) < 6:
                continue
            try:
                src_pts = np.float32([kp1[m.queryIdx].pt for m in bons]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp2[m.trainIdx].pt for m in bons]).reshape(-1, 1, 2)
                _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            except Exception:
                continue
            if mask is None:
                continue
            inliers = int(np.sum(mask))
            inlier_ratio = inliers / max(len(bons), 1)
            if melhor is None or (inliers, inlier_ratio) > (melhor["inliers"], melhor["inlier_ratio"]):
                melhor = {
                    "detector": nome_detector,
                    "orientacao": orientacao,
                    "inliers": inliers,
                    "matches": len(bons),
                    "inlier_ratio": inlier_ratio,
                }

        if melhor and (melhor["inliers"] >= 16 or (melhor["inliers"] >= 9 and melhor["inlier_ratio"] >= 0.42)):
            return melhor
        return None

    def _calcular_score_ela(self, imagem_pil):
        cv2, np = self._lazy_import_cv()
        temp_path = None
        try:
            img = _resize_equilibrio(ImageOps.exif_transpose(imagem_pil.convert("RGB")), max_lado=900)
            fd, temp_path = tempfile.mkstemp(prefix="sia_ela_score_", suffix=".jpg")
            os.close(fd)
            img.save(temp_path, "JPEG", quality=90)
            with Image.open(temp_path) as img_jpeg:
                diff = ImageChops.difference(img, img_jpeg.convert("RGB"))
            arr = np.array(diff.convert("L"), dtype=np.float32)
            media = float(np.mean(arr))
            p95 = float(np.percentile(arr, 95))
            p99 = float(np.percentile(arr, 99))
            score = min(100.0, ((p99 * 0.50) + (p95 * 0.35) + (media * 0.15)) * 1.7)
            return {"score": score, "media": media, "p95": p95, "p99": p99}
        except Exception as erro:
            registrar_erro("Falha ao calcular score ELA", erro)
            return {"score": 0.0, "media": 0.0, "p95": 0.0, "p99": 0.0}
        finally:
            if temp_path and not remover_arquivo_seguro(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _analisar_semelhanca_forense(self):
        img1 = self.painel_1.imagem_original
        img2 = self.painel_2.imagem_original
        if not img1 or not img2:
            self.lbl_resultado.configure(text="Insira as duas imagens para comparar", fg_color="#34495E", text_color="white")
            return True

        try:
            texto_alerta = "OK: imagens diferentes"
            cor_fundo = "#27AE60"
            nivel_fraude = 0

            sha1_img1 = _sha1_imagem(_resize_equilibrio(img1, max_lado=1600))
            sha1_img2 = _sha1_imagem(_resize_equilibrio(img2, max_lado=1600))
            if sha1_img1 == sha1_img2:
                texto_alerta = "ALERTA: imagens identicas"
                cor_fundo = "#E74C3C"
                nivel_fraude = 3

            if nivel_fraude < 3:
                distancia_hash, tipo_hash = self._distancia_dhash_minima(img1, img2)
                if distancia_hash <= 2:
                    texto_alerta = f"ALERTA: imagens praticamente identicas ({tipo_hash}, dHash {distancia_hash})"
                    cor_fundo = "#E74C3C"
                    nivel_fraude = 3
                elif distancia_hash <= 6:
                    texto_alerta = f"ALTO RISCO: imagens muito semelhantes ({tipo_hash}, dHash {distancia_hash})"
                    cor_fundo = "#E67E22"
                    nivel_fraude = 2

            if nivel_fraude < 3:
                recorte = self._detectar_recorte_template(img1, img2)
                if recorte:
                    score_pct = recorte["score"] * 100.0
                    if recorte["score"] >= 0.90:
                        texto_alerta = f"ALERTA: recorte localizado. {recorte['origem']} ({score_pct:.1f}%)"
                        cor_fundo = "#E74C3C"
                        nivel_fraude = 3
                    elif nivel_fraude < 2:
                        texto_alerta = f"ALTO RISCO: possivel recorte localizado. {recorte['origem']} ({score_pct:.1f}%)"
                        cor_fundo = "#E67E22"
                        nivel_fraude = 2

            if nivel_fraude < 3:
                features = self._comparar_features_geometricas(img1, img2)
                if features:
                    detalhe = f"{features['detector']} {features['inliers']}/{features['matches']} pts"
                    if features["inliers"] >= 18 or features["inlier_ratio"] >= 0.55:
                        texto_alerta = f"ALERTA: mesma estrutura visual detectada ({features['orientacao']}, {detalhe})"
                        cor_fundo = "#E74C3C"
                        nivel_fraude = 3
                    elif nivel_fraude < 2:
                        texto_alerta = f"ALTO RISCO: semelhanca estrutural detectada ({features['orientacao']}, {detalhe})"
                        cor_fundo = "#E67E22"
                        nivel_fraude = 2

            if nivel_fraude < 3:
                maior_similaridade, tipo_fraude = self._calcular_similaridade_transformada(img1, img2)
                if maior_similaridade >= 95.0:
                    texto_alerta = f"ALERTA: imagem {tipo_fraude.upper()} ({maior_similaridade:.1f}%)"
                    cor_fundo = "#E74C3C"
                    nivel_fraude = 3
                elif maior_similaridade >= 89.0 and nivel_fraude < 2:
                    texto_alerta = f"ALTO RISCO: imagem {tipo_fraude.upper()} ({maior_similaridade:.1f}%)"
                    cor_fundo = "#E67E22"
                    nivel_fraude = 2
                elif maior_similaridade >= 85.0 and nivel_fraude < 1:
                    texto_alerta = f"REVISAR: estruturas parecidas ({maior_similaridade:.1f}%)"
                    cor_fundo = "#F1C40F"
                    nivel_fraude = 1

            if nivel_fraude == 0:
                ela1 = self._calcular_score_ela(img1)
                ela2 = self._calcular_score_ela(img2)
                score_ela = max(ela1["score"], ela2["score"])
                if score_ela >= 68.0:
                    texto_alerta = f"REVISAR: possiveis sinais de edicao digital por ELA ({score_ela:.0f}/100)"
                    cor_fundo = "#F1C40F"
                    nivel_fraude = 1

            cor_texto = "black" if cor_fundo == "#F1C40F" else "white"
            self.lbl_resultado.configure(text=texto_alerta, fg_color=cor_fundo, text_color=cor_texto)
            return True
        except Exception as erro:
            registrar_erro("Erro no analisador forense reforcado", erro)
            return False

    def analisar_semelhanca(self):
        if self._analisar_semelhanca_forense():
            return
        cv2, np = self._lazy_import_cv()
        img1 = self.painel_1.imagem_original
        img2 = self.painel_2.imagem_original
        if not img1 or not img2:
            self.lbl_resultado.configure(text="Insira as duas imagens para comparar", fg_color="#34495E", text_color="white")
            return
        try:
            texto_alerta = "✅ Imagens Diferentes"
            cor_fundo = "#27AE60"
            nivel_fraude = 0
            
            # --- 1. SIFT AVANÇADO COM RANSAC (Mapeamento Geométrico) ---
            cv_img1 = cv2.cvtColor(np.array(img1.convert('RGB')), cv2.COLOR_RGB2GRAY)
            cv_img2_base = cv2.cvtColor(np.array(img2.convert('RGB')), cv2.COLOR_RGB2GRAY)
            
            sift = cv2.SIFT_create()
            kp1, des1 = sift.detectAndCompute(cv_img1, None)
            
            melhor_inliers = 0
            melhor_tipo_sift = ""
            
            variacoes_cv = {
                "Normal/Editada": cv_img2_base,
                "Espelhada (Lado Trocado)": cv2.flip(cv_img2_base, 1),
                "Invertida (Cima p/ Baixo)": cv2.flip(cv_img2_base, 0),
                "Rotacionada 180º": cv2.flip(cv_img2_base, -1)
            }
            
            if des1 is not None and len(des1) > 10:
                index_params = dict(algorithm=1, trees=5)
                search_params = dict(checks=50)
                flann = cv2.FlannBasedMatcher(index_params, search_params)
                
                for tipo, cv_var in variacoes_cv.items():
                    kp2, des2 = sift.detectAndCompute(cv_var, None)
                    if des2 is not None and len(des2) > 10:
                        matches = flann.knnMatch(des1, des2, k=2)
                        good = []
                        for match_set in matches:
                            if len(match_set) == 2:
                                m, n = match_set
                                if m.distance < 0.75 * n.distance:
                                    good.append(m)
                        
                        # Filtro RANSAC
                        if len(good) >= 10:
                            src_pts = np.float32([ kp1[m.queryIdx].pt for m in good ]).reshape(-1,1,2)
                            dst_pts = np.float32([ kp2[m.trainIdx].pt for m in good ]).reshape(-1,1,2)
                            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                            if mask is not None:
                                inliers = int(np.sum(mask))
                                if inliers > melhor_inliers:
                                    melhor_inliers = inliers
                                    melhor_tipo_sift = tipo
                                
            # Avalia resultado do SIFT (Mínimo de 12 inliers para ser fraude)
            if melhor_inliers >= 12:
                if melhor_tipo_sift == "Normal/Editada":
                    texto_alerta = f"🚨 SUSPEITA DE FRAUDE: Imagem RECORTADA! ({melhor_inliers} pts de colisão)"
                else:
                    texto_alerta = f"🚨 SUSPEITA DE FRAUDE: {melhor_tipo_sift.upper()} COM RECORTES"
                cor_fundo = "#E74C3C"
                nivel_fraude = 3

            # --- 2. COMPARAÇÃO POR PIXEL (CASO NÃO TENHA RECORTE) ---
            if nivel_fraude < 3:
                i1 = img1.convert("RGB").convert("L").resize((256, 256))
                i2 = img2.convert("RGB").convert("L").resize((256, 256))
                try:
                    i1 = ImageOps.autocontrast(i1)
                    i2 = ImageOps.autocontrast(i2)
                except Exception: pass
                
                variacoes_pil = {
                    "Normal/Editada": i2,
                    "Espelhada (Lado Trocado)": i2.transpose(Image.FLIP_LEFT_RIGHT),
                    "Invertida (Cima p/ Baixo)": i2.transpose(Image.FLIP_TOP_BOTTOM),
                    "Rotacionada 180º": i2.rotate(180)
                }
                
                maior_similaridade = 0
                tipo_fraude = ""
                for tipo, img_var in variacoes_pil.items():
                    diff = ImageChops.difference(i1, img_var)
                    soma_diff = sum(val * cnt for val, cnt in enumerate(diff.histogram()))
                    similaridade = 100.0 - ((soma_diff / (255 * 256 * 256)) * 100.0)
                    if similaridade > maior_similaridade:
                        maior_similaridade = similaridade
                        tipo_fraude = tipo
                
                if maior_similaridade >= 95.0:
                    texto_alerta = f"🚨 SUSPEITA DE FRAUDE: Imagem {tipo_fraude.upper()}!"
                    cor_fundo = "#E74C3C"
                    nivel_fraude = 3
                elif maior_similaridade >= 89.0 and nivel_fraude < 2:
                    texto_alerta = f"⚠️ ALTO RISCO: Imagem {tipo_fraude.upper()} detectada ({maior_similaridade:.1f}%)"
                    cor_fundo = "#E67E22"
                    nivel_fraude = 2
                elif maior_similaridade >= 85.0 and nivel_fraude < 1:
                    texto_alerta = f"👀 SUSPEITO: Estruturas parecidas ({maior_similaridade:.1f}%)"
                    cor_fundo = "#F1C40F"
                    nivel_fraude = 1
            
            cor_texto = "black" if cor_fundo == "#F1C40F" else "white"
            self.lbl_resultado.configure(text=texto_alerta, fg_color=cor_fundo, text_color=cor_texto)
        except Exception as e:
            registrar_erro("Erro ao analisar imagens", e)
            self.lbl_resultado.configure(text="Erro ao analisar imagens.", fg_color="#E74C3C", text_color="white")

    def atalho_colar_global(self, event=None):
        try:
            if not self.winfo_exists() or not self.winfo_ismapped(): return
        except Exception: return
        if not self.painel_1.imagem_original: self.painel_1.colar_imagem()
        else: self.painel_2.colar_imagem()
