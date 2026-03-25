import requests
import time
import json
import re
import random
from datetime import datetime

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

COOKIE_FILE = "cookies.json"

INTERVALO = 1200
SKUS_POR_CICLO = 150

DELAY_MIN = 1.0
DELAY_MAX = 2.5

# 🔥 CONTROLE DE HORÁRIO
HORA_INICIO = 8
HORA_FIM = 22

# ================= MAPAS =================
# (mantive exatamente igual ao seu)

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

MAPA_SUBDEPARTAMENTOS = { ... }  # mantém o seu inteiro

# ================= UTIL =================

def delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

def dentro_horario():
    hora = datetime.now().hour
    return HORA_INICIO <= hora <= HORA_FIM

def limpar_sku(sku):
    return re.sub(r"[^0-9.]", "", sku)

def montar_url(sku):
    p = sku.split(".")
    return f"{URL}/produto/detalhe/272/{p[0]}/{p[1]}/{p[2]}"

# ================= SESSÃO =================

def sessao():
    s = requests.Session()

    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Connection": "keep-alive"
    })

    try:
        cookies = json.load(open(COOKIE_FILE))
        for c in cookies:
            s.cookies.set(c["name"], c["value"])
        print("✅ cookies carregados")
    except:
        print("⚠️ cookies não carregados")

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

        # 🔥 DETECTAR LOGIN EXPIRADO
        if "login" in r.text.lower():
            print("🔐 sessão expirada! precisa renovar cookies")
            return None

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
        print("❌ erro produto:", sku, e)
        return None

# ================= ENVIO =================

def enviar(prod, sku, cache, cats):
    dep_nome = MAPA_DEPARTAMENTOS.get(prod["dep"], "OUTROS")
    sub_nome = MAPA_SUBDEPARTAMENTOS.get(prod["subdep"], None)

    if dep_nome not in cats:
        cats[dep_nome] = criar_categoria(dep_nome)
        print("📁 categoria criada:", dep_nome)

    cat_id = cats[dep_nome]

    if sub_nome:
        if sub_nome not in cats:
            cats[sub_nome] = criar_categoria(sub_nome, parent=cat_id)
            print("📂 subcategoria criada:", sub_nome)
        cat_id = cats[sub_nome]

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

    # 🔥 LOG INTELIGENTE
    print(f"💰 {sku} | R${prod['price']} | estoque {prod['stock']}")

    if sku in cache:
        requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
        print("♻️ update:", sku)
    else:
        requests.post(URL_WOO, auth=(CK, CS), json=payload)
        print("🆕 create:", sku)

# ================= PROCESSOS =================

def atualizar_existentes(session, cache, cats):
    print("🔄 atualização controlada...")

    skus = list(cache.keys())[:SKUS_POR_CICLO]

    for sku in skus:
        prod = pegar(session, sku)
        if prod:
            enviar(prod, sku, cache, cats)

def descobrir_novos(session, cache, cats):
    print("🧠 descoberta leve...")

    encontrados = 0

    for a in range(300, 360):
        for b in range(1, 10):
            for c in range(0, 3):

                sku = f"{a}.{b}.{c}"

                if sku in cache:
                    continue

                prod = pegar(session, sku)
                if not prod:
                    continue

                enviar(prod, sku, cache, cats)
                encontrados += 1

                if encontrados >= 20:
                    print("🛑 limite descoberta atingido")
                    return

# ================= EXECUÇÃO =================

def executar():
    if not dentro_horario():
        print("🌙 fora do horário de operação")
        return

    print("\n🚀 ciclo iniciado")

    s = sessao()
    cache = get_produtos()
    cats = get_categorias()

    print(f"📦 {len(cache)} produtos no Woo")

    atualizar_existentes(s, cache, cats)
    descobrir_novos(s, cache, cats)

    print("✅ ciclo finalizado")

# ================= LOOP =================

while True:
    executar()
    time.sleep(INTERVALO)