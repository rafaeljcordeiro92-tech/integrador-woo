import requests
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

TIMEOUT = 20
MAX_WORKERS = 3
CACHE_FILE = "cache_local.json"

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

MAPA_SUBDEPARTAMENTOS = { ... }  # mantém seu completo aqui

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= RETRY =================

def request_com_retry(method, url, **kwargs):
    for i in range(3):
        try:
            return requests.request(method, url, **kwargs)
        except:
            log(f"⚠️ retry {i+1}")
            time.sleep(2)
    return None

# ================= CACHE =================

def carregar_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def salvar_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w"))

# ================= FILTRO =================

def produto_bloqueado(nome):
    texto = re.sub(r'[^A-Z\s]', ' ', nome.upper())
    palavras = texto.split()

    for i, p in enumerate(palavras):
        if p == "MM":
            return True
        if p == "BEM" and i+1 < len(palavras) and palavras[i+1] == "MM":
            return True
    return False

# ================= WOO =================

def get_produtos():
    produtos = {}
    page = 1
    while True:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"per_page":100,"page":page})
        if not data := r.json():
            break
        for p in data:
            produtos[p["sku"]] = p["id"]
        page += 1
    return produtos

def get_categorias():
    cats = {}
    page = 1
    while True:
        r = requests.get(URL_CAT, auth=(CK, CS), params={"per_page":100,"page":page})
        if not data := r.json():
            break
        for c in data:
            cats[c["name"]] = c["id"]
        page += 1
    return cats

def criar_categoria(nome, parent=None):
    payload = {"name": nome}
    if parent:
        payload["parent"] = parent
    return requests.post(URL_CAT, auth=(CK, CS), json=payload).json()["id"]

# ================= FORNECEDOR =================

DEPARTAMENTOS = list(MAPA_DEPARTAMENTOS.keys())

def get_produtos_departamento(dep):
    produtos = []
    offset = 0

    while True:
        url = f"{URL}/produto/getPorDepartamento/{dep}/272/{offset}/0/0"

        r = request_com_retry("GET", url, timeout=TIMEOUT)
        if not r:
            break

        data = r.json()
        itens = data.get("itens", [])

        produtos.extend(itens)

        if data.get("final"):
            break

        offset += data.get("offset", 12)

    return produtos

def get_todos_produtos():
    todos = []

    for dep in DEPARTAMENTOS:
        log(f"📦 carregando departamento {dep}")
        produtos = get_produtos_departamento(dep)
        todos.extend(produtos)

    log(f"📊 total produtos fornecedor: {len(todos)}")
    return todos

# ================= EXECUÇÃO =================

def executar():
    log("🚀 ciclo iniciado")

    cache = get_produtos()
    cats = get_categorias()
    cache_local = carregar_cache()

    produtos = get_todos_produtos()
    processados = set()

    def processar(p):
        sku = p["codigo"]
        nome = p["produto"]

        if produto_bloqueado(nome):
            if sku in cache:
                request_com_retry("DELETE", f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), params={"force": True})
                log(f"🗑️ removido MM: {sku}")
            return

        processados.add(sku)

        prod = {
            "name": nome,
            "price": str(round(float(p["precovenda"]), 2)),
            "stock": int(p["saldo"]),
            "dep": None,
            "subdep": p.get("idsubdepartamento"),
            "images": []
        }

        for img in p.get("fotos", {}).get("imagem", []):
            if img.get("grande"):
                prod["images"].append({"src": img["grande"][0]})

        antigo = cache_local.get(sku)
        if antigo and antigo["price"] == prod["price"] and antigo["stock"] == prod["stock"]:
            return

        enviar(prod, sku, cache, cats)

        cache_local[sku] = {
            "price": prod["price"],
            "stock": prod["stock"]
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(processar, produtos)

    # 🔒 proteção inteligente
    if len(processados) > 100:
        for sku, prod_id in cache.items():
            if sku not in processados:
                zerar_estoque(prod_id, sku)
    else:
        log("⚠️ proteção ativada - não zerando estoque")

    salvar_cache(cache_local)

    log("✅ ciclo finalizado")