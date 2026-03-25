from flask import Flask, render_template_string, redirect
import threading
import time
from integrador_excel_woo import executar
from stats import carregar_stats

app = Flask(__name__)

HTML = """... (mantém o HTML que te mandei antes) ..."""

def loop():
    while True:
        executar()
        time.sleep(1200)

threading.Thread(target=loop, daemon=True).start()

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