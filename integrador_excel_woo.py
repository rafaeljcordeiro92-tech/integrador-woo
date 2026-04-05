import requests
import threading
import os
import json
import time
import random
import urllib3

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, send_from_directory

# 🔒 DESATIVA WARNING DE SSL (FORNECEDOR COM CERTIFICADO VENCIDO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔥 SESSÃO GLOBAL COM SSL DESATIVADO
session = requests.Session()
session.verify = False

app = Flask(__name__)

# 🔥 CACHE DE IMAGENS (ULTRA PERFORMANCE)
CACHE_IMAGENS = {}

# ================= CONFIG =================

CACHE_FILE = "cache_produtos.json"

def carregar_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def salvar_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def gerar_hash(prod):
    return f"{prod['price']}-{prod['stock']}-{len(prod['imagens'])}"

# 🔥 NOVA FUNÇÃO (ULTRA PERFORMANCE)
def gerar_hash_lista(item):
    return f"{item.get('precovenda',0)}-{item.get('saldo',0)}"

BASE = "https://portal.juntossomosimbativeis.com.br"
LOGIN_URL = BASE + "/login/parceiro"
BUSCA_URL = BASE + "/produto/getPorCodigoNome/%20/2/272"

EMPRESA = 272
USUARIO = "00905486986"
SENHA = "Rafael2026@"

URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"
URL_WOO_CAT = "https://moveisdolar.com.br/wp-json/wc/v3/products/categories"
URL_MEDIA = "https://moveisdolar.com.br/wp-json/wp/v2/media"  # 🔥 ADICIONADO

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

WP_USER = "admin"
WP_PASS = "UcLe k2Ir ZIdt lVJO 6wtx 2F5H"

MAX_WORKERS = 2

# ================= UPLOAD IMAGEM =================

def upload_imagem_wp(url, sku):

    # 🔥 SE JÁ FOI UPLOAD, USA CACHE
    if url in CACHE_IMAGENS:
        return CACHE_IMAGENS[url]

    for tentativa in range(3):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}

            r = requests.get(url, headers=headers, timeout=30)

            if r.status_code != 200:
                log(f"❌ erro download imagem {url}")
                continue

            nome = f"{sku}.jpg"

            files = {
                "file": (nome, r.content, "image/jpeg")
            }

            headers_upload = {
                "Content-Disposition": f"attachment; filename={nome}"
            }

            r2 = requests.post(
                URL_MEDIA,
                auth=(WP_USER, WP_PASS),
                headers=headers_upload,
                files=files,
                timeout=30
            )

            if r2.status_code in [200, 201]:
                url_wp = r2.json().get("source_url")

                # 🔥 SALVA CACHE
                CACHE_IMAGENS[url] = url_wp

                return url_wp
            else:
                log(f"❌ erro upload WP - {r2.text}")

        except Exception as e:
            log(f"⚠️ erro upload imagem {e}")

    return None

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

STATUS = {
    "rodando": False,
    "total": 0,
    "processados": 0,
    "atualizados": 0,
    "criados": 0,
    "erros": 0,
    "fila": 0,
    "inicio": None,
    "velocidade": 0,
    "tempo_restante": 0
}

LOGS = []
LOG_ATUALIZADOS = []
LOG_CRIADOS = []

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

def deletar_produto_woo(prod_id, sku):
    try:
        requests.delete(f"{URL_WOO}/{prod_id}", auth=(CK, CS), params={"force": True})
        log(f"🗑️ removido do Woo: {sku}")
    except Exception as e:
        log(f"❌ erro ao deletar {sku}: {e}")

# ================= FILTRO =================

def deve_bloquear(nome):
    nome_upper = nome.upper()

    if "BEM MM" in nome_upper:
        return True

    if "CHIP" in nome_upper:
        return True

    palavras = nome_upper.split()
    if "MM" in palavras:
        return True

    return False

# ================= LOGIN =================

def login():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "cpf": "00905486986",
            "senha": "Rafael2026@",
            "idempresa": 272
        }

        r = session.post(
            LOGIN_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        log(f"📡 login status code: {r.status_code}")
        log(f"📡 resposta login: {r.text[:200]}")

        if r.status_code != 200:
            log("❌ login falhou (status != 200)")
            return False

        data = r.json()
        ok = data.get("status")

        if ok:
            log("✅ login OK")
            return True
        else:
            log("❌ login inválido (status false)")
            return False

    except Exception as e:
        log(f"❌ erro login: {e}")
        return False

# ================= DETALHE =================

def get_detalhe(id, x, y):
    url = f"{BASE}/produto/detalhe/{EMPRESA}/{id}/{x}/{y}"

    for tentativa in range(3):
        try:
            r = session.get(url, timeout=40)

            if r.status_code != 200:
                log(f"❌ erro detalhe status {r.status_code}")
                continue

            data = r.json()

            if not data.get("itens"):
                return None

            return data["itens"][0]

        except Exception as e:
            log(f"⚠️ tentativa {tentativa+1} erro detalhe: {e}")
            time.sleep(2)

    log(f"❌ falhou detalhe {id}")
    return None

# ================= ENVIAR =================

def enviar(prod, cache):

    hash_atual = gerar_hash(prod)
    hash_antigo = cache.get(prod["sku"])

    if hash_antigo == hash_atual:
        log(f"⏭️ sem alteração: {prod['sku']}")
        return

    if deve_bloquear(prod["name"]):
        prod_woo = get_produto_woo(prod["sku"])
        if prod_woo:
            deletar_produto_woo(prod_woo["id"], prod["sku"])
        log(f"🚫 bloqueado: {prod['sku']} - {prod['name']}")
        return

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

    # 🔥 IMAGENS
    imagens_upload = []

    for img in prod["imagens"]:
        url_wp = upload_imagem_wp(img["src"], prod["sku"])
        if url_wp:
            imagens_upload.append({"src": url_wp})

    # 🔥 SE NÃO TIVER NENHUMA IMAGEM, USA PADRÃO
    if not imagens_upload:
        imagens_upload.append({
            "src": "https://via.placeholder.com/600x600.jpg"
        })

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
        "images": imagens_upload,
        "attributes": prod["atributos"]
    }

    try:
        if prod_id:
            r = requests.post(f"{URL_WOO}/{prod_id}", auth=(CK, CS), json=payload)

            if r.status_code not in [200, 201]:
                log(f"❌ erro update {prod['sku']} - {r.status_code} - {r.text[:200]}")
            else:
                STATUS["atualizados"] += 1
                LOG_ATUALIZADOS.append(prod["sku"])

                log(f"♻️ {prod['sku']} | 💰 {preco_antigo} → {preco_novo} | 📦 {estoque_antigo} → {estoque_novo} | 🖼️ {imagens_antigas} → {imagens_novas}")

        else:
            r = requests.post(URL_WOO, auth=(CK, CS), json=payload)

            if r.status_code not in [200, 201]:
                log(f"❌ erro criar {prod['sku']} - {r.status_code} - {r.text[:200]}")
            else:
                STATUS["criados"] += 1
                LOG_CRIADOS.append(prod["sku"])

                log(f"🆕 {prod['sku']} criado | 💰 {preco_novo} | 📦 {estoque_novo} | 🖼️ {imagens_novas}")

        # 👇 MESMO NÍVEL DO IF/ELSE
        cache[prod["sku"]] = hash_atual

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ erro {prod['sku']} {e}")


