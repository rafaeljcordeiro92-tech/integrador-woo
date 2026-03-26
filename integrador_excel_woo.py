import requests
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
EMPRESA = 272

USUARIO = "00905486986"
SENHA = "Rafael2026@"

URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

TIMEOUT = 20
MAX_WORKERS = 3
CACHE_FILE = "cache_local.json"

session = requests.Session()

# ================= HEADERS (CRÍTICO) =================

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Referer": BASE
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

    log(f"LOGIN STATUS: {r.status_code}")
    log(f"LOGIN RESPONSE: {r.text}")

    data = r.json()

    if not data.get("status"):
        log("❌ login falhou")
        exit()

    log("✅ login OK")
    log(f"🍪 cookies: {session.cookies.get_dict()}")

# ================= CACHE =================

def load_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE, "w"))

# ================= FILTRO =================

def bloqueado(nome):
    palavras = re.sub(r'[^A-Z\s]', ' ', nome.upper()).split()
    return "MM" in palavras or ("BEM" in palavras and "MM" in palavras)

# ================= FORNECEDOR =================

def get_dep(dep):
    lista = []
    offset = 0

    while True:
        url = f"{BASE}/produto/getPorDepartamento/{dep}/{EMPRESA}/{offset}/0/0"

        r = session.get(url, timeout=TIMEOUT)

        try:
            data = r.json()
        except:
            log(f"❌ erro JSON dep {dep}")
            break

        log(f"DEBUG dep {dep}: {data}")

        if not data.get("status"):
            log(f"❌ bloqueado dep {dep}")
            break

        itens = data.get("itens", [])

        if not itens:
            log(f"⚠️ vazio dep {dep}")
            break

        lista.extend(itens)

        log(f"📦 dep {dep} total {len(lista)}")

        if data.get("final"):
            break

        offset += data.get("offset", 12)

        time.sleep(0.5)

    return lista

def get_all():
    tudo = []
    for dep in [
        1010000000,
        1020000000,
        1050000000,
        1190000000
    ]:
        log(f"🚀 carregando dep {dep}")
        tudo.extend(get_dep(dep))

    log(f"📊 TOTAL PRODUTOS: {len(tudo)}")
    return tudo

# ================= WOO =================

def enviar(prod):
    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": prod["sku"],
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "images": prod["images"]
    }

    try:
        requests.post(URL_WOO, auth=(CK, CS), json=payload, timeout=TIMEOUT)
        log(f"🆕 {prod['sku']}")
    except:
        log(f"❌ erro envio {prod['sku']}")

# ================= MAIN =================

def executar():

    log("🚀 inicio")

    login()

    cache = load_cache()

    produtos = get_all()

    if not produtos:
        log("❌ NENHUM PRODUTO ENCONTRADO")
        return

    def proc(p):

        nome = p["produto"]

        if bloqueado(nome):
            return

        sku = p["codigo"]

        prod = {
            "name": nome,
            "price": str(round(float(p["precovenda"]), 2)),
            "sku": sku,
            "stock": int(p["saldo"]),
            "images": []
        }

        for img in p.get("fotos", {}).get("imagem", []):
            try:
                prod["images"].append({"src": img["grande"][0]})
            except:
                pass

        old = cache.get(sku)

        if old and old["price"] == prod["price"] and old["stock"] == prod["stock"]:
            return

        enviar(prod)

        cache[sku] = {
            "price": prod["price"],
            "stock": prod["stock"]
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ex.map(proc, produtos)

    save_cache(cache)

    log("✅ fim")


if __name__ == "__main__":
    executar()