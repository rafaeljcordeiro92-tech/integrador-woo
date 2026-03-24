import pandas as pd
import requests
import time
import json
import os
import re

from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

ARQUIVO = r"C:\Users\Rafa\Desktop\produtos.xlsx"
COOKIE_FILE = "cookies.json"

MAX_THREADS = 15

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

# 🔥 MAPA COMPLETO (seu final)
MAPA_SUBDEPARTAMENTOS = {
    # (mantive exatamente como você consolidou)
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

def produto_bloqueado(txt):
    if not txt:
        return False
    txt = txt.upper()
    return bool(re.search(r'\bMM\b|\bBEM\s+MM\b', txt))

# ================= SESSÃO =================

def carregar_sessao():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    cookies = json.load(open(COOKIE_FILE))
    for c in cookies:
        session.cookies.set(c["name"], c["value"])

    return session

# ================= CATEGORIAS =================

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

    print(f"📂 categorias carregadas: {len(cats)}")
    return cats

# ================= CACHE WOO =================

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

    print(f"⚡ cache Woo: {len(produtos)} produtos")
    return produtos

# ================= PRODUTO =================

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

        if produto_bloqueado(p["produto"]) or produto_bloqueado(p["descricaotecnica"]):
            return None

        return {
            "name": p["produto"],
            "price": f"{float(p['precovenda']):.2f}",
            "stock": int(p["saldo"]),
            "description": p["descricaotecnica"] or "",
            "images": [{"src": img["grande"][0]} for img in p["fotos"]["imagem"]],
            "dep": p["iddepartamento"],
            "subdep": int(p.get("idcategoria")) if p.get("idcategoria") else None
        }

    except Exception as e:
        print("❌ erro produto:", sku, e)
        return None

# ================= WOO =================

def zerar_estoque(sku, cache):
    if sku not in cache:
        return

    r = requests.put(
        f"{URL_WOO}/{cache[sku]}",
        auth=(CK, CS),
        json={"stock_quantity": 0, "stock_status": "outofstock"}
    )

    print("⚡ zerado:", sku, r.status_code)


def enviar(produto, sku, categorias, cache):
    try:
        nome_dep = MAPA_DEPARTAMENTOS.get(produto["dep"])
        sub_nome = MAPA_SUBDEPARTAMENTOS.get(produto["subdep"])

        # ===== DEP =====
        dep_id = None
        for c in categorias:
            if c["name"].strip().upper() == nome_dep.upper() and c["parent"] == 0:
                dep_id = c["id"]
                break

        if not dep_id:
            print("❌ dep não existe:", nome_dep)
            return

        categoria_ids = [{"id": dep_id}]

        # ===== SUB =====
        if sub_nome:
            sub_id = None

            for c in categorias:
                if (
                    c["name"].strip().upper() == sub_nome.upper()
                    and c["parent"] == dep_id
                ):
                    sub_id = c["id"]
                    break

            if not sub_id:
                print("📁 criando sub:", sub_nome)

                r = requests.post(
                    URL_CAT,
                    auth=(CK, CS),
                    json={"name": sub_nome, "parent": dep_id}
                )

                if r.status_code == 201:
                    nova = r.json()
                    sub_id = nova["id"]
                    categorias.append(nova)

            if sub_id:
                categoria_ids.append({"id": sub_id})

        payload = {
            "name": produto["name"],
            "regular_price": produto["price"],
            "sku": sku,
            "stock_quantity": produto["stock"],
            "manage_stock": True,
            "stock_status": "instock",
            "description": produto["description"],
            "images": produto["images"],
            "categories": categoria_ids
        }

        if sku in cache:
            r = requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
            print("♻️ update:", sku, r.status_code)
        else:
            r = requests.post(URL_WOO, auth=(CK, CS), json=payload)
            print("🆕 create:", sku, r.status_code)

    except Exception as e:
        print("❌ erro envio:", sku, e)

# ================= PROCESSAMENTO =================

def processar(row, categorias, cache):
    session = carregar_sessao()

    sku = limpar_sku(str(row["SKU"]))
    print("🔎", sku)

    prod = pegar_produto(session, sku)
    if not prod:
        return

    if prod["stock"] == 0:
        zerar_estoque(sku, cache)
        return

    enviar(prod, sku, categorias, cache)

# ================= EXECUÇÃO =================

categorias = carregar_categorias()
cache = carregar_produtos_woo()

df = pd.read_excel(ARQUIVO)

with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    futures = [
        executor.submit(processar, row, categorias, cache)
        for _, row in df.iterrows()
    ]

    for _ in as_completed(futures):
        pass

print("✅ FINALIZADO")