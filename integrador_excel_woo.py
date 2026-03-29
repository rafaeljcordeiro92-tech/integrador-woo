import requests
import threading
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

# ================= CONFIG =================

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
BUSCA_URL = BASE + "/produto/getPorCodigoNome/%20/2/272"

EMPRESA = 272
USUARIO = "00905486986"
SENHA = "Rafael2026@"

URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_WOO_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

MAX_WORKERS = 2
session = requests.Session()

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

# ================= CACHE CATEGORIAS =================

CACHE_CATEGORIAS = {}

def get_or_create_category(nome):
    if nome in CACHE_CATEGORIAS:
        return CACHE_CATEGORIAS[nome]

    try:
        r = requests.get(URL_WOO_CAT, auth=(CK, CS), params={"search": nome})
        data = r.json()

        for cat in data:
            if cat["name"].lower() == nome.lower():
                CACHE_CATEGORIAS[nome] = cat["id"]
                return cat["id"]

        r = requests.post(URL_WOO_CAT, auth=(CK, CS), json={"name": nome})
        cat_id = r.json()["id"]

        CACHE_CATEGORIAS[nome] = cat_id
        return cat_id

    except Exception as e:
        log(f"❌ erro categoria {nome}: {e}")
        return None

# ================= STATUS =================

STATUS = {"rodando": False, "total": 0, "atualizados": 0, "criados": 0, "erros": 0}
LOGS = []

def log(msg):
    print(msg)
    LOGS.append(f"{datetime.now()} - {msg}")
    if len(LOGS) > 300:
        LOGS.pop(0)

# ================= WOO EXTRA =================

def get_produto_woo(sku):
    try:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"sku": sku})
        data = r.json()
        return data[0] if data else None
    except:
        return None

# ================= LOGIN =================

def login():
    try:
        r = session.post(LOGIN_URL, json={"cpf": USUARIO, "senha": SENHA, "idempresa": EMPRESA})
        ok = r.json().get("status")
        log("✅ login OK" if ok else "❌ login falhou")
        return ok
    except:
        return False

# ================= DETALHE =================

def get_detalhe(id, x, y):
    try:
        url = f"{BASE}/produto/detalhe/{EMPRESA}/{id}/{x}/{y}"
        r = session.get(url, timeout=20)
        data = r.json()
        return data["itens"][0] if data.get("itens") else None
    except:
        return None

# ================= ENVIAR =================

def enviar(prod):
    prod_woo = get_produto_woo(prod["sku"])
    prod_id = prod_woo["id"] if prod_woo else None

    preco_antigo = prod_woo.get("regular_price") if prod_woo else "-"
    estoque_antigo = prod_woo.get("stock_quantity") if prod_woo else "-"
    imagens_antigas = len(prod_woo.get("images", [])) if prod_woo else 0

    preco_novo = str(prod["price"])
    estoque_novo = int(prod["stock"])
    imagens_novas = len(prod["imagens"])

    cat_depto_id = get_or_create_category(prod["departamento"])
    cat_sub_id = get_or_create_category(prod["categoria"])

    categorias = []
    if cat_depto_id:
        categorias.append({"id": cat_depto_id})
    if cat_sub_id:
        categorias.append({"id": cat_sub_id})

    payload = {
        "name": prod["name"],
        "sku": prod["sku"],
        "regular_price": preco_novo,
        "stock_quantity": estoque_novo,
        "manage_stock": True,
        "stock_status": "instock" if estoque_novo > 0 else "outofstock",
        "status": "publish",
        "description": prod.get("descricao_tecnica", ""),
        "short_description": prod.get("descricao_curta", ""),
        "categories": categorias,
        "images": prod["imagens"],
        "attributes": prod["atributos"]
    }

    try:
        if prod_id:
            requests.put(f"{URL_WOO}/{prod_id}", auth=(CK, CS), json={"images": []})
            requests.put(f"{URL_WOO}/{prod_id}", auth=(CK, CS), json=payload)

            STATUS["atualizados"] += 1

            log(f"♻️ {prod['sku']} | 💰 {preco_antigo} → {preco_novo} | 📦 {estoque_antigo} → {estoque_novo} | 🖼️ {imagens_antigas} → {imagens_novas}")

        else:
            requests.post(URL_WOO, auth=(CK, CS), json=payload)

            STATUS["criados"] += 1

            log(f"🆕 {prod['sku']} criado | 💰 {preco_novo} | 📦 {estoque_novo} | 🖼️ {imagens_novas}")

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ erro {prod['sku']} {e}")

# ================= EXECUTAR =================

def executar():
    STATUS.update({"rodando": True, "atualizados": 0, "criados": 0, "erros": 0})

    if not login():
        STATUS["rodando"] = False
        return

    r = session.get(BUSCA_URL)
    lista = r.json().get("itens", [])
    STATUS["total"] = len(lista)

    def processar(item):

        sku = f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"

        detalhe = get_detalhe(item['idproduto'], item.get('idgradex',0), item.get('idgradey',0))
        if not detalhe:
            return

        id_departamento = detalhe.get("iddepartamento")
        id_categoria = int(detalhe.get("idcategoria", 0))

        departamento = MAPA_DEPARTAMENTOS.get(id_departamento, "GERAL")
        categoria = MAPA_SUBDEPARTAMENTOS.get(id_categoria, "GERAL")

        imagens = []
        for img in detalhe.get("fotos", {}).get("imagem", []):
            for url in img.get("grande", []):
                imagens.append({"src": url})

        descricao_curta = detalhe.get("descricaodetalhada", "")
        descricao_tecnica = detalhe.get("descricaotecnica", "")

        atributos = []

        if detalhe.get("cor"):
            atributos.append({"name": "Cor", "visible": True, "options": [detalhe.get("cor")]})

        if detalhe.get("voltagem"):
            atributos.append({"name": "Voltagem", "visible": True, "options": [detalhe.get("voltagem")]})

        prod = {
            "name": detalhe.get("produto"),
            "sku": sku,
            "price": detalhe.get("precovenda", 0),
            "stock": int(detalhe.get("saldo", 0)),
            "descricao_curta": descricao_curta,
            "descricao_tecnica": descricao_tecnica,
            "imagens": imagens,
            "atributos": atributos,
            "categoria": categoria,
            "departamento": departamento
        }

        enviar(prod)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        ex.map(processar, lista)

    STATUS["rodando"] = False
    log("✅ finalizado")

# ================= ROTAS =================

@app.route("/")
def dashboard():
    return send_from_directory("dashboard", "index.html")

@app.route("/status")
def status():
    return jsonify(STATUS)

@app.route("/logs")
def logs():
    return jsonify(LOGS)

@app.route("/relatorio/atualizados")
def relatorio_atualizados():
    return jsonify(LOG_ATUALIZADOS)

@app.route("/relatorio/criados")
def relatorio_criados():
    return jsonify(LOG_CRIADOS)

@app.route("/executar")
def executar_manual():
    threading.Thread(target=executar).start()
    return "ok"

# ================= START =================

if __name__ == "__main__":
    log("🔥 iniciado")
    PORT = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=PORT)