import requests
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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
TIMEOUT = 20
MAX_WORKERS = 5

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

# ================= LOGIN =================

def login():
    payload = {
        "cpf": USUARIO,
        "senha": SENHA,
        "idempresa": EMPRESA
    }

    r = session.post(LOGIN_URL, json=payload)

    if not r.json().get("status"):
        log("❌ login falhou")
        exit()

    log("✅ login OK")

# ================= BUSCA =================

def buscar_skus():

    r = session.get(BUSCA_URL, timeout=TIMEOUT)

    log(f"STATUS BUSCA: {r.status_code}")

    data = r.json()

    skus = [item["codigo"] for item in data.get("itens", [])]

    log(f"📦 TOTAL SKUS: {len(skus)}")

    return skus

# ================= DETALHE =================

def get_detalhe(sku):
    try:
        p = sku.split(".")
        url = f"{BASE}/produto/detalhe/{EMPRESA}/{p[0]}/{p[1]}/{p[2]}"
        r = session.get(url, timeout=TIMEOUT)
        return r.json()["itens"][0]
    except:
        return None

# ================= FILTRO =================

def bloqueado(nome):
    palavras = re.sub(r'[^A-Z\s]', ' ', nome.upper()).split()
    return "MM" in palavras or ("BEM" in palavras and "MM" in palavras)

# ================= CACHE =================

def load_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE, "w"))

# ================= WOO =================

def enviar(prod):
    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": prod["sku"],
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "categories": [{"name": prod["categoria"]}],
        "images": prod["images"]
    }

    try:
        requests.post(URL_WOO, auth=(CK, CS), json=payload)
        log(f"🆕 {prod['sku']}")
    except:
        log(f"❌ erro envio {prod['sku']}")

# ================= MAPA =================

MAPA_SUBDEPARTAMENTOS = {
    1191030000: "COLCHÕES DE CASAL",
    1191020000: "COLCHÕES DE SOLTEIRO",
    1193030000: "CAMA BOX"
}

# ================= MAIN =================

def executar():

    log("🚀 inicio")

    login()

    cache = load_cache()

    skus = buscar_skus()

    def processar(sku):

        data = get_detalhe(sku)
        if not data:
            return

        nome = data["produto"]

        if bloqueado(nome):
            return

        categoria = MAPA_SUBDEPARTAMENTOS.get(
            int(data.get("idcategoria", 0)),
            "GERAL"
        )

        prod = {
            "name": nome,
            "price": str(round(float(data["precovenda"]), 2)),
            "sku": sku,
            "stock": int(data["saldo"]),
            "categoria": categoria,
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
        ex.map(processar, skus)

    save_cache(cache)

    log("✅ finalizado")


if __name__ == "__main__":
    executar()