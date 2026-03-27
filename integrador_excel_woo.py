import requests
import threading
import os
import time
from datetime import datetime
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

# ================= CONFIG =================

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
BUSCA_URL = BASE + "/produto/getPorCodigoNome/%20/2/272"

EMPRESA = 272
USUARIO = "00905486986"
SENHA = "Rafael2026@"

URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

# ================= MAPAS =================

MAPA_DEPARTAMENTOS = {
    1010000000: "ELETRO",
    1020000000: "MÓVEIS",
    1050000000: "ESPORTE E LAZER",
    1030000000: "INFORMÁTICA",
    1040000000: "TELEF. CELULAR",
    1060000000: "UTILIDADES",
    1080000000: "CAMA, MESA E BANHO",
    1090000000: "TAPETES",
    1150000000: "LINHA AUTOMOTIVA",
    1180000000: "LINHA ALTA",
    1190000000: "COLCHÕES",
    1170000000: "DECORAÇÃO"
}

MAPA_SUBDEPARTAMENTOS = {
    1012090000: "ADEGAS", 1013050000: "AQUECIMENTO", 1011030000: "ÁUDIO",
    1012070000: "CONDICIONADOR DE AR", 1013030000: "CUIDADOS PESSOAIS",
    1012010000: "EXAUSTORES", 1012020000: "FOGÕES", 1012050000: "FORNOS",
    1012040000: "FREEZER", 1012080000: "LAVADORAS",
    1013010000: "PORTÁTEIS DE COZINHA", 1013020000: "PORTÁTEIS DE SERVIÇO",
    1012030000: "REFRIGERADORES", 1012060000: "SECADORAS",
    1011010000: "TELEVISORES", 1013040000: "VENTILAÇÃO", 1011020000: "VÍDEOS",
    1051020000: "ADULTO", 1055010000: "CAMPING", 1051010000: "INFANTIL",
    1056010000: "LINHA BEBÊ", 1052010000: "MINI VEÍCULOS",
    1033010000: "IMPRESSORAS", 1035010000: "TABLETS",
    1181020000: "COPA",
    1152010000: "IMPORTADO", 1151010000: "LINHA AUTOMOTIVA", 1152020000: "NACIONAL",
    1024030000: "APARADOR", 1023020000: "ARMÁRIOS", 1023010000: "BALCÃO",
    1024020000: "BALCÕES", 1028010000: "BANHEIRO", 1021020000: "CABECEIRAS",
    1023120000: "CADEIRA", 1024080000: "CADEIRAS", 1021010000: "CAMA",
    1021040000: "COLCHÕES MOLA", 1021080000: "CÔMODAS",
    1024010000: "CONJUNTO DE JANTAR", 1023070000: "COZINHAS COMPACTAS",
    1021060000: "CRIADOS", 1023040000: "CRISTALEIRAS", 1023090000: "CUBA",
    1025010000: "ESCRITÓRIO", 1022020000: "ESTANTES", 1022010000: "ESTOFADOS",
    1021070000: "GUARDA-ROUPAS", 1022030000: "HOME", 1023080000: "KITS",
    1026010000: "LAVANDERIA", 1023110000: "MESA",
    1043010000: "ACESSÓRIOS", 1041010000: "CELULARES",
    1061010000: "CUTELARIA", 1063010000: "FORNO E FOGÃO", 1067010000: "UTILIDADES",
    1081010000: "CAMA",
    1193030000: "CAMA BOX", 1191010000: "COLCHÕES DE BERÇO",
    1191030000: "COLCHÕES DE CASAL", 1192020000: "COLCHÕES DE MOLA CASAL",
    1191020000: "COLCHÕES DE SOLTEIRO", 1193010000: "CONJUNTO BOX SOLTEIRO"
}

# ================= STATUS =================

STATUS = {"rodando": False, "total": 0, "atualizados": 0, "criados": 0, "erros": 0}
LOGS = []
STOP = False

def log(msg):
    print(msg)
    LOGS.append(f"{datetime.now()} - {msg}")
    if len(LOGS) > 300:
        LOGS.pop(0)

# ================= REQUEST =================

def safe_request(method, url, **kwargs):
    for tentativa in range(3):
        try:
            return requests.request(method, url, timeout=30, **kwargs)
        except:
            log(f"⚠️ retry {tentativa+1}")
            time.sleep(1)
    return None

