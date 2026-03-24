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

MAX_THREADS = 15
INTERVALO = 300

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
    1012030000: "REFRIGERADORES", 1012060000: "SECADORAS E CENTRÍFUGAS",
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
    1021110000: "MÓVEIS QUARTO - DIVERSOS", 1023050000: "NICHO",
    1023030000: "PANELEIROS", 1022040000: "RACKS", 1023100000: "TAMPOS",

    1043010000: "ACESSÓRIOS", 1041010000: "CELULARES",

    1061010000: "CUTELARIA", 1063010000: "FORNO E FOGÃO", 1067010000: "UTILIDADES",

    1081010000: "CAMA",

    1193030000: "CAMA BOX", 1191010000: "COLCHÕES DE BERÇO",
    1191030000: "COLCHÕES DE CASAL", 1192020000: "COLCHÕES DE MOLA CASAL",
    1191020000: "COLCHÕES DE SOLTEIRO", 1193010000: "CONJUNTO BOX SOLTEIRO"
}

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
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        cookies = json.load(open(COOKIE_FILE))
        for c in cookies:
            session.cookies.set(c["name"], c["value"])
    except:
        print("⚠️ cookies não carregados")

    return session

# ================= BUSCAR SKUS =================

def buscar_skus(session):
    print("🔎 buscando SKUs...")

    try:
        r = session.get(f"{URL}/produto/listar/272", timeout=30)

        if r.status_code != 200:
            print("❌ erro ao buscar SKUs")
            return []

        data = r.json()

        skus = []
        for item in data.get("produtos", []):
            if item.get("codigo"):
                skus.append(str(item["codigo"]))

        print(f"✅ {len(skus)} SKUs encontrados")
        return skus

    except Exception as e:
        print("❌ erro SKUs:", e)
        return []

# ================= RESTO =================

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

        data = r.json()
        if not data.get("itens"):
            return None

        p = data["itens"][0]

        return {
            "name": p["produto"],
            "price": f"{float(p['precovenda']):.2f}",
            "stock": int(p["saldo"]),
            "description": p.get("descricaotecnica", ""),
            "images": [{"src": img["grande"][0]} for img in p["fotos"]["imagem"]],
            "dep": p["iddepartamento"],
            "subdep": int(p.get("idcategoria")) if p.get("idcategoria") else None
        }

    except Exception as e:
        print("❌ erro produto:", sku, e)
        return None

def enviar(produto, sku, categorias, cache):
    payload = {
        "name": produto["name"],
        "regular_price": produto["price"],
        "sku": sku,
        "stock_quantity": produto["stock"],
        "manage_stock": True,
        "stock_status": "instock",
        "description": produto["description"],
        "images": produto["images"],
        "categories": []
    }

    if sku in cache:
        requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
    else:
        requests.post(URL_WOO, auth=(CK, CS), json=payload)

# ================= EXECUÇÃO =================

def executar():
    print("🚀 ciclo iniciado")

    session = carregar_sessao()

    categorias = carregar_categorias()
    cache = carregar_produtos_woo()

    skus = buscar_skus(session)

    def processar(sku):
        sku = limpar_sku(sku)

        prod = pegar_produto(session, sku)
        if not prod:
            return

        if prod["stock"] == 0:
            return

        enviar(prod, sku, categorias, cache)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(processar, skus)

    print("✅ ciclo finalizado")

# ================= LOOP =================

while True:
    executar()
    time.sleep(INTERVALO)