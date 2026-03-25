import requests
import time
import json
import random
from datetime import datetime
from stats import registrar_evento

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

COOKIE_FILE = "cookies.json"

INTERVALO = 1200
SKUS_POR_CICLO = 120

DELAY_MIN = 1.5
DELAY_MAX = 3.5

HORA_INICIO = 8
HORA_FIM = 22

CACHE_FILE = "cache_local.json"

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

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

# ================= CACHE =================

def carregar_cache_local():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def salvar_cache_local(cache):
    json.dump(cache, open(CACHE_FILE, "w"))

# ================= UTIL =================

def delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

def dentro_horario():
    hora = datetime.now().hour
    return HORA_INICIO <= hora <= HORA_FIM

def montar_url(sku):
    p = sku.split(".")
    return f"{URL}/produto/detalhe/272/{p[0]}/{p[1]}/{p[2]}"

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

def get_categorias():
    cats = {}
    page = 1

    while True:
        r = requests.get(URL_CAT, auth=(CK, CS), params={"per_page": 100, "page": page})
        if r.status_code != 200:
            break

        data = r.json()
        if not data:
            break

        for c in data:
            cats[c["name"]] = c["id"]

        page += 1

    return cats

def criar_categoria(nome, parent=None):
    payload = {"name": nome}
    if parent:
        payload["parent"] = parent

    r = requests.post(URL_CAT, auth=(CK, CS), json=payload)
    return r.json()["id"]

# ================= PRODUTO =================

def pegar(session, sku):
    try:
        delay()
        r = session.get(montar_url(sku), timeout=10)

        if r.status_code != 200:
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
            "dep": p["iddepartamento"],
            "subdep": int(p.get("idcategoria")) if p.get("idcategoria") else None,
            "images": [{"src": img["grande"][0]} for img in p["fotos"]["imagem"]],
        }

    except Exception as e:
        log(f"❌ erro produto {sku}: {e}")
        registrar_evento("erros")
        return None

# ================= ENVIO =================

def enviar(prod, sku, cache, cats, cache_local):
    dep_nome = MAPA_DEPARTAMENTOS.get(prod["dep"], "OUTROS")
    sub_nome = MAPA_SUBDEPARTAMENTOS.get(prod["subdep"], None)

    if dep_nome not in cats:
        cats[dep_nome] = criar_categoria(dep_nome)
        log(f"📁 categoria criada: {dep_nome}")

    cat_id = cats[dep_nome]

    if sub_nome:
        if sub_nome not in cats:
            cats[sub_nome] = criar_categoria(sub_nome, parent=cat_id)
            log(f"📂 subcategoria criada: {sub_nome}")
        cat_id = cats[sub_nome]

    antigo = cache_local.get(sku)

    if antigo:
        if antigo["price"] == prod["price"] and antigo["stock"] == prod["stock"]:
            log(f"⏭️ sem mudança: {sku}")
            return

    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": sku,
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "categories": [{"id": cat_id}],
        "images": prod["images"],
        "description": prod["descricao"],
    }

    try:
        if sku in cache:
            requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
            log(f"♻️ update: {sku}")
            registrar_evento("updates")
        else:
            requests.post(URL_WOO, auth=(CK, CS), json=payload)
            log(f"🆕 create: {sku}")
            registrar_evento("novos")

    except Exception as e:
        log(f"❌ erro envio: {sku} - {e}")
        registrar_evento("erros")

    cache_local[sku] = {
        "price": prod["price"],
        "stock": prod["stock"]
    }

# ================= EXECUÇÃO =================

def executar():
    if not dentro_horario():
        log("🌙 fora do horário")
        return

    log("🚀 ciclo iniciado")

    s = sessao()
    cache = get_produtos()
    cats = get_categorias()
    cache_local = carregar_cache_local()

    log(f"📦 {len(cache)} produtos no Woo")

    skus = list(cache.keys())
    random.shuffle(skus)

    for sku in skus[:SKUS_POR_CICLO]:
        prod = pegar(s, sku)
        if prod:
            enviar(prod, sku, cache, cats, cache_local)

    salvar_cache_local(cache_local)

    log("✅ ciclo finalizado")