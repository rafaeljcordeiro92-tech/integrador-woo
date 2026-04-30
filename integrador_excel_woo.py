import requests
import threading
import os
import base64
import json
import time
import random
import re
import urllib3

from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from flask import Flask, jsonify, send_from_directory

# 🔒 DESATIVA WARNING DE SSL (FORNECEDOR COM CERTIFICADO VENCIDO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔥 SESSÃO GLOBAL COM SSL DESATIVADO
session = requests.Session()
session.verify = False

app = Flask(__name__)

# 🇧🇷 HORÁRIO DE BRASÍLIA
BR_TZ = ZoneInfo("America/Sao_Paulo") if ZoneInfo else None
try:
    os.environ["TZ"] = "America/Sao_Paulo"
    if hasattr(time, "tzset"):
        time.tzset()
except Exception:
    pass

def agora_brasilia():
    if BR_TZ:
        return datetime.now(BR_TZ)
    return datetime.now()

# 🔥 CACHE DE IMAGENS (ULTRA PERFORMANCE)
CACHE_IMAGENS = {}

# 🛑 CONTROLE GLOBAL DE PARADA
PARAR = False

# 📦 FILA DE ENVIO EM LOTE (BATCH)
FILA_BATCH = []
BATCH_SIZE = 10

# 🔥 REGRA MDL: abaixo deste saldo no fornecedor, fica ESGOTADO no Woo
ESTOQUE_MINIMO_WOO = 10
# 🔥 Versão da regra para forçar reprocessamento do cache quando mudar regra
VERSAO_REGRA_ESTOQUE = "min10_v3_fora_fornecedor"

# 🔒 Segurança: só marca produtos fora do fornecedor se a lista vier com tamanho mínimo
# Evita zerar produtos por falha temporária/API retornando lista incompleta
MIN_ITENS_FORNECEDOR_PARA_CONFERENCIA = 100

# ⏱️ BLINDAGEM CONTRA TRAVAMENTO NO RAILWAY
# Evita a execução ficar presa em 99% por request sem resposta ou thread travada.
REQUEST_TIMEOUT = 35
ITEM_TIMEOUT = 0  # desativado: não cancela lote inteiro por tempo de item
EXECUCAO_MAX_SEGUNDOS = 3600  # 60 minutos de segurança

# ================= CONFIG =================

CACHE_FILE = "cache_produtos.json"

def carregar_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def salvar_cache(cache):
    if len(cache) > 5000:
        cache = dict(list(cache.items())[-5000:])

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def estoque_woo_por_regra(saldo_fornecedor):
    """
    Regra MDL:
    - Saldo do fornecedor menor que 10 = produto esgotado no WooCommerce
    - Saldo 10 ou maior = mantém saldo real no WooCommerce
    """
    try:
        saldo = int(float(saldo_fornecedor or 0))
    except Exception:
        saldo = 0

    return saldo if saldo >= ESTOQUE_MINIMO_WOO else 0

def gerar_hash(prod):
    estoque_woo = estoque_woo_por_regra(prod.get('stock', 0))
    return f"{VERSAO_REGRA_ESTOQUE}-{prod['price']}-{prod.get('stock',0)}-{estoque_woo}-{len(prod['imagens'])}"

# 🔥 NOVA FUNÇÃO (ULTRA PERFORMANCE)
def gerar_hash_lista(item):
    saldo_fornecedor = item.get('saldo', 0)
    estoque_woo = estoque_woo_por_regra(saldo_fornecedor)
    return f"{VERSAO_REGRA_ESTOQUE}-{item.get('precovenda',0)}-{saldo_fornecedor}-{estoque_woo}"

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

