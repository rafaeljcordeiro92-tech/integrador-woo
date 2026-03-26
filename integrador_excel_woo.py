import requests
import time
import json
import random
import re
from datetime import datetime
from stats import registrar_evento
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

COOKIE_FILE = "cookies.json"

SKUS_POR_CICLO = 120
MAX_WORKERS = 3
TIMEOUT = 20

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= RETRY =================

def request_com_retry(method, url, **kwargs):
    for tentativa in range(3):
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.RequestException:
            log(f"⚠️ retry {tentativa+1}")
            time.sleep(2)
    return None

# ================= FILTRO =================

def produto_bloqueado(prod):
    nome = prod.get("name", "")
    texto = re.sub(r'[^A-Z\s]', ' ', nome.upper())
    palavras = texto.split()

    for i, p in enumerate(palavras):
        if p == "MM":
            return True
        if p == "BEM" and i+1 < len(palavras) and palavras[i+1] == "MM":
            return True

    return False

# ================= SESSÃO =================

def sessao():
    s = requests.Session()
    try:
        cookies = json.load(open(COOKIE_FILE))
        for c in cookies:
            s.cookies.set(c["name"], c["value"])
        log("✅ cookies carregados")
    except:
        log("⚠️ cookies não carregados")
    return s

# ================= SKUS FORNECEDOR =================

def get_skus_fornecedor(session):
    try:
        url = f"{URL}/produto/lista/272"

        r = request_com_retry("GET", url, timeout=TIMEOUT)
        if not r:
            return []

        data = r.json()

        skus = [str(p["codigo"]) for p in data.get("produtos", []) if p.get("codigo")]

        log(f"📦 {len(skus)} SKUs carregados")
        return skus

    except Exception as e:
        log(f"❌ erro SKUs fornecedor: {e}")
        return []

# ================= PRODUTO =================

def pegar(session, sku):
    try:
        url = f"{URL}/produto/detalhe/272/{'/'.join(sku.split('.')[:3])}"

        r = request_com_retry("GET", url, timeout=TIMEOUT)
        if not r or r.status_code != 200:
            return None

        data = r.json()
        if not data.get("itens"):
            return None

        p = data["itens"][0]

        return {
            "name": p["produto"],
            "price": str(round(float(p["precovenda"]), 2)),
            "stock": int(p["saldo"]),
            "descricao": p.get("descricaotecnica", ""),
            "images": [{"src": img["grande"][0]} for img in p["fotos"]["imagem"]],
        }

    except Exception as e:
        log(f"❌ erro produto {sku}: {e}")
        return None

# ================= WOO =================

def get_produtos():
    produtos = {}
    page = 1
    while True:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"per_page": 100, "page": page})
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        for p in data:
            produtos[p["sku"]] = p["id"]
        page += 1
    return produtos

# ================= ENVIO =================

def enviar(prod, sku, cache):
    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": sku,
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "images": prod["images"],
        "description": prod["descricao"],
    }

    try:
        if sku in cache:
            request_com_retry("PUT", f"{URL_WOO}/{cache[sku]}", json=payload, auth=(CK, CS), timeout=TIMEOUT)
            log(f"♻️ atualização: {sku}")
        else:
            request_com_retry("POST", URL_WOO, json=payload, auth=(CK, CS), timeout=TIMEOUT)
            log(f"🆕 criação: {sku}")
    except Exception as e:
        log(f"❌ erro envio: {sku} - {e}")

# ================= EXECUÇÃO =================

def executar():
    log("🚀 ciclo iniciado")

    s = sessao()
    cache = get_produtos()
    skus = get_skus_fornecedor(s)

    random.shuffle(skus)

    def processar(sku):
        prod = pegar(s, sku)
        if not prod:
            return

        if produto_bloqueado(prod):
            log(f"🚫 bloqueado: {sku} - {prod['name']}")
            return

        enviar(prod, sku, cache)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(processar, skus[:SKUS_POR_CICLO])

    log("✅ ciclo finalizado")