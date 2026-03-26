import requests
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import threading

# ================= CONFIG =================

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
BUSCA_URL = BASE + "/produto/getPorCodigoNome/%20/2/272"
EMPRESA = 272

USUARIO = "00905486986"
SENHA = "Rafael2026@"

URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

CACHE_FILE = "cache.json"
TIMEOUT = 60
MAX_WORKERS = 2
INTERVALO = 300

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE,
    "Origin": BASE
})

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

def request_com_retry(url, tentativas=3):
    for tentativa in range(tentativas):
        try:
            r = session.get(url, timeout=TIMEOUT)
            return r
        except Exception:
            log(f"⚠️ tentativa {tentativa+1} falhou: {url}")
            time.sleep(2)

    log(f"❌ falhou definitivo: {url}")
    return None

# ================= LOGIN =================

def login():
    try:
        payload = {
            "cpf": USUARIO,
            "senha": SENHA,
            "idempresa": EMPRESA
        }

        r = session.post(LOGIN_URL, json=payload, timeout=TIMEOUT)

        if not r.json().get("status"):
            log("❌ login falhou")
            return False

        log("✅ login OK")
        return True

    except Exception as e:
        log(f"❌ erro login: {e}")
        return False

# ================= BUSCA =================

def buscar_skus():
    log("🔎 buscando SKUs...")

    r = request_com_retry(BUSCA_URL)
    if not r:
        return []

    try:
        data = r.json()
    except:
        return []

    skus = []

    for item in data.get("itens", []):
        idproduto = item.get("idproduto")

        url = f"{BASE}/produto/detalhe/{EMPRESA}/{idproduto}/0/0"
        r2 = request_com_retry(url)

        if not r2:
            continue

        try:
            detalhe = r2.json()["itens"][0]
            grades = detalhe.get("grades", {}).get("itens", [])

            if grades:
                for g in grades:
                    skus.append(f"{idproduto}.{g['grade']}")
            else:
                skus.append(f"{idproduto}.0.0")

        except:
            continue

    log(f"📦 TOTAL SKUS: {len(skus)}")
    return skus

# ================= DETALHE =================

def get_detalhe(sku):
    p = sku.split(".")
    url = f"{BASE}/produto/detalhe/{EMPRESA}/{p[0]}/{p[1]}/{p[2]}"

    r = request_com_retry(url)
    if not r:
        return None

    try:
        return r.json()["itens"][0]
    except:
        return None

# ================= FILTRO =================

def bloqueado(nome):
    palavras = re.sub(r'[^A-Z\s]', ' ', nome.upper()).split()
    return "MM" in palavras

# ================= CACHE =================

def load_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE, "w"))

# ================= WOO =================

def produto_existe(sku):
    try:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"sku": sku}, timeout=TIMEOUT)
        data = r.json()
        if data:
            return data[0]["id"]
        return None
    except:
        return None

def enviar(prod):

    prod_id = produto_existe(prod["sku"])

    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": prod["sku"],
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "categories": [
            {"name": prod["departamento"]},
            {"name": prod["categoria"]}
        ],
        "images": prod["images"]
    }

    try:
        if prod_id:
            requests.put(f"{URL_WOO}/{prod_id}", auth=(CK, CS), json=payload, timeout=TIMEOUT)
            log(f"♻️ atualizado {prod['sku']}")
        else:
            requests.post(URL_WOO, auth=(CK, CS), json=payload, timeout=TIMEOUT)
            log(f"🆕 criado {prod['sku']}")
    except Exception as e:
        log(f"❌ erro envio {prod['sku']}: {e}")

# ================= EXECUÇÃO =================

def executar():

    log("🚀 inicio")

    if not login():
        return

    cache = load_cache()
    skus = buscar_skus()

    def processar(sku):

        data = get_detalhe(sku)
        if not data:
            return

        nome = data["produto"]

        if bloqueado(nome):
            log(f"🚫 bloqueado: {nome}")
            return

        idcat = int(data.get("idcategoria", 0))

        categoria = MAPA_SUBDEPARTAMENTOS.get(idcat, "GERAL")

        departamento = MAPA_DEPARTAMENTOS.get(
            int(str(idcat)[:3] + "0000000"),
            "GERAL"
        )

        prod = {
            "name": nome,
            "price": str(round(float(data["precovenda"]), 2)),
            "sku": sku,
            "stock": int(data["saldo"]),
            "categoria": categoria,
            "departamento": departamento,
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

# ================= LOOP + SERVER =================

app = Flask(__name__)

def loop_principal():
    while True:
        try:
            executar()
        except Exception as e:
            log(f"❌ erro loop: {e}")

        time.sleep(INTERVALO)

@app.route("/")
def home():
    return "Integrador Woo rodando 🚀"

if __name__ == "__main__":
    thread = threading.Thread(target=loop_principal, daemon=True)
    thread.start()

    log("🔥 Loop iniciado")

    app.run(host="0.0.0.0", port=8080)