def get_auth_headers():
    token = base64.b64encode(f"{CK}:{CS}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

WP_USER = "admin"
WP_PASS = "UcLe k2Ir ZIdt lVJO 6wtx 2F5H"

def get_wp_headers():
    token = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return {
        "Authorization": f"Basic {token}"
    }

MAX_WORKERS = 4

# ================= UPLOAD IMAGEM (OTIMIZADO) =================

def upload_imagem_wp(url, sku):
    try:
        # 🔥 agora não faz upload — usa direto a URL externa
        if not url:
            return None

        return url

    except Exception as e:
        log(f"⚠️ erro imagem {e}")
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
        # 🔥 GET categoria
        r = requests.get(
            URL_WOO_CAT,
            headers=get_auth_headers(),
            params={"search": nome},
            timeout=REQUEST_TIMEOUT
        )

        if r.status_code != 200:
            log(f"❌ erro categoria {nome} - status {r.status_code} - {r.text[:100]}")
            return None

        # 🔒 proteção JSON
        try:
            data = r.json()
        except:
            log(f"❌ resposta não JSON categoria {nome}: {r.text[:200]}")
            return None

        # 🔍 verifica se já existe
        for cat in data:
            if cat["name"].lower() == nome.lower():
                CACHE_CATEGORIAS[nome] = cat["id"]
                return cat["id"]

        # 🔥 cria categoria
        r = requests.post(
            URL_WOO_CAT,
            headers=get_auth_headers(),
            json={"name": nome},
            timeout=REQUEST_TIMEOUT
        )

        if r.status_code not in [200, 201]:
            log(f"❌ erro criar categoria {nome} - {r.status_code} - {r.text[:100]}")
            return None

        try:
            cat_id = r.json()["id"]
        except:
            log(f"❌ erro JSON ao criar categoria {nome}: {r.text[:200]}")
            return None

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
    LOGS.append(f"{agora_brasilia().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
    if len(LOGS) > 300:
        LOGS.pop(0)

# ================= WOO EXTRA =================

def get_produto_woo(sku):
    try:
        r = requests.get(
            URL_WOO,
            headers=get_auth_headers(),
            params={"sku": sku},
            timeout=REQUEST_TIMEOUT
        )

        if r.status_code != 200:
            log(f"❌ erro buscar produto {sku} - {r.status_code} - {r.text[:100]}")
            return None

        try:
            data = r.json()
        except:
            log(f"❌ resposta inválida produto: {r.text[:200]}")
            return None

        return data[0] if data else None

    except Exception as e:
        log(f"❌ erro get produto {sku}: {e}")
        return None

def deletar_produto_woo(prod_id, sku):
    try:
        r = requests.delete(
            f"{URL_WOO}/{prod_id}",
            headers=get_auth_headers(),
            params={"force": True},
            timeout=REQUEST_TIMEOUT
        )

        if r.status_code not in [200, 204]:
            log(f"❌ erro deletar {sku} - {r.status_code} - {r.text[:100]}")
        else:
            log(f"🗑️ removido do Woo: {sku}")

    except Exception as e:
        log(f"❌ erro ao deletar {sku}: {e}")


def sku_integrador_valido(sku):
    """Considera apenas SKUs gerados pelo integrador: idproduto.idgradex.idgradey"""
    return bool(re.match(r"^\d+\.\d+\.\d+$", str(sku or "").strip()))


def listar_produtos_woo_integrador():
    """Lista produtos do WooCommerce que parecem ter sido criados pelo integrador."""
    produtos = []
    page = 1

    while True:
        try:
            r = requests.get(
                URL_WOO,
                headers=get_auth_headers(),
                params={
                    "per_page": 100,
                    "page": page,
                    "status": "any"
                },
                timeout=REQUEST_TIMEOUT
            )

            if r.status_code != 200:
                log(f"❌ erro listar Woo página {page} - {r.status_code} - {r.text[:150]}")
                break

            data = r.json()
            if not data:
                break

            for prod in data:
                sku = prod.get("sku", "")
                if sku_integrador_valido(sku):
                    produtos.append(prod)

            if len(data) < 100:
                break

            page += 1

        except Exception as e:
            log(f"❌ erro listar produtos Woo: {e}")
            break

    return produtos


def marcar_produto_esgotado_woo(prod_woo, motivo):
    """Atualiza um produto existente no Woo para esgotado."""
    sku = prod_woo.get("sku", "-")
    prod_id = prod_woo.get("id")

    if not prod_id:
        return False

    try:
        payload = {
            "manage_stock": True,
            "stock_quantity": 0,
            "stock_status": "outofstock",
            "backorders": "no"
        }

        r = requests.put(
            f"{URL_WOO}/{prod_id}",
            headers=get_auth_headers(),
            json=payload,
            timeout=REQUEST_TIMEOUT
        )

        if r.status_code not in [200, 201]:
            log(f"❌ erro marcar esgotado {sku} - {r.status_code} - {r.text[:200]}")
            return False

        STATUS["atualizados"] += 1
        LOG_ATUALIZADOS.append(sku)
        log(f"🚫 {sku} marcado como ESGOTADO no Woo | motivo: {motivo}")
        return True

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ erro marcar esgotado {sku}: {e}")
        return False


def marcar_fora_do_fornecedor_como_esgotado(skus_fornecedor, cache):
    """
    Regra MDL:
    Se um SKU criado pelo integrador existe no Woo, mas não veio mais na lista atual do fornecedor,
    ele deve ficar ESGOTADO no WooCommerce.
    """
    if len(skus_fornecedor) < MIN_ITENS_FORNECEDOR_PARA_CONFERENCIA:
        log(
            f"⚠️ conferência fora-fornecedor ignorada: lista fornecedor muito pequena "
            f"({len(skus_fornecedor)} itens). Segurança ativada."
        )
        return

    log("🔎 conferindo produtos que não existem mais no fornecedor...")

    produtos_woo = listar_produtos_woo_integrador()
    total_marcados = 0

    for prod_woo in produtos_woo:
        sku = prod_woo.get("sku", "")

        if sku in skus_fornecedor:
            continue

        estoque_atual = prod_woo.get("stock_quantity")
        status_atual = prod_woo.get("stock_status")

        # Se já está esgotado, não precisa reenviar toda execução
        if status_atual == "outofstock" and (estoque_atual in [0, None, "0"]):
            continue

        if marcar_produto_esgotado_woo(prod_woo, "não veio mais na lista atual do fornecedor"):
            total_marcados += 1
            cache[sku] = f"{VERSAO_REGRA_ESTOQUE}-FORA_FORNECEDOR-ESGOTADO"

    log(f"✅ conferência fora-fornecedor concluída | marcados como esgotado: {total_marcados}")

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

        # 🔒 BLINDAGEM JSON
        try:
            data = r.json()
        except:
            log(f"❌ resposta inválida login: {r.text[:200]}")
            return False

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
            r = session.get(url, timeout=REQUEST_TIMEOUT)

            if r.status_code != 200:
                log(f"❌ erro detalhe status {r.status_code}")
                continue

            # 🔒 BLINDAGEM JSON
            try:
                data = r.json()
            except:
                log(f"❌ resposta inválida detalhe: {r.text[:200]}")
                return None

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
    estoque_fornecedor = int(prod.get("stock", 0))
    estoque_novo = estoque_woo_por_regra(estoque_fornecedor)
    stock_status_novo = "instock" if estoque_novo > 0 else "outofstock"
    imagens_novas = len(prod["imagens"])

    cat_depto_id = get_or_create_category(prod["departamento"]) if prod["departamento"] else None
    cat_sub_id = get_or_create_category(prod["categoria"]) if prod["categoria"] else None

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
            "src": "https://moveisdolar.com.br/wp-content/uploads/2026/04/Sem-imagem-disponivel.png"
        })

    payload = {
        "name": prod["name"],
        "sku": prod["sku"],
        "regular_price": preco_novo,
        "stock_quantity": estoque_novo,
        "manage_stock": True,
        "stock_status": stock_status_novo,
        "backorders": "no",
        "status": "publish",
        "description": prod.get("descricao_tecnica", ""),
        "short_description": prod.get("descricao_curta", ""),
        "categories": categorias,
        "attributes": prod["atributos"]
    }

    # 🔥 só adiciona imagem se for produto novo
    if not prod_id:
        payload["images"] = imagens_upload

    try:
        if prod_id:
            r = requests.put(f"{URL_WOO}/{prod_id}", headers=get_auth_headers(), json=payload, timeout=REQUEST_TIMEOUT)

            if r.status_code not in [200, 201]:
                log(f"❌ erro update {prod['sku']} - {r.status_code} - {r.text[:200]}")
            else:
                STATUS["atualizados"] += 1
                LOG_ATUALIZADOS.append(prod["sku"])

                if estoque_fornecedor < ESTOQUE_MINIMO_WOO:
                    log(f"♻️ {prod['sku']} | 💰 {preco_antigo} → {preco_novo} | 📦 fornecedor {estoque_fornecedor} (<{ESTOQUE_MINIMO_WOO}) → WOO ESGOTADO | 🖼️ {imagens_antigas} → {imagens_novas}")
                else:
                    log(f"♻️ {prod['sku']} | 💰 {preco_antigo} → {preco_novo} | 📦 {estoque_antigo} → {estoque_novo} | 🖼️ {imagens_antigas} → {imagens_novas}")

        else:
            r = requests.post(URL_WOO, headers=get_auth_headers(), json=payload, timeout=REQUEST_TIMEOUT)

            if r.status_code not in [200, 201]:
                log(f"❌ erro criar {prod['sku']} - {r.status_code} - {r.text[:200]}")
            else:
                STATUS["criados"] += 1
                LOG_CRIADOS.append(prod["sku"])

                if estoque_fornecedor < ESTOQUE_MINIMO_WOO:
                    log(f"🆕 {prod['sku']} criado | 💰 {preco_novo} | 📦 fornecedor {estoque_fornecedor} (<{ESTOQUE_MINIMO_WOO}) → WOO ESGOTADO | 🖼️ {imagens_novas}")
                else:
                    log(f"🆕 {prod['sku']} criado | 💰 {preco_novo} | 📦 {estoque_novo} | 🖼️ {imagens_novas}")

        # 👇 MESMO NÍVEL DO IF/ELSE
        cache[prod["sku"]] = hash_atual

    except Exception as e:
        STATUS["erros"] += 1
        log(f"❌ erro {prod['sku']} {e}")


