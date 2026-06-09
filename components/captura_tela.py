import customtkinter as ctk
from PIL import ImageGrab, ImageTk

class CapturaTela(ctk.CTkToplevel):
    def __init__(self, master, callback_imagem):
        super().__init__(master)
        self.callback_imagem = callback_imagem
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.config(cursor="crosshair")
        self.imagem_fundo = ImageGrab.grab(all_screens=False)
        self.tk_fundo = ImageTk.PhotoImage(self.imagem_fundo)
        self.canvas = ctk.CTkCanvas(self, cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        img_escura = self.imagem_fundo.point(lambda p: p * 0.5)
        self.tk_escura = ImageTk.PhotoImage(img_escura)
        self.canvas.create_image(0, 0, image=self.tk_escura, anchor="nw")
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.canvas.bind("<ButtonPress-1>", self.ao_clicar)
        self.canvas.bind("<B1-Motion>", self.ao_arrastar)
        self.canvas.bind("<ButtonRelease-1>", self.ao_soltar)
        self.bind("<Escape>", lambda e: self.destroy())

    def ao_clicar(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#3498DB", width=2, dash=(4, 4)
        )

    def ao_arrastar(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def ao_soltar(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        if x2 - x1 > 10 and y2 - y1 > 10:
            imagem_recortada = self.imagem_fundo.crop((x1, y1, x2, y2))
            self.callback_imagem(imagem_recortada)
        self.destroy()
