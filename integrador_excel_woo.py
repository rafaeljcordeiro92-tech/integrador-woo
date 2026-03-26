import requests
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import threading

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

CACHE_FILE = "cache.json"
TIMEOUT = 60
MAX_WORKERS = 2
INTERVALO = 300

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE,
    "Origin": BASE
})

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= RETRY =================

def request_com_retry(url, tentativas=3):
    for tentativa in range(tentativas):
        try:
            r = session.get(url, timeout=TIMEOUT)
            return r
        except:
            log(f"⚠️ tentativa {tentativa+1} falhou: {url}")
            time.sleep(2)

    log(f"❌ falhou definitivo: {url}")
    return None

# ================= LOGIN =================

def login():
    try:
        payload = {
            "cpf": USUARIO,
            "senha": SENHA,
            "idempresa": EMPRESA
        }

        r = session.post(LOGIN_URL, json=payload, timeout=TIMEOUT)

        if not r.json().get("status"):
            log("❌ login falhou")
            return False

        log("✅ login OK")
        return True

    except Exception as e:
        log(f"❌ erro login: {e}")
        return False

# ================= DETALHE =================

def get_detalhe(sku):
    try:
        p = sku.split(".")
        url = f"{BASE}/produto/detalhe/{EMPRESA}/{p[0]}/{p[1]}/{p[2]}"

        r = request_com_retry(url)
        if not r:
            return None

        return r.json()["itens"][0]

    except:
        return None

# ================= FILTRO =================

def bloqueado(nome):
    palavras = re.sub(r'[^A-Z\s]', ' ', nome.upper()).split()
    return "MM" in palavras

# ================= CACHE =================

def load_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE, "w"))

# ================= WOO =================

def produto_existe(sku):
    try:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"sku": sku}, timeout=TIMEOUT)
        data = r.json()
        if data:
            return data[0]["id"]
        return None
    except:
        return None

def enviar(prod):

    prod_id = produto_existe(prod["sku"])

    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": prod["sku"],
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "images": prod["images"]
    }

    try:
        if prod_id:
            requests.put(f"{URL_WOO}/{prod_id}", auth=(CK, CS), json=payload, timeout=TIMEOUT)
            log(f"♻️ atualizado {prod['sku']}")
        else:
            requests.post(URL_WOO, auth=(CK, CS), json=payload, timeout=TIMEOUT)
            log(f"🆕 criado {prod['sku']}")
    except Exception as e:
        log(f"❌ erro envio {prod['sku']}: {e}")

# ================= EXECUÇÃO =================

def executar():

    log("🚀 inicio")

    if not login():
        return

    cache = load_cache()

    r = request_com_retry(BUSCA_URL)
    if not r:
        return

    try:
        lista = r.json().get("itens", [])
    except:
        log("❌ erro lista")
        return

    skus_fornecedor = set()

    def processar(item):

        idp = item.get("idproduto")
        gx = item.get("idgradex", 0)
        gy = item.get("idgradey", 0)

        sku = f"{idp}.{gx}.{gy}"
        skus_fornecedor.add(sku)

        data = get_detalhe(sku)
        if not data:
            return

        nome = data["produto"]

        if bloqueado(nome):
            return

        prod = {
            "name": nome,
            "price": str(round(float(data["precovenda"]), 2)),
            "sku": sku,
            "stock": int(item.get("saldo", 0)),
            "images": []
        }

        for img in data.get("fotos", {}).get("imagem", []):
            try:
                prod["images"].append({"src": img["grande"][0]})
            except:
                pass

        old = cache.get(sku)

        if old and old == prod:
            return

        enviar(prod)
        cache[sku] = prod

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ex.map(processar, lista)

    # 🔥 ZERAR PRODUTOS

    log("🧹 zerando produtos...")

    try:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"per_page": 100})
        produtos_woo = r.json()
    except:
        produtos_woo = []

    for p in produtos_woo:
        sku = p.get("sku")

        if sku and sku not in skus_fornecedor:
            try:
                requests.put(
                    f"{URL_WOO}/{p['id']}",
                    auth=(CK, CS),
                    json={"stock_quantity": 0, "manage_stock": True}
                )
                log(f"❌ zerado {sku}")
            except:
                pass

    save_cache(cache)

    log("✅ finalizado")

# ================= LOOP =================

app = Flask(__name__)

def loop():
    while True:
        try:
            executar()
        except Exception as e:
            log(f"❌ erro loop: {e}")

        time.sleep(INTERVALO)

@app.route("/")
def home():
    return "Integrador Woo rodando 🚀"

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    log("🔥 Loop iniciado")
    app.run(host="0.0.0.0", port=8080)