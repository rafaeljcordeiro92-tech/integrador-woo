import requests
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
BUSCA_URL = BASE + "/produto/listar"
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

# ================= MAPAS =================

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

# ================= BUSCA REAL =================

def buscar_skus():

    payload = {
        "busca": " "
    }

    r = session.post(BUSCA_URL, json=payload, timeout=TIMEOUT)

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