from flask import Flask, render_template_string
from datetime import datetime

app = Flask(__name__)

HTML = """
<h2>📊 Painel Integrador</h2>

<p><b>Status:</b> Online 🚀</p>
<p><b>Última atualização:</b> {{hora}}</p>

<h3>📜 Últimos logs:</h3>
<pre style="background:#111;color:#0f0;padding:10px;height:400px;overflow:auto;">
{{logs}}
</pre>
"""

@app.route("/")
def home():
    try:
        with open("log.txt", "r", encoding="utf-8") as f:
            logs = f.read()[-8000:]
    except:
        logs = "Sem logs ainda"

    return render_template_string(
        HTML,
        logs=logs,
        hora=datetime.now()
    )

app.run(host="0.0.0.0", port=3000)