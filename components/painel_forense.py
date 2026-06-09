import time
import os
import tempfile
import threading
import customtkinter as ctk
from PIL import Image, ImageTk, ImageGrab, ImageChops, ImageEnhance, ImageOps

from core.settings import TEMA
from shared.utils import remover_arquivo_seguro, registrar_erro
from components.captura_tela import CapturaTela

class PainelImagemForense(ctk.CTkFrame):
    def __init__(self, master, titulo, on_change_callback, app_master, add_historico_callback, on_update_guia):
        super().__init__(master, fg_color="#31455C", corner_radius=10)
        self.titulo_painel = titulo
        self.on_change = on_change_callback
        self.app_master = app_master
        self.add_historico = add_historico_callback
        self.on_update_guia = on_update_guia
        self.imagem_original = None
        self.imagem_exibicao = None
        self.tk_image = None
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.start_x = 0
        self.start_y = 0

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)
        lbl_titulo = ctk.CTkLabel(header, text=titulo, font=("Segoe UI", 14, "bold"), text_color="white")
        lbl_titulo.pack(side="left")

        self.entry_guia = ctk.CTkEntry(header, placeholder_text="No da Guia...", width=110, height=28, fg_color="#1E2B3C", border_color="#34495E")
        self.entry_guia.pack(side="left", padx=(10, 0))
        
        self.entry_guia.bind("<Return>", self.notificar_guia)
        self.entry_guia.bind("<FocusOut>", self.notificar_guia)

        self.btn_limpar = ctk.CTkButton(header, text="Limpar", width=64, height=28, fg_color="#E74C3C", hover_color="#C0392B", command=self.limpar)
        self.btn_limpar.pack(side="right", padx=(5, 0))
        self.btn_colar = ctk.CTkButton(header, text="Colar", width=64, height=28, fg_color="#34495E", hover_color="#2C3E50", command=self.colar_imagem)
        self.btn_colar.pack(side="right", padx=(5, 0))
        self.btn_capturar = ctk.CTkButton(header, text="Capturar", width=90, height=28, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], font=("Segoe UI", 12, "bold"), command=self.iniciar_captura)
        self.btn_capturar.pack(side="right")

        bar_filtros = ctk.CTkFrame(self, fg_color="transparent")
        bar_filtros.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(bar_filtros, text="Filtro:", font=("Segoe UI", 11, "bold"), text_color="#D6E2F2").pack(side="left", padx=(0, 5))
        self.combo_filtros = ctk.CTkSegmentedButton(bar_filtros, values=["Normal", "Analise ELA", "Negativo"], command=self.aplicar_filtro)
        self.combo_filtros.set("Normal")
        self.combo_filtros.pack(side="left", fill="x", expand=True)

        self.canvas = ctk.CTkCanvas(self, bg="#1E2B3C", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<MouseWheel>", self.aplicar_zoom)
        self.canvas.bind("<ButtonPress-1>", self.iniciar_arraste)
        self.canvas.bind("<B1-Motion>", self.arrastar_imagem)
        self.canvas.bind("<Configure>", lambda e: self.desenhar_imagem())

    def notificar_guia(self, event=None):
        nova_guia = self.entry_guia.get().strip()
        if self.imagem_original and nova_guia:
            self.on_update_guia(self.imagem_original, nova_guia)

    def processar_nova_imagem(self, img_pil):
        try:
            self.imagem_original = img_pil.convert("RGB")
            self.zoom = 1.0
            self.offset_x = 0
            self.offset_y = 0
            self.aplicar_filtro(self.combo_filtros.get())
            guia_atual = self.entry_guia.get().strip()
            
            painel_origem = 'P1' if 'Base' in self.titulo_painel or '1' in self.titulo_painel else 'P2'
            self.add_historico(self.imagem_original, guia_atual, painel_origem=painel_origem)
            self.on_change()
        except Exception as e:
            registrar_erro("Erro ao processar imagem", e)

    def iniciar_captura(self):
        self.app_master.withdraw()
        def restaurar_e_abrir_captura():
            time.sleep(0.3)
            self.app_master.after(0, lambda: CapturaTela(self.winfo_toplevel(), self.receber_captura))
        threading.Thread(target=restaurar_e_abrir_captura, daemon=True).start()

    def receber_captura(self, img_recortada):
        self.processar_nova_imagem(img_recortada)
        self.app_master.deiconify()
        self.app_master.focus_force()

    def colar_imagem(self):
        try:
            clip = ImageGrab.grabclipboard()
            if isinstance(clip, Image.Image):
                self.processar_nova_imagem(clip)
            elif isinstance(clip, list) and len(clip) > 0:
                self.processar_nova_imagem(Image.open(clip[0]))
        except Exception as e:
            registrar_erro("Falha ao colar imagem", e)

    def carregar_do_historico(self, imagem, guia):
        self.entry_guia.delete(0, 'end')
        if guia and guia != "Pendente":
            self.entry_guia.insert(0, guia)
        self.imagem_original = imagem.copy()
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.aplicar_filtro(self.combo_filtros.get())
        self.on_change()

    def aplicar_filtro(self, nome_filtro):
        if not self.imagem_original: return
        if nome_filtro == "Normal":
            self.imagem_exibicao = self.imagem_original.copy()
        elif nome_filtro == "Analise ELA":
            fd, temp_path = tempfile.mkstemp(prefix="sia_ela_", suffix=".jpg")
            os.close(fd)
            try:
                self.imagem_original.save(temp_path, "JPEG", quality=90)
                with Image.open(temp_path) as img_comprimida:
                    diferenca = ImageChops.difference(self.imagem_original, img_comprimida.convert("RGB"))
                extrema = diferenca.getextrema()
                max_diff = max([ex[1] for ex in extrema]) if extrema else 255
                if max_diff == 0: max_diff = 1
                escala = 255.0 / max_diff
                self.imagem_exibicao = ImageEnhance.Brightness(diferenca).enhance(escala)
            finally:
                if not remover_arquivo_seguro(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as erro:
                        registrar_erro(f'Falha ao limpar temporário: {temp_path}', erro)
        elif nome_filtro == "Negativo":
            self.imagem_exibicao = ImageOps.invert(self.imagem_original.convert("RGB"))
        self.desenhar_imagem()

    def limpar(self):
        self.imagem_original = None
        self.imagem_exibicao = None
        self.tk_image = None
        self.entry_guia.delete(0, 'end')
        self.canvas.delete("all")
        self.desenhar_imagem()
        self.on_change()

    def desenhar_imagem(self):
        self.canvas.delete("all")
        if not self.imagem_exibicao:
            self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2, text="Use 'Capturar Tela' ou 'Colar'", fill="gray", font=("Segoe UI", 14))
            return
        w, h = self.imagem_exibicao.size
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        fator = min(canvas_w / w, canvas_h / h)
        new_w = int(w * fator * self.zoom)
        new_h = int(h * fator * self.zoom)
        if new_w > 0 and new_h > 0:
            resized = self.imagem_exibicao.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized)
            cx = canvas_w // 2 + self.offset_x
            cy = canvas_h // 2 + self.offset_y
            self.canvas.create_image(cx, cy, anchor="center", image=self.tk_image)

    def aplicar_zoom(self, event):
        if not self.imagem_exibicao: return
        if event.delta > 0: self.zoom *= 1.1
        else: self.zoom /= 1.1
        self.zoom = max(0.2, min(self.zoom, 8.0))
        self.desenhar_imagem()

    def iniciar_arraste(self, event):
        self.start_x = event.x
        self.start_y = event.y

    def arrastar_imagem(self, event):
        if not self.imagem_exibicao: return
        self.offset_x += (event.x - self.start_x)
        self.offset_y += (event.y - self.start_y)
        self.start_x = event.x
        self.start_y = event.y
        self.desenhar_imagem()
