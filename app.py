from flask import Flask, render_template_string
import threading
import time
from datetime import datetime

# IMPORTA SEU SCRIPT
from integrador_excel_woo import executar

app = Flask(__name__)

HTML = """
<h2>📊 Painel Integrador</h2>

<p>Status: Online 🚀</p>
<p>Última atualização: {{hora}}</p>

<h3>Logs:</h3>
<pre style="background:#111;color:#0f0;padding:10px;height:400px;overflow:auto;">
{{logs}}
</pre>
"""

def loop_integrador():
    while True:
        executar()
        time.sleep(1200)

@app.route("/")
def home():
    try:
        with open("log.txt", "r", encoding="utf-8") as f:
            logs = f.read()[-8000:]
    except:
        logs = "Sem logs ainda"

    return render_template_string(HTML, logs=logs, hora=datetime.now())

# THREAD DO INTEGRADOR
threading.Thread(target=loop_integrador, daemon=True).start()

app.run(host="0.0.0.0", port=3000)