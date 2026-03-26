import requests
import time
import json
import random
import re
from datetime import datetime
from stats import registrar_evento
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"

CK = "ck_..."
CS = "cs_..."

COOKIE_FILE = "cookies.json"

SKUS_POR_CICLO = 120

DELAY_MIN = 0.3
DELAY_MAX = 1.0

MAX_WORKERS = 3  # 🔥 ESTÁVEL
TIMEOUT = 20

CACHE_FILE = "cache_local.json"

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= RETRY =================

def request_com_retry(method, url, **kwargs):
    for tentativa in range(3):
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.ReadTimeout:
            log(f"⚠️ timeout, retry {tentativa+1}...")
            time.sleep(2)
    return None

# ================= SKU =================

def limpar_sku_url(sku):
    return re.sub(r"[^0-9.]", "", str(sku)).strip()

# ================= FILTRO =================

def produto_bloqueado(prod):
    nome = prod.get("name", "")
    texto = re.sub(r'[^A-Z\s]', ' ', nome.upper())
    palavras = texto.split()

    for i, p in enumerate(palavras):
        if p == "MM":
            return True
        if p == "BEM" and i + 1 < len(palavras) and palavras[i + 1] == "MM":
            return True

    return False

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

# ================= RESTO (RESUMIDO) =================
# ⚠️ MANTIVE SUA LÓGICA — SÓ ALTEREI REQUESTS

def pegar(session, sku_limpo):
    try:
        url = f"{URL}/produto/detalhe/272/{'/'.join(sku_limpo.split('.')[:3])}"
        r = request_com_retry("GET", url, timeout=TIMEOUT)
        if not r or r.status_code != 200:
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
        log(f"❌ erro produto {sku_limpo}: {e}")
        return None

def enviar(prod, sku, cache):
    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": sku,
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "images": prod["images"],
        "description": prod["descricao"],
    }

    try:
        if sku in cache:
            request_com_retry("PUT", f"{URL_WOO}/{cache[sku]}", json=payload, auth=(CK, CS), timeout=TIMEOUT)
            log(f"♻️ atualização: {sku}")
        else:
            request_com_retry("POST", URL_WOO, json=payload, auth=(CK, CS), timeout=TIMEOUT)
            log(f"🆕 criação: {sku}")
    except Exception as e:
        log(f"❌ erro envio: {sku} - {e}")

def executar():
    log("🚀 ciclo iniciado")

    cache = {}
    skus = list(cache.keys())

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(lambda sku: processar(sku, cache), skus[:SKUS_POR_CICLO])

    log("✅ ciclo finalizado")