# ================= EXECUTAR =================

def executar():

    global PARAR

    if PARAR:
        log("🛑 execução bloqueada (PARAR ativo)")
        return

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
        "inicio": time.time()
    })

    try:
        if not login():
            return

        r = session.get(BUSCA_URL, timeout=30)

        # 👇 COLE AQUI 👇
        if r.status_code != 200:
            log(f"❌ erro buscar lista - {r.status_code} - {r.text[:100]}")
            return

        # 🔒 BLINDAGEM JSON
        try:
            data = r.json()
        except:
            log(f"❌ resposta inválida lista: {r.text[:200]}")
            return

        lista = data.get("itens", [])

        # SKUs que vieram na lista atual do fornecedor.
        # Usado no fim da execução para marcar como ESGOTADO no Woo
        # tudo que existe no Woo, mas não existe mais no fornecedor.
        skus_fornecedor_atual = {
            f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"
            for item in lista
        }

        STATUS["total"] = len(lista)
        STATUS["processados"] = 0
        STATUS["fila"] = len(lista)

        def processar(item):
            try:
                if PARAR:
                    return

                sku = f"{item['idproduto']}.{item.get('idgradex',0)}.{item.get('idgradey',0)}"

                # 🔥 HASH RÁPIDO
                hash_atual = gerar_hash_lista(item)
                hash_antigo = cache.get(sku)

                if hash_antigo == hash_atual:
                    log(f"⏭️ sem alteração: {sku}")
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

                # 🔥 PREÇO COM REGRA DE DATA
                preco = float(item.get("precovenda", 0))

                if item.get("gabarito"):

                    data_ini = item.get("datainicial_gabarito")
                    data_fim = item.get("datafinal_gabarito")

                    try:
                        hoje = agora_brasilia().date()

                        if data_ini and data_fim:
                            data_ini = datetime.strptime(data_ini, "%d/%m/%Y").date()
                            data_fim = datetime.strptime(data_fim, "%d/%m/%Y").date()

                            if data_ini <= hoje <= data_fim:
                                preco = round(preco * 1.3, 2)
                        else:
                            preco = round(preco * 1.3, 2)

                    except:
                        preco = round(preco * 1.3, 2)

                prod = {
                    "name": detalhe.get("produto"),
                    "sku": sku,
                    "price": preco,
                    "stock": int(item.get("saldo", 0)),
                    "descricao_curta": descricao_curta,
                    "descricao_tecnica": descricao_tecnica,
                    "imagens": imagens,
                    "atributos": atributos,
                    "categoria": categoria,
                    "departamento": departamento
                }

                enviar(prod, cache)

                cache[sku] = hash_atual

                tempo_execucao = time.time() - STATUS["inicio"]

                if tempo_execucao > 0:
                    STATUS["velocidade"] = round(STATUS["processados"] / tempo_execucao, 2)

                if STATUS["velocidade"] > 0:
                    restante = STATUS["total"] - STATUS["processados"]
                    STATUS["tempo_restante"] = int(restante / STATUS["velocidade"])

                time.sleep(random.uniform(0.3, 0.7))

            except Exception as e:
                STATUS["erros"] += 1
                log(f"❌ erro processar item: {e}")

            finally:
                STATUS["processados"] += 1
                STATUS["fila"] -= 1

        execucao_completa = False

        # 🔥 THREAD POOL BLINDADO
        # Não usamos "with" aqui porque, se uma thread travar, o context manager pode ficar esperando
        # para sempre. Com shutdown(wait=False), a execução consegue finalizar e o dashboard reseta.
        ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        futures = []

        try:
            for item in lista:
                if PARAR:
                    log("🛑 execução interrompida pelo usuário")
                    break
                futures.append(ex.submit(processar, item))

            pendentes = set(futures)

            while pendentes and not PARAR:
                tempo_execucao_total = time.time() - STATUS["inicio"]

                if tempo_execucao_total > EXECUCAO_MAX_SEGUNDOS:
                    log(f"⚠️ tempo máximo de execução atingido ({EXECUCAO_MAX_SEGUNDOS}s). Encerrando ciclo sem contar pendentes como erro em massa.")
                    break

                concluidos, pendentes = wait(pendentes, timeout=5, return_when=FIRST_COMPLETED)

                for f in concluidos:
                    try:
                        f.result(timeout=1)
                    except Exception as e:
                        STATUS["erros"] += 1
                        log(f"❌ erro em thread de produto: {e}")

            execucao_completa = (not pendentes and not PARAR)

        finally:
            for f in futures:
                if not f.done():
                    f.cancel()
            ex.shutdown(wait=False, cancel_futures=True)

        if execucao_completa and not PARAR:
            marcar_fora_do_fornecedor_como_esgotado(skus_fornecedor_atual, cache)
        else:
            log("⚠️ conferência fora-fornecedor pulada porque o ciclo não finalizou 100%.")

    except Exception as e:
        log(f"❌ erro geral executar: {e}")

    finally:
        # 🔥 garante que o dashboard não fique preso em rodando
        if STATUS.get("fila", 0) < 0:
            STATUS["fila"] = 0
        if STATUS.get("processados", 0) >= STATUS.get("total", 0) and STATUS.get("total", 0):
            STATUS["processados"] = STATUS["total"]
            STATUS["fila"] = 0

        salvar_cache(cache)
        STATUS["rodando"] = False
        STATUS["tempo_restante"] = 0
        log("✅ finalizado")

