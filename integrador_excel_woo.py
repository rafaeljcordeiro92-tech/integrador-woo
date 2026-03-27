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
URL_WOO_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

session = requests.Session()

# ================= MAPAS =================
# (mantive exatamente como você tinha)

MAPA_DEPARTAMENTOS = {...}
MAPA_SUBDEPARTAMENTOS = {...}

# ================= STATUS =================

STATUS = {"rodando": False, "total": 0, "atualizados": 0, "criados": 0, "erros": 0}
LOGS = []

def log(msg):
    print(msg)
    LOGS.append(f"{datetime.now()} - {msg}")
    if len(LOGS) > 300:
        LOGS.pop(0)

# ================= SAFE REQUEST =================

def safe_request(method, url, **kwargs):
    for tentativa in range(3):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            return r
        except Exception as e:
            log(f"⚠️ retry {tentativa+1} {url}")
            time.sleep(1)
    return None

# ================= LOGIN =================

def login():
    r = safe_request("POST", LOGIN_URL, json={"cpf": USUARIO, "senha": SENHA, "idempresa": EMPRESA})
    return r and r.json().get("status")

# ================= DETALHE =================

def get_detalhe(id, x, y):
    url = f"{BASE}/produto/detalhe/{EMPRESA}/{id}/{x}/{y}"
    r = safe_request("GET", url)
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

def get_todos_produtos_woo():
    produtos = []
    page = 1

    while True:
        r = safe_request("GET", URL_WOO, auth=(CK, CS), params={"per_page": 100, "page": page})
        if not r:
            break

        data = r.json()
        if not data:
            break

        produtos.extend(data)
        page += 1

    return produtos

# ================= ENVIAR =================

def enviar(prod):
    try:
        prod_woo = get_produto_woo(prod["sku"])
        prod_id = prod_woo["id"] if prod_woo else None

        payload = {
            "name": prod["name"],
            "sku": prod["sku"],
            "regular_price": str(prod["price"]),
            "stock_quantity": int(prod["stock"]),
            "manage_stock": True,
            "stock_status": "instock" if prod["stock"] > 0 else "outofstock",
            "description": prod["descricao"],
            "short_description": prod["descricao"],
            "images": prod["imagens"],
            "attributes": prod["atributos"]
        }

        if prod_id:
            safe_request("PUT", f"{URL_WOO}/{prod_id}", auth=(CK, CS), json=payload)
            STATUS["atualizados"] += 1
        else:
            safe_request("POST", URL_WOO, auth=(CK, CS), json=payload)
            STATUS["criados"] += 1

        log(f"✔ {prod['sku']} atualizado")

        time.sleep(0.3)

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ erro {prod['sku']} {e}")

# ================= ZERAR =================

def zerar_produtos_ausentes(skus_fornecedor):
    produtos = get_todos_produtos_woo()

    for p in produtos:
        sku = p.get("sku")
        if sku and sku not in skus_fornecedor:
            safe_request("PUT", f"{URL_WOO}/{p['id']}", auth=(CK, CS),
                         json={"stock_quantity": 0, "stock_status": "outofstock"})
            log(f"🚫 zerado {sku}")

# ================= EXECUTAR =================

def executar():
    STATUS.update({"rodando": True, "atualizados": 0, "criados": 0, "erros": 0})

    if not login():
        STATUS["rodando"] = False
        return

    r = safe_request("GET", BUSCA_URL)
    lista = r.json().get("itens", [])

    skus_fornecedor = set()

    for item in lista:
        try:
            sku = f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"
            skus_fornecedor.add(sku)

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
                "imagens": imagens,
                "atributos": []
            }

            enviar(prod)

        except Exception as e:
            STATUS["erros"] += 1
            log(f"❌ erro geral {e}")

    zerar_produtos_ausentes(skus_fornecedor)

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