# ================= LOGIN =================

def login():
    r = safe_request("POST", LOGIN_URL, json={"cpf": USUARIO, "senha": SENHA, "idempresa": EMPRESA})
    return r and r.json().get("status")

# ================= DETALHE =================

def get_detalhe(id, x, y):
    r = safe_request("GET", f"{BASE}/produto/detalhe/{EMPRESA}/{id}/{x}/{y}")
    if not r:
        return None
    data = r.json()
    return data["itens"][0] if data.get("itens") else None

# ================= WOO =================

def get_produto_woo(sku):
    r = safe_request("GET", URL_WOO, auth=(CK, CS), params={"sku": sku})
    if not r:
        return None
    data = r.json()
    return data[0] if data else None

# ================= COMPARAÇÃO =================
# (mantido igual)

def mudou(prod, woo):
    mudancas = []

    if float(woo.get("regular_price", 0)) != float(prod["price"]):
        mudancas.append(f"💰 {woo.get('regular_price')}→{prod['price']}")

    if int(woo.get("stock_quantity", 0)) != int(prod["stock"]):
        mudancas.append(f"📦 {woo.get('stock_quantity')}→{prod['stock']}")

    if len(woo.get("images", [])) != len(prod["imagens"]):
        mudancas.append(f"🖼️ {len(woo.get('images', []))}→{len(prod['imagens'])}")

    if (woo.get("description") or "") != prod["descricao"]:
        mudancas.append("📄 descrição")

    return mudancas

# ================= ENVIAR =================
# (mantido igual)

def enviar(prod):
    try:
        woo = get_produto_woo(prod["sku"])

        if woo:
            changes = mudou(prod, woo)

            if not changes:
                return

            payload = {
                "regular_price": str(prod["price"]),
                "stock_quantity": prod["stock"],
                "description": prod["descricao"],
                "images": prod["imagens"]
            }

            safe_request("PUT", f"{URL_WOO}/{woo['id']}", auth=(CK, CS), json=payload)

            STATUS["atualizados"] += 1
            log(f"{prod['sku']} | {' | '.join(changes)}")

        else:
            payload = {
                "name": prod["name"],
                "sku": prod["sku"],
                "regular_price": str(prod["price"]),
                "stock_quantity": prod["stock"],
                "manage_stock": True,
                "images": prod["imagens"]
            }

            safe_request("POST", URL_WOO, auth=(CK, CS), json=payload)

            STATUS["criados"] += 1
            log(f"🆕 {prod['sku']} criado")

        time.sleep(0.4)

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ {prod['sku']} {e}")

# ================= EXECUTAR =================
# (mantido igual)

def executar():
    global STOP
    STOP = False

    STATUS.update({"rodando": True, "atualizados": 0, "criados": 0, "erros": 0})

    if not login():
        STATUS["rodando"] = False
        return

    r = safe_request("GET", BUSCA_URL)
    lista = r.json().get("itens", [])

    for item in lista:

        if STOP:
            log("⛔ execução parada")
            break

        try:
            sku = f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"

            detalhe = get_detalhe(item['idproduto'], item.get('idgradex',0), item.get('idgradey',0))
            if not detalhe:
                continue

            imagens = [{"src": url}
                       for img in detalhe.get("fotos", {}).get("imagem", [])
                       for url in img.get("grande", [])]

            prod = {
                "name": detalhe.get("produto"),
                "sku": sku,
                "price": detalhe.get("precovenda", 0),
                "stock": int(detalhe.get("saldo", 0)),
                "descricao": detalhe.get("descricaodetalhada", ""),
                "imagens": imagens
            }

            enviar(prod)

        except Exception as e:
            STATUS["erros"] += 1
            log(f"❌ erro geral {e}")

    STATUS["rodando"] = False
    log("✅ finalizado")

# ================= ROTAS =================

@app.route("/")
def dashboard():
    return send_from_directory("dashboard", "index.html")

@app.route("/executar")
def executar_manual():
    threading.Thread(target=executar).start()
    return "ok"

@app.route("/parar")
def parar():
    global STOP
    STOP = True
    return "parando"

@app.route("/status")
def status():
    return jsonify(STATUS)

@app.route("/logs")
def logs():
    return jsonify(LOGS)

# ================= START =================

if __name__ == "__main__":
    log("🔥 iniciado")
    PORT = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=PORT)