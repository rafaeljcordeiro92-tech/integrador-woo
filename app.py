from flask import Flask, render_template_string, redirect
import threading
import time
from integrador_excel_woo import executar
from stats import carregar_stats

app = Flask(__name__)

HTML = """
<html>
<head>
<title>Painel ERP</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>

<body style="font-family:Arial;background:#0f172a;color:white;padding:20px">

<h1>🚀 Painel ERP Integrador</h1>

<div style="display:flex;gap:20px">

<div style="background:#1e293b;padding:15px;border-radius:10px">
<h3>📦 Updates</h3>
<h2>{{updates}}</h2>
</div>

<div style="background:#1e293b;padding:15px;border-radius:10px">
<h3>🆕 Novos</h3>
<h2>{{novos}}</h2>
</div>

<div style="background:#1e293b;padding:15px;border-radius:10px">
<h3>⚠️ Erros</h3>
<h2>{{erros}}</h2>
</div>

</div>

<br>

<form method="post" action="/rodar">
<button style="padding:10px 20px;font-size:16px">🔄 Rodar agora</button>
</form>

<br>

<canvas id="grafico"></canvas>

<script>
const data = {
labels: {{labels}},
datasets: [{
label: 'Eventos',
data: {{valores}},
borderWidth: 2
}]
};

new Chart(document.getElementById('grafico'), {
type: 'line',
data: data
});
</script>

<h3>📜 Logs</h3>
<pre style="background:black;color:#00ff00;padding:10px;height:300px;overflow:auto">
{{logs}}
</pre>

</body>
</html>
"""

# ================= LOOP =================

def loop():
    while True:
        executar()
        time.sleep(1200)

threading.Thread(target=loop, daemon=True).start()

# ================= ROTAS =================

@app.route("/")
def home():
    stats = carregar_stats()

    try:
        logs = open("log.txt").read()[-8000:]
    except:
        logs = "Sem logs"

    labels = [h["hora"] for h in stats["historico"]]
    valores = list(range(len(labels)))

    return render_template_string(
        HTML,
        updates=stats["updates"],
        novos=stats["novos"],
        erros=stats["erros"],
        logs=logs,
        labels=labels,
        valores=valores
    )

@app.route("/rodar", methods=["POST"])
def rodar():
    threading.Thread(target=executar).start()
    return redirect("/")

app.run(host="0.0.0.0", port=3000)