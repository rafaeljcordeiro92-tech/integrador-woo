import requests
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

COOKIE_FILE = "cookies.json"

MAX_THREADS = 10
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

# ================= DEBUG SKUS =================

def buscar_skus(session):
    print("🔎 buscando SKUs...")

    try:
        url = f"{URL}/produto/listar/272"
        r = session.get(url, timeout=30)

        print("STATUS:", r.status_code)
        print("CONTENT-TYPE:", r.headers.get("content-type"))

        print("\n--- RESPOSTA (INÍCIO) ---")
        print(r.text[:500])
        print("--- FIM ---\n")

        if "html" in r.headers.get("content-type", ""):
            print("❌ RETORNOU HTML → LOGIN FALHOU")
            return []

        try:
            data = r.json()
        except:
            print("❌ NÃO É JSON VÁLIDO")
            return []

        if "produtos" not in data:
            print("⚠️ JSON não contém 'produtos'")
            return []

        skus = []
        for item in data.get("produtos", []):
            if item.get("codigo"):
                skus.append(str(item["codigo"]))

        print(f"✅ {len(skus)} SKUs encontrados")
        return skus

    except Exception as e:
        print("❌ erro SKUs:", e)
        return []

# ================= WOO =================

def carregar_categorias():
    cats = []
    page = 1

    while True:
        r = requests.get(URL_CAT, auth=(CK, CS), params={"per_page": 100, "page": page})
        if r.status_code != 200:
            break

        data = r.json()
        if not data:
            break

        cats.extend(data)
        page += 1

    return cats

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

    except Exception as e:
        print("❌ erro produto:", sku, e)
        return None

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

    if sku in cache:
        requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
        print("♻️ update:", sku)
    else:
        requests.post(URL_WOO, auth=(CK, CS), json=payload)
        print("🆕 create:", sku)

# ================= EXECUÇÃO =================

def executar():
    print("\n🚀 ciclo iniciado")

    session = carregar_sessao()

    categorias = carregar_categorias()
    cache = carregar_produtos_woo()

    skus = buscar_skus(session)

    if not skus:
        print("⚠️ nenhum SKU encontrado")
        return

    def processar(sku):
        sku = limpar_sku(sku)

        prod = pegar_produto(session, sku)
        if not prod:
            return

        if prod["stock"] == 0:
            return

        enviar(prod, sku, cache)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(processar, skus)

    print("✅ ciclo finalizado")

# ================= LOOP =================

while True:
    executar()
    time.sleep(INTERVALO)