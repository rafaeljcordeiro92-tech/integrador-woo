from flask import Flask, render_template_string
import json
import threading
import time
import os
from integrador_excel_woo import executar

app = Flask(__name__)

# ================= CONTROLE =================

rodando = False  # evita múltiplas execuções simultâneas

# ================= LOOP BACKGROUND =================

def loop():
    global rodando

    time.sleep(10)  # deixa o servidor subir antes

    while True:
        try:
            if not rodando:
                rodando = True
                print("🚀 Rodando integrador...")

                executar()

                print("✅ Finalizado")
                rodando = False

        except Exception as e:
            print("❌ Erro no integrador:", e)
            rodando = False

        time.sleep(1200)  # 20 minutos

def start_background():
    t = threading.Thread(target=loop, daemon=True)
    t.start()

# 🔥 inicia automaticamente (sem before_first_request)
start_background()

# ================= HTML =================

HTML = """
<html>
<head>
<title>ERP PRO</title>

<style>
body { font-family:Arial;background:#0f172a;color:white;padding:20px }

.card {
  background:#1e293b;
  padding:15px;
  border-radius:10px;
  margin:10px;
  display:inline-block;
  min-width:120px;
  text-align:center;
}

button {
  padding:10px;
  margin:5px;
  border:none;
  border-radius:5px;
  cursor:pointer;
  background:#334155;
  color:white;
}

.progress {
  background:#1e293b;
  border-radius:10px;
  margin-bottom:10px;
}

.bar {
  height:20px;
  background:#22c55e;
  border-radius:10px;
}

table {
  width:100%;
  margin-top:20px;
  border-collapse: collapse;
}

td,th {
  padding:8px;
  border-bottom:1px solid #334155;
}

.novo { color:#22c55e }
.atualizado { color:#3b82f6 }
.erro { color:#ef4444 }

.up { color:#22c55e }
.down { color:#ef4444 }

.zero { background:#7f1d1d }
</style>

</head>

<body>

<h1>🚀 ERP PRO DASHBOARD</h1>

<div class="progress">
<div class="bar" id="bar"></div>
</div>

<p id="percent">0%</p>

<div>
<div class="card">🆕 <span id="novos">0</span></div>
<div class="card">♻️ <span id="atualizados">0</span></div>
<div class="card">❌ <span id="erros">0</span></div>
</div>

<div>
<button onclick="filtrar('todos')">Todos</button>
<button onclick="filtrar('novo')">Novos</button>
<button onclick="filtrar('atualizado')">Atualizados</button>
<button onclick="filtrar('erro')">Erros</button>
</div>

<table>
<thead>
<tr>
<th>Produto</th>
<th>Preço</th>
<th>Estoque</th>
<th>Status</th>
</tr>
</thead>
<tbody id="tabela"></tbody>
</table>

<script>
let dados = []

function atualizar(){
fetch('/data')
.then(r => r.json())
.then(d => {

if(!d.produtos) return

document.getElementById('novos').innerText = d.novos || 0
document.getElementById('atualizados').innerText = d.atualizados || 0
document.getElementById('erros').innerText = d.erros || 0

document.getElementById('bar').style.width = (d.percentual || 0) + "%"
document.getElementById('percent').innerText = (d.percentual || 0) + "%"

dados = d.produtos
render("todos")
})
}

function filtrar(tipo){
render(tipo)
}

function render(tipo){
let tbody = document.getElementById("tabela")
tbody.innerHTML = ""

dados
.filter(p => tipo === "todos" || p.status === tipo)
.slice(-200)
.forEach(p => {

let preco = p.preco_novo
let precoClass = ""

if(p.preco_antigo){
if(p.preco_novo > p.preco_antigo) precoClass = "up"
if(p.preco_novo < p.preco_antigo) precoClass = "down"
preco = p.preco_antigo + " → " + p.preco_novo
}

let estoque = p.estoque_novo
let estoqueClass = ""

if(p.estoque_antigo != null && p.estoque_antigo != p.estoque_novo){
estoque = p.estoque_antigo + " → " + p.estoque_novo
}

if(p.estoque_novo == 0) estoqueClass = "zero"

tbody.innerHTML += `
<tr class="${estoqueClass}">
<td>${p.nome}</td>
<td class="${precoClass}">${preco}</td>
<td>${estoque}</td>
<td class="${p.status}">${p.status}</td>
</tr>`
})
}

setInterval(atualizar, 2000)
atualizar()
</script>

</body>
</html>
"""

# ================= ROTAS =================

@app.route("/")
def home():
    try:
        return render_template_string(HTML)
    except Exception as e:
        return f"Erro: {e}"

@app.route("/data")
def data():
    try:
        with open("dashboard.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"produtos":[]}

# 🔥 HEALTHCHECK (IMPORTANTE PRO RAILWAY)
@app.route("/health")
def health():
    return {"status": "ok"}

# ================= START =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)