# ================= EXECUTAR =================

def executar():

    # 🔒 PROTEÇÃO CONTRA DUPLICAÇÃO
    if STATUS["rodando"]:
        log("⚠️ já está rodando, ignorando execução")
        return

    cache = carregar_cache()

    STATUS.update({
        "rodando": True,
        "atualizados": 0,
        "criados": 0,
        "erros": 0,
        "inicio": datetime.now().timestamp()
    })

    try:
        if not login():
            return

        r = session.get(BUSCA_URL, timeout=30)
        lista = r.json().get("itens", [])

        STATUS["total"] = len(lista)
        STATUS["processados"] = 0
        STATUS["fila"] = len(lista)

        # 🔥 FUNÇÃO CORRETA DENTRO DO EXECUTAR
        def processar(item):
            try:
                sku = f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"

                # 🔥 HASH RÁPIDO
                hash_atual = gerar_hash_lista(item)
                hash_antigo = cache.get(sku)

                if hash_antigo == hash_atual:
                    log(f"⏭️ sem alteração: {sku}")

                    STATUS["processados"] += 1
                    STATUS["fila"] -= 1
                    return

                detalhe = get_detalhe(
                    item['idproduto'],
                    item.get('idgradex',0),
                    item.get('idgradey',0)
                )

                if not detalhe:
                    STATUS["erros"] += 1
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
                    atributos.append({
                        "name": "Cor",
                        "visible": True,
                        "options": [detalhe.get("cor")]
                    })

                if detalhe.get("voltagem"):
                    atributos.append({
                        "name": "Voltagem",
                        "visible": True,
                        "options": [detalhe.get("voltagem")]
                    })

                prod = {
                    "name": detalhe.get("produto"),
                    "sku": sku,
                    "price": item.get("precovenda", 0),
                    "stock": int(item.get("saldo", 0)),
                    "descricao_curta": descricao_curta,
                    "descricao_tecnica": descricao_tecnica,
                    "imagens": imagens,
                    "atributos": atributos,
                    "categoria": categoria,
                    "departamento": departamento
                }

                enviar(prod, cache)

                # 🔥 salva hash leve
                cache[sku] = hash_atual

                STATUS["processados"] += 1
                STATUS["fila"] -= 1

                tempo_execucao = datetime.now().timestamp() - STATUS["inicio"]

                if tempo_execucao > 0:
                    STATUS["velocidade"] = round(STATUS["processados"] / tempo_execucao, 2)

                if STATUS["velocidade"] > 0:
                    restante = STATUS["total"] - STATUS["processados"]
                    STATUS["tempo_restante"] = int(restante / STATUS["velocidade"])

                time.sleep(random.uniform(0.3, 0.8))

            except Exception as e:
                STATUS["erros"] += 1
                log(f"❌ erro processar item: {e}")

        # 🔥 THREAD POOL (FALTAVA ISSO)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            ex.map(processar, lista)

    except Exception as e:
        log(f"❌ erro geral executar: {e}")

    finally:
        salvar_cache(cache)
        STATUS["rodando"] = False
        log("✅ finalizado")

# ================= ROTAS =================

@app.route("/")
def dashboard():
    return send_from_directory("dashboard2", "index.html")

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
    if STATUS["rodando"]:
        return "já está rodando"

    threading.Thread(target=executar).start()
    return "ok"

# ================= START =================

def loop_automatico():
    while True:
        log("🔄 execução automática iniciando...")
        executar()

        tempo = random.randint(1800, 3600)  # 30 a 60 min
        log(f"⏳ aguardando {tempo}s...")
        time.sleep(tempo)


def iniciar_loop():
    # 🔒 garante que só inicia uma vez por processo
    if getattr(iniciar_loop, "iniciado", False):
        return

    iniciar_loop.iniciado = True

    log("🚀 iniciando loop automático...")
    threading.Thread(target=loop_automatico, daemon=True).start()


# 👇 ESSENCIAL: inicia automaticamente no Railway (Gunicorn)
iniciar_loop()


if __name__ == "__main__":
    log("🔥 iniciado")

    PORT = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=PORT)