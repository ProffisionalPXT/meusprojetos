import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab
import os
import time

INPUT_DIR = "input"
imagens_coladas = []

def colar_imagem(event=None):
    try:
        img = ImageGrab.grabclipboard()
        
        if img is None:
            messagebox.showwarning("Aviso", "Nenhuma imagem encontrada na área de transferência!\n\nTire um print (Windows+Shift+S ou PrintScreen) e tente colar novamente.")
            return

        imagens_coladas.append(img)
        lbl_status.config(text=f"✅ {len(imagens_coladas)} imagem(ns) na fila.\nCole mais prints ou clique em Iniciar.", fg="#00FF00")
        btn_iniciar.config(state=tk.NORMAL)
        
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao colar a imagem: {str(e)}")

def iniciar_automacao():
    if not imagens_coladas:
        messagebox.showwarning("Aviso", "Nenhuma imagem na fila para processar!")
        return
        
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR)
        
    for idx, img in enumerate(imagens_coladas):
        filename = f"coleta_lote_{int(time.time())}_{idx}.png"
        filepath = os.path.join(INPUT_DIR, filename)
        img.save(filepath, 'PNG')
        
    # Dá um tempo para garantir que o Windows terminou de gravar as imagens no HD
    time.sleep(0.5)
        
    # Sinaliza para o main.py que o lote está pronto para processamento
    with open(os.path.join(INPUT_DIR, "processar.go"), "w") as f:
        f.write("go")
        
    lbl_status.config(text=f"🚀 Lote de {len(imagens_coladas)} imagem(ns) enviado!\nO robô está trabalhando na tela de trás...", fg="#00a8ff")
    imagens_coladas.clear()
    btn_iniciar.config(state=tk.DISABLED)

# Configuração da Janela Principal
root = tk.Tk()
root.title("Robô CHEP - Painel de Entrada")
root.geometry("450x300")
root.configure(bg="#2b2b2b")
root.attributes("-topmost", True)

# Título
lbl_title = tk.Label(root, text="📥 Central de Lotes do CHEP", font=("Arial", 16, "bold"), bg="#2b2b2b", fg="#00a8ff")
lbl_title.pack(pady=15)

# Instruções
lbl_inst = tk.Label(root, text="1. Tire um print da tela (PrintScreen ou Win+Shift+S).\n2. Clique no botão verde 'Colar Imagem' abaixo.\n3. Repita o processo até ter todas as telas.\n4. Clique em INICIAR AUTOMAÇÃO.", font=("Arial", 11), bg="#2b2b2b", fg="white")
lbl_inst.pack(pady=10)

# Frame dos Botões
frame_botoes = tk.Frame(root, bg="#2b2b2b")
frame_botoes.pack(pady=10)

btn_colar = tk.Button(frame_botoes, text="Colar Imagem", font=("Arial", 12, "bold"), bg="#4CAF50", fg="white", 
                      activebackground="#45a049", activeforeground="white", relief=tk.FLAT, 
                      padx=10, pady=5, command=colar_imagem)
btn_colar.grid(row=0, column=0, padx=10)

btn_iniciar = tk.Button(frame_botoes, text="▶ INICIAR AUTOMAÇÃO", font=("Arial", 12, "bold"), bg="#ff5722", fg="white", 
                      activebackground="#e64a19", activeforeground="white", relief=tk.FLAT, 
                      padx=10, pady=5, command=iniciar_automacao, state=tk.DISABLED)
btn_iniciar.grid(row=0, column=1, padx=10)

# Status
lbl_status = tk.Label(root, text="Aguardando primeira imagem...", font=("Arial", 11, "bold"), bg="#2b2b2b", fg="gray")
lbl_status.pack(side=tk.BOTTOM, pady=15)

# Atalho global na janela
root.bind('<Control-v>', colar_imagem)

# Inicia o app
root.mainloop()
