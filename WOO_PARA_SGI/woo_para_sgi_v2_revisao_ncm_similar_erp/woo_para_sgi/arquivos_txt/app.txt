# -*- coding: utf-8 -*-
from flask import Flask, jsonify, send_from_directory, request
import threading

from config import RELATORIO_DIR, LIMITE_PRODUTOS_TESTE
from logger_app import ler_status, salvar_status, LOG_FILE
from main import executar
from relatorios import listar_relatorios, itens_para_revisao, ler_ultimo_relatorio, ultimo_relatorio_json
from revisao_store import salvar_decisao, listar_decisoes, listar_vinculos

app = Flask(__name__, static_folder="dashboard", static_url_path="")
_exec_thread = None


@app.route("/")
def index():
    return send_from_directory("dashboard", "index.html")


@app.route("/status")
def status():
    return jsonify(ler_status())


@app.route("/logs")
def logs():
    if not LOG_FILE.exists():
        return jsonify({"linhas": []})
    linhas = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()[-300:]
    return jsonify({"linhas": linhas})


@app.route("/relatorios")
def relatorios():
    return jsonify({"relatorios": listar_relatorios()})


@app.route("/ultimo_relatorio")
def ultimo_relatorio():
    p = ultimo_relatorio_json()
    return jsonify({
        "arquivo": p.name if p else "",
        "itens": ler_ultimo_relatorio(),
    })


@app.route("/revisao")
def revisao():
    p = ultimo_relatorio_json()
    return jsonify({
        "arquivo": p.name if p else "",
        "itens": itens_para_revisao(),
        "decisoes": listar_decisoes()[-50:],
        "vinculos": listar_vinculos(),
    })


@app.route("/decidir", methods=["POST"])
def decidir():
    payload = request.get_json(silent=True) or {}
    registro = salvar_decisao(payload)
    return jsonify({"ok": True, "decisao": registro})


@app.route("/vinculos")
def vinculos():
    return jsonify({"vinculos": listar_vinculos()})


@app.route("/baixar/<path:nome>")
def baixar(nome):
    return send_from_directory(RELATORIO_DIR, nome, as_attachment=True)


@app.route("/executar", methods=["POST", "GET"])
def executar_robo():
    global _exec_thread
    limite = int(request.args.get("limite", LIMITE_PRODUTOS_TESTE))

    if _exec_thread and _exec_thread.is_alive():
        return jsonify({"ok": False, "mensagem": "Robô já está rodando."}), 409

    def alvo():
        try:
            executar(limite=limite)
        except Exception as e:
            salvar_status({"rodando": False, "mensagem": f"Erro: {e}"})

    _exec_thread = threading.Thread(target=alvo, daemon=True)
    _exec_thread.start()
    return jsonify({"ok": True, "mensagem": f"Execução iniciada com limite={limite}."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
