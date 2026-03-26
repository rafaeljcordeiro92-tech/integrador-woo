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

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= RETRY =================

def request_retry(method, url, **kwargs):
    for i in range(3):
        try:
            return requests.request(method, url, timeout=TIMEOUT, **kwargs)
        except:
            log(f"⚠️ retry {i+1}")
            time.sleep(2)
    return None

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

# ================= WOO =================

def get_woo():
    produtos = {}
    page = 1

    while True:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"per_page":100,"page":page})
        data = r.json()
        if not data:
            break

        for p in data:
            produtos[p["sku"]] = p["id"]

        page += 1

    return produtos

def get_cats():
    cats = {}
    page = 1

    while True:
        r = requests.get(URL_CAT, auth=(CK, CS), params={"per_page":100,"page":page})
        data = r.json()
        if not data:
            break

        for c in data:
            cats[c["name"]] = c["id"]

        page += 1

    return cats

def cria_cat(nome, parent=None):
    payload = {"name": nome}
    if parent:
        payload["parent"] = parent

    r = requests.post(URL_CAT, auth=(CK, CS), json=payload)
    return r.json()["id"]

# ================= FORNECEDOR =================

def get_dep(dep):
    lista = []
    offset = 0

    while True:
        url = f"{URL}/produto/getPorDepartamento/{dep}/272/{offset}/0/0"

        r = request_retry("GET", url)
        if not r:
            break

        data = r.json()
        itens = data.get("itens", [])

        lista.extend(itens)

        log(f"📄 dep {dep} offset {offset} total {len(lista)}")

        if data.get("final"):
            break

        offset += data.get("offset", 12)

    return lista

def get_all():
    tudo = []

    for dep in MAPA_DEPARTAMENTOS.keys():
        log(f"📦 dep {dep}")
        tudo.extend(get_dep(dep))

    log(f"📊 TOTAL {len(tudo)}")
    return tudo

# ================= ENVIO =================

def enviar(prod, sku, cache, cats):

    dep = MAPA_DEPARTAMENTOS.get(prod["dep"], "OUTROS")
    sub = MAPA_SUBDEPARTAMENTOS.get(prod["subdep"])

    if dep not in cats:
        cats[dep] = cria_cat(dep)

    cat_id = cats[dep]

    if sub:
        if sub not in cats:
            cats[sub] = cria_cat(sub, parent=cat_id)
        cat_id = cats[sub]

    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": sku,
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "categories": [{"id": cat_id}],
        "images": prod["images"]
    }

    if sku in cache:
        request_retry("PUT", f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
        log(f"♻️ {sku}")
    else:
        request_retry("POST", URL_WOO, auth=(CK, CS), json=payload)
        log(f"🆕 {sku}")

# ================= MAIN =================

def executar():

    log("🚀 inicio")

    cache = get_woo()
    cats = get_cats()
    cache_local = load_cache()

    produtos = get_all()

    def proc(p):

        sku = p["codigo"]
        nome = p["produto"]

        if bloqueado(nome):
            return

        prod = {
            "name": nome,
            "price": str(round(float(p["precovenda"]), 2)),
            "stock": int(p["saldo"]),
            "dep": p.get("iddepartamento"),
            "subdep": p.get("idsubdepartamento"),
            "images": []
        }

        for img in p.get("fotos", {}).get("imagem", []):
            try:
                prod["images"].append({"src": img["grande"][0]})
            except:
                pass

        old = cache_local.get(sku)
        if old and old["price"] == prod["price"] and old["stock"] == prod["stock"]:
            return

        enviar(prod, sku, cache, cats)

        cache_local[sku] = {
            "price": prod["price"],
            "stock": prod["stock"]
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ex.map(proc, produtos)

    save_cache(cache_local)

    log("✅ fim")


if __name__ == "__main__":
    executar()