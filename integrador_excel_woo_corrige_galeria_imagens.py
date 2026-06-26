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
from flask import Flask, jsonify, send_from_directory, Response

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
VERSAO_REGRA_ESTOQUE = "min10_v3_fora_fornecedor_img_dedup_v5"

# 🔒 Segurança: só marca produtos fora do fornecedor se a lista vier com tamanho mínimo
# Evita zerar produtos por falha temporária/API retornando lista incompleta
MIN_ITENS_FORNECEDOR_PARA_CONFERENCIA = 100

# ⏱️ BLINDAGEM CONTRA TRAVAMENTO NO RAILWAY
# Evita a execução ficar presa em 99% por request sem resposta ou thread travada.
REQUEST_TIMEOUT = 35
VERIFY_SSL_WOO = False  # 🔒 desativa validação SSL nas chamadas do WooCommerce
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


# ================= WOO REQUESTS COM SSL DESATIVADO =================
def woo_get(url, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("verify", VERIFY_SSL_WOO)
    return requests.get(url, **kwargs)

def woo_post(url, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("verify", VERIFY_SSL_WOO)
    return requests.post(url, **kwargs)

def woo_put(url, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("verify", VERIFY_SSL_WOO)
    return requests.put(url, **kwargs)

def woo_delete(url, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("verify", VERIFY_SSL_WOO)
    return requests.delete(url, **kwargs)

MAX_WORKERS = 4

# ================= TELEGRAM ALERTAS =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_ALERTAS_ATIVOS = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
TELEGRAM_ULTIMO_ALERTA = 0
TELEGRAM_INTERVALO_MINIMO = 300  # 5 minutos para não lotar o Telegram

def enviar_telegram(mensagem, forcar=False):
    """
    Envia mensagem para o Telegram.
    - Usa variáveis do Railway:
      TELEGRAM_BOT_TOKEN
      TELEGRAM_CHAT_ID
    """
    global TELEGRAM_ULTIMO_ALERTA

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado: faltam TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID")
        return False

    agora = time.time()

    if not forcar and (agora - TELEGRAM_ULTIMO_ALERTA) < TELEGRAM_INTERVALO_MINIMO:
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": str(mensagem)[:3900],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        r = requests.post(url, json=payload, timeout=15)

        if r.status_code == 200:
            TELEGRAM_ULTIMO_ALERTA = agora
            return True

        print(f"⚠️ falha Telegram status {r.status_code}: {r.text[:300]}")
        return False

    except Exception as e:
        print(f"⚠️ erro ao enviar Telegram: {e}")
        return False


def alerta_telegram_erro(msg):
    """
    Envia alerta apenas para erros reais, com trava anti-spam.
    Avisos de imagem ignorada não entram aqui.
    """
    texto = str(msg)

    ignorar = [
        "imagem ignorada",
        "URL não encontrada",
        "sem imagem válida"
    ]

    if any(p.lower() in texto.lower() for p in ignorar):
        return

    mensagem = (
        "🚨 <b>Erro no Integrador Woo MDL</b>\n\n"
        f"🕒 {agora_brasilia().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"⚠️ {texto[:1200]}\n\n"
        "🔗 Painel: https://integrador-woo-production.up.railway.app"
    )

    enviar_telegram(mensagem, forcar=False)



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

def normalizar_url_imagem(valor):
    """
    Normaliza imagens do fornecedor sem multiplicar galeria.

    Correção MDL V5:
    - Quando o fornecedor manda a mesma foto em tamanhos diferentes
      (grande/media/pequena ou 600_/300_/100_), usamos APENAS uma versão.
    - Preferência: grande/600_ > media/300_ > pequena/100_.
    - Evita duplicar /Catalogo/600_/Catalogo/600_/.
    - Retorna sempre lista de URLs strings.
    """
    if valor is None:
        return []

    if isinstance(valor, list):
        urls = []
        for item in valor:
            urls.extend(normalizar_url_imagem(item))
        return urls

    if isinstance(valor, dict):
        # IMPORTANTE: não varrer todas as chaves, senão pega grande+media+pequena
        # e triplica as imagens no Woo. Usa só a melhor disponível.
        for chave in ["grande", "src", "url", "media", "pequena", "arquivo", "nome", "imagem"]:
            if chave in valor and valor.get(chave):
                urls = normalizar_url_imagem(valor.get(chave))
                if urls:
                    return urls
        return []

    if not isinstance(valor, str):
        return []

    src = valor.strip().replace("\\", "/")

    if not src or src.lower() in ["none", "null", "undefined", "false"]:
        return []

    # Se vier uma URL de 100_ ou 300_, tenta priorizar 600_ para não mandar 3 tamanhos.
    src = re.sub(r"/Catalogo/(100_|300_)/", "/Catalogo/600_/", src, flags=re.IGNORECASE)

    # Evita duplicação de caminho gerada por retorno estranho.
    src = src.replace("/Catalogo/600_/Catalogo/600_/", "/Catalogo/600_/")
    src = src.replace("Catalogo/600_/Catalogo/600_/", "Catalogo/600_/")

    src_limpo = src.lstrip("/")

    if src.startswith("http://") or src.startswith("https://"):
        return [src]

    if src_limpo.lower().startswith("files/catalogo/"):
        return [BASE + "/" + src_limpo]

    if src_limpo.lower().startswith("catalogo/"):
        return [BASE + "/files/" + src_limpo]

    if re.search(r"\.(jpg|jpeg|png|webp)$", src_limpo, re.IGNORECASE):
        return [f"{BASE}/files/Catalogo/600_/{src_limpo}"]

    return []

def url_imagem_existe(url):
    """Confere rapidamente se a URL da imagem responde antes de mandar para o Woo."""
    try:
        r = session.get(url, timeout=12, stream=True)
        content_type = r.headers.get("Content-Type", "").lower()
        return r.status_code == 200 and ("image" in content_type or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    except Exception:
        return False

def coletar_imagens_detalhe(detalhe, sku):
    """
    Coleta imagens reais do fornecedor sem repetir tamanhos.

    Regra: cada foto do fornecedor vira no máximo 1 imagem no Woo.
    Se a foto vier em 600_/300_/100_, fica somente a versão 600_.
    """
    urls = []

    fotos = detalhe.get("fotos", {}) if isinstance(detalhe, dict) else {}
    imagens_raw = fotos.get("imagem", []) if isinstance(fotos, dict) else []

    urls.extend(normalizar_url_imagem(imagens_raw))

    urls_unicas = []
    vistos = set()

    for url in urls:
        if not url or not isinstance(url, str):
            continue

        # Normaliza para 600_ para comparar e evitar 600/300/100 da mesma foto.
        url_norm = re.sub(r"/Catalogo/(100_|300_)/", "/Catalogo/600_/", url, flags=re.IGNORECASE)
        url_norm = url_norm.replace("/Catalogo/600_/Catalogo/600_/", "/Catalogo/600_/")

        chave = url_norm.lower()
        if chave in vistos:
            continue

        vistos.add(chave)
        urls_unicas.append(url_norm)

    if not urls_unicas:
        fallback = f"{BASE}/files/Catalogo/600_/{sku}.1.JPG"
        if url_imagem_existe(fallback):
            urls_unicas.append(fallback)
        else:
            log(f"⚠️ {sku} sem imagem válida no fornecedor")

    return [{"src": url} for url in urls_unicas]


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
        r = woo_get(
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
        r = woo_post(
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

    # Telegram: envia alerta somente para erros críticos, com trava anti-spam.
    try:
        if str(msg).strip().startswith("❌"):
            alerta_telegram_erro(msg)
    except Exception as e:
        print(f"⚠️ falha alerta Telegram no log: {e}")

# ================= WOO EXTRA =================

def get_produto_woo(sku):
    try:
        r = woo_get(
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
        r = woo_delete(
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
            r = woo_get(
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

        r = woo_put(
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

    # 🔥 IMAGENS - BLINDADO
    imagens_upload = []

    for img in prod["imagens"]:
        try:
            src = img.get("src") if isinstance(img, dict) else img
            urls_validas = normalizar_url_imagem(src)

            for url in urls_validas:
                url_wp = upload_imagem_wp(url, prod["sku"])
                if not (url_wp and isinstance(url_wp, str) and url_wp.startswith("http")):
                    continue

                # Confere se a imagem existe antes de mandar para o Woo.
                # Evita erro 400: woocommerce_product_image_upload_error / Not Found.
                if not url_imagem_existe(url_wp):
                    log(f"⚠️ imagem ignorada {prod['sku']} - URL não encontrada: {url_wp}")
                    continue

                imagens_upload.append({"src": url_wp})

        except Exception as e:
            log(f"⚠️ imagem ignorada {prod['sku']} - erro: {e}")

    # remove duplicadas para não enviar imagem repetida ao Woo
    imagens_sem_duplicar = []
    urls_ja_usadas = set()
    for img in imagens_upload:
        src = img.get("src")
        if src and src not in urls_ja_usadas:
            imagens_sem_duplicar.append(img)
            urls_ja_usadas.add(src)
    imagens_upload = imagens_sem_duplicar

    imagens_novas = len(imagens_upload)

    if not imagens_upload:
        log(f"⚠️ {prod['sku']} sem imagem válida para enviar ao Woo")

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

    # 🔥 GALERIA DEFINITIVA
    # Produto novo: envia imagens obrigatoriamente.
    # Produto existente: se a quantidade no Woo estiver diferente da quantidade real do fornecedor,
    # envia a galeria completa para substituir e limpar duplicadas antigas.
    # Isso corrige casos como 5 → 15, 3 → 9, 14 → 42.
    if imagens_upload and (not prod_id or imagens_antigas != imagens_novas):
        payload["images"] = imagens_upload

    # MDL: produto novo sem imagem válida não será criado, para não poluir o site com produto sem foto.
    if not prod_id and not imagens_upload:
        log(f"🚫 não criado {prod['sku']} - sem imagem válida no fornecedor")
        return

    try:
        if prod_id:
            r = woo_put(f"{URL_WOO}/{prod_id}", headers=get_auth_headers(), json=payload, timeout=REQUEST_TIMEOUT)

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
            r = woo_post(URL_WOO, headers=get_auth_headers(), json=payload, timeout=REQUEST_TIMEOUT)

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

                imagens = coletar_imagens_detalhe(detalhe, sku)

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
        erros_ciclo = STATUS.get("erros", 0)

        STATUS["rodando"] = False
        STATUS["tempo_restante"] = 0

        if erros_ciclo and erros_ciclo > 0:
            enviar_telegram(
                "⚠️ <b>Integrador Woo MDL finalizou com erros</b>\n\n"
                f"🕒 {agora_brasilia().strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"❌ Erros no ciclo: {erros_ciclo}\n"
                f"📦 Processados: {STATUS.get('processados', 0)} / {STATUS.get('total', 0)}\n"
                f"♻️ Atualizados: {STATUS.get('atualizados', 0)}\n"
                f"🆕 Criados: {STATUS.get('criados', 0)}\n\n"
                "🔗 Painel: https://integrador-woo-production.up.railway.app",
                forcar=True
            )

        log("✅ finalizado")

# ================= ROTAS =================

@app.route("/")
def dashboard():
    """
    Carrega o dashboard e injeta automaticamente o botão de teste do Telegram,
    sem precisar editar o arquivo dashboard2/index.html.
    """
    try:
        caminho = os.path.join(app.root_path, "dashboard2", "index.html")

        with open(caminho, "r", encoding="utf-8") as f:
            html = f.read()

        botao_telegram_js = """
<script>
document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("btn-testar-telegram-mdl")) return;

    const btn = document.createElement("button");
    btn.id = "btn-testar-telegram-mdl";
    btn.innerHTML = "📨 Testar Telegram";
    btn.style.background = "#229ED9";
    btn.style.color = "#fff";
    btn.style.border = "0";
    btn.style.borderRadius = "8px";
    btn.style.padding = "10px 16px";
    btn.style.fontWeight = "700";
    btn.style.cursor = "pointer";
    btn.style.marginLeft = "10px";
    btn.style.boxShadow = "0 4px 12px rgba(0,0,0,.18)";

    btn.onclick = async function () {
        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = "⏳ Enviando...";

        try {
            const r = await fetch("/testar-telegram");
            const data = await r.json();

            if (data.ok) {
                alert("✅ Mensagem de teste enviada no Telegram!");
            } else {
                alert("❌ Falha ao enviar Telegram: " + (data.erro || data.status || "verifique as variáveis no Railway"));
            }
        } catch (e) {
            alert("❌ Erro ao testar Telegram: " + e);
        }

        btn.innerHTML = original;
        btn.disabled = false;
    };

    const botoes = Array.from(document.querySelectorAll("button, a"));
    const botaoParar = botoes.find(el => (el.textContent || "").toLowerCase().includes("parar"));
    const botaoExecutar = botoes.find(el => (el.textContent || "").toLowerCase().includes("executar"));

    if (botaoParar && botaoParar.parentElement) {
        botaoParar.insertAdjacentElement("afterend", btn);
    } else if (botaoExecutar && botaoExecutar.parentElement) {
        botaoExecutar.insertAdjacentElement("afterend", btn);
    } else {
        document.body.prepend(btn);
    }
});
</script>
"""

        if "</body>" in html:
            html = html.replace("</body>", botao_telegram_js + "\n</body>")
        else:
            html += botao_telegram_js

        return Response(html, mimetype="text/html")

    except Exception as e:
        print(f"⚠️ falha ao injetar botão Telegram: {e}")
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



@app.route("/testar-telegram")
def testar_telegram():
    ok = enviar_telegram(
        "✅ <b>Teste Telegram MDL</b>\n\n"
        f"Mensagem enviada pelo integrador em {agora_brasilia().strftime('%d/%m/%Y %H:%M:%S')}.\n"
        "Se você recebeu esta mensagem, o alerta está funcionando.",
        forcar=True
    )

    if ok:
        return jsonify({"ok": True, "status": "mensagem enviada"})

    return jsonify({
        "ok": False,
        "erro": "Falha ao enviar. Confira TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no Railway e faça Redeploy."
    }), 500


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