# ================= ROTAS =================

@app.route("/")
def dashboard():
    return send_from_directory("dashboard2", "index.html")


@app.route("/status")
def status():
    return jsonify(STATUS)


@app.route("/hora")
def hora():
    return jsonify({"hora_brasilia": agora_brasilia().strftime("%d/%m/%Y, %H:%M:%S")})


@app.route("/logs")
def logs():
    return jsonify(LOGS)


@app.route("/relatorio/atualizados")
def relatorio_atualizados():
    return jsonify(LOG_ATUALIZADOS)


@app.route("/relatorio/criados")
def relatorio_criados():
    return jsonify(LOG_CRIADOS)


# 🚀 EXECUTAR (AGORA CORRIGIDO)
@app.route("/executar")
def executar_manual():
    global PARAR

    if STATUS["rodando"]:
        return jsonify({"status": "já está rodando"})

    # 🔥 RESETA O PARAR AQUI (CORRETO)
    PARAR = False

    thread = threading.Thread(target=executar)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "iniciado"})


# 🛑 PARAR
@app.route("/parar")
def parar():
    global PARAR
    PARAR = True
    return jsonify({"status": "parando"})


# 🔄 RESET (OPCIONAL)
@app.route("/reset")
def reset():
    global STATUS, LOGS, LOG_ATUALIZADOS, LOG_CRIADOS, PARAR

    # 🔥 GARANTE QUE PARA TUDO
    PARAR = True

    STATUS.update({
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
    })

    LOGS.clear()
    LOG_ATUALIZADOS.clear()
    LOG_CRIADOS.clear()

    return jsonify({"status": "resetado"})

# ================= START =================

def loop_automatico():
    while True:
        if not PARAR:
            log("🔄 execução automática iniciando...")
            executar()

        tempo = 1200  # 20 minutos fixo
        log(f"⏳ aguardando {tempo}s (20 minutos)...")
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