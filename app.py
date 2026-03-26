from flask import Flask, render_template_string
import json
import threading
import time
import os
from integrador_excel_woo import executar

app = Flask(__name__)

# ================= LOOP BACKGROUND =================

def loop():
    time.sleep(5)  # deixa o servidor subir

    while True:
        try:
            print("🚀 Rodando integrador...")
            executar()
            print("✅ Finalizado")
        except Exception as e:
            print("❌ Erro:", e)

        time.sleep(1200)

# 🔥 inicia direto (SEM before_first_request)
threading.Thread(target=loop, daemon=True).start()

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
}

.progress { background:#1e293b;border-radius:10px }
.bar { height:20px;background:#22c55e;border-radius:10px }
</style>

</head>

<body>

<h1>🚀 ERP PRO</h1>

<div class="progress">
<div class="bar" id="bar"></div>
</div>

<p id="percent">0%</p>

<div>
<div class="card">🆕 <span id="novos">0</span></div>
<div class="card">♻️ <span id="atualizados">0</span></div>
<div class="card">❌ <span id="erros">0</span></div>
</div>

<script>
function atualizar(){
fetch('/data')
.then(r => r.json())
.then(d => {
if(!d.produtos) return

document.getElementById('novos').innerText = d.novos
document.getElementById('atualizados').innerText = d.atualizados
document.getElementById('erros').innerText = d.erros

document.getElementById('bar').style.width = d.percentual + "%"
document.getElementById('percent').innerText = d.percentual + "%"
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
    return render_template_string(HTML)

@app.route("/data")
def data():
    try:
        with open("dashboard.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"produtos":[]}

# ================= START =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)