import requests
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

COOKIE_FILE = "cookies.json"
SKU_FILE = "skus_validos.json"

MAX_THREADS = 5
INTERVALO = 300

# ================= UTIL =================

def limpar_sku(sku):
    return re.sub(r"[^0-9.]", "", sku)

def montar_url_produto(sku):
    p = sku.split(".")
    if len(p) < 3:
        return None
    return f"{URL}/produto/detalhe/272/{p[0]}/{p[1]}/{p[2]}"

# ================= SESSÃO =================

def carregar_sessao():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*"
    })

    try:
        cookies = json.load(open(COOKIE_FILE))
        for c in cookies:
            session.cookies.set(c["name"], c["value"])
        print("✅ cookies carregados")
    except:
        print("⚠️ cookies não carregados")

    return session

# ================= CACHE SKU =================

def carregar_skus_salvos():
    try:
        with open(SKU_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def salvar_skus(skus):
    with open(SKU_FILE, "w") as f:
        json.dump(list(set(skus)), f, indent=2)

# ================= GERADOR =================

def gerar_skus_base():
    skus = []

    for a in range(300, 360):
        for b in range(1, 20):
            for c in range(0, 10):
                skus.append(f"{a}.{b}.{c}")

    return skus

def preparar_skus():
    salvos = carregar_skus_salvos()
    gerados = gerar_skus_base()

    novos = list(set(gerados) - set(salvos))

    print(f"🧠 {len(salvos)} SKUs já conhecidos")
    print(f"🆕 {len(novos)} SKUs novos")

    return novos, salvos

# ================= PRODUTO =================

def pegar_produto(session, sku):
    try:
        url = montar_url_produto(sku)
        if not url:
            return None

        r = session.get(url, timeout=15)

        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except:
            return None

        if not data.get("itens"):
            return None

        p = data["itens"][0]

        return {
            "name": p["produto"],
            "price": f"{float(p['precovenda']):.2f}",
            "stock": int(p["saldo"]),
            "description": p.get("descricaotecnica", ""),
            "images": [{"src": img["grande"][0]} for img in p["fotos"]["imagem"]],
        }

    except:
        return None

# ================= WOO =================

def carregar_produtos_woo():
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

def enviar(produto, sku, cache):
    payload = {
        "name": produto["name"],
        "regular_price": produto["price"],
        "sku": sku,
        "stock_quantity": produto["stock"],
        "manage_stock": True,
        "stock_status": "instock",
        "description": produto["description"],
        "images": produto["images"],
    }

    try:
        if sku in cache:
            requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
            print("♻️ update:", sku)
        else:
            requests.post(URL_WOO, auth=(CK, CS), json=payload)
            print("🆕 create:", sku)
    except:
        print("❌ erro ao enviar:", sku)

# ================= EXECUÇÃO =================

def executar():
    print("\n🚀 ciclo iniciado")

    session = carregar_sessao()

    cache = carregar_produtos_woo()
    print(f"📦 {len(cache)} produtos no Woo")

    novos_skus, skus_salvos = preparar_skus()

    validos = []

    def processar(sku):
        sku = limpar_sku(sku)

        prod = pegar_produto(session, sku)

        if not prod:
            return

        if prod["stock"] == 0:
            return

        validos.append(sku)
        enviar(prod, sku, cache)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(processar, novos_skus)

    todos = skus_salvos + validos
    salvar_skus(todos)

    print(f"💾 {len(validos)} novos SKUs salvos")
    print("✅ ciclo finalizado")

# ================= LOOP =================

while True:
    executar()
    time.sleep(INTERVALO)