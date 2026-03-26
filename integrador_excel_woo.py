import requests
import time
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================

URL = "https://portal.juntossomosimbativeis.com.br"
URL_WOO = "https://moveisdolar.com.br/wp-json/wc/v3/products"

CK = "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293"
CS = "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f"

TIMEOUT = 20
MAX_WORKERS = 5

CACHE_FILE = "cache_local.json"
DASH_FILE = "dashboard.json"

# ================= LOG =================

def log(msg):
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ================= CACHE =================

def carregar_cache():
    try:
        return json.load(open(CACHE_FILE))
    except:
        return {}

def salvar_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w"))

# ================= FILTRO =================

def produto_bloqueado(nome):
    texto = re.sub(r'[^A-Z\s]', ' ', nome.upper())
    palavras = texto.split()

    for i, p in enumerate(palavras):
        if p == "MM":
            return True
        if p == "BEM" and i+1 < len(palavras) and palavras[i+1] == "MM":
            return True
    return False

# ================= WOO =================

def get_produtos():
    produtos = {}
    page = 1

    while True:
        r = requests.get(URL_WOO, auth=(CK, CS), params={"per_page":100,"page":page})
        if r.status_code != 200:
            break

        data = r.json()
        if not data:
            break

        for p in data:
            produtos[p["sku"]] = p["id"]

        page += 1

    return produtos

# ================= NOVA API =================

def get_todos_produtos():
    produtos = []
    pagina = 1
    MAX_PAGINAS = 20

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    while pagina <= MAX_PAGINAS:
        url = f"{URL}/produto/getPorCodigoNome/%20/{pagina}/272"

        r = requests.get(url, headers=headers, timeout=TIMEOUT)

        if r.status_code != 200:
            log(f"❌ erro página {pagina}")
            break

        try:
            data = r.json()
        except:
            log("❌ erro ao converter JSON")
            break

        # 🔥 leitura inteligente (resolve seu problema)
        if isinstance(data, list):
            itens = data
        else:
            itens = data.get("itens") or data.get("data") or data.get("produtos") or []

        if not itens:
            log(f"⚠️ página {pagina} sem itens")
            break

        produtos.extend(itens)

        log(f"📄 página {pagina} | total {len(produtos)}")

        pagina += 1

    log(f"📊 total fornecedor: {len(produtos)}")
    return produtos

# ================= ENVIO =================

def enviar(prod, sku, cache):
    payload = {
        "name": prod["name"],
        "regular_price": prod["price"],
        "sku": sku,
        "stock_quantity": prod["stock"],
        "manage_stock": True,
        "images": prod["images"]
    }

    if sku in cache:
        requests.put(f"{URL_WOO}/{cache[sku]}", auth=(CK, CS), json=payload)
        log(f"♻️ atualização: {sku}")
    else:
        requests.post(URL_WOO, auth=(CK, CS), json=payload)
        log(f"🆕 criação: {sku}")

# ================= EXECUÇÃO =================

def executar():
    log("🚀 ciclo iniciado")

    cache = get_produtos()
    cache_local = carregar_cache()

    produtos = get_todos_produtos()

    dashboard = {
        "total": len(produtos),
        "processados": 0,
        "novos": 0,
        "atualizados": 0,
        "erros": 0,
        "produtos": []
    }

    def processar(p):
        try:
            sku = p.get("codigo") or p.get("sku")
            nome = p.get("produto") or p.get("nome")

            if not sku or not nome:
                return

            if produto_bloqueado(nome):
                return

            prod = {
                "name": nome,
                "price": str(round(float(p.get("precovenda", 0)), 2)),
                "stock": int(p.get("saldo", 0)),
                "images": []
            }

            for img in p.get("fotos", {}).get("imagem", []):
                if img.get("grande"):
                    prod["images"].append({"src": img["grande"][0]})

            antigo = cache_local.get(sku)

            mudou_preco = antigo and antigo["price"] != prod["price"]
            mudou_estoque = antigo and antigo["stock"] != prod["stock"]

            if sku not in cache:
                status = "novo"
                dashboard["novos"] += 1

            elif mudou_preco or mudou_estoque:
                status = "atualizado"
                dashboard["atualizados"] += 1

            else:
                status = "igual"

            if status in ["novo", "atualizado"]:
                enviar(prod, sku, cache)

            dashboard["produtos"].append({
                "sku": sku,
                "nome": nome,
                "status": status,
                "preco_antigo": antigo["price"] if antigo else None,
                "preco_novo": prod["price"],
                "estoque_antigo": antigo["stock"] if antigo else None,
                "estoque_novo": prod["stock"]
            })

            cache_local[sku] = {
                "price": prod["price"],
                "stock": prod["stock"]
            }

        except Exception as e:
            dashboard["erros"] += 1
            log(f"❌ erro {p}: {e}")

        finally:
            dashboard["processados"] += 1
            dashboard["percentual"] = round(
                (dashboard["processados"] / dashboard["total"]) * 100, 2
            )

            with open(DASH_FILE, "w", encoding="utf-8") as f:
                json.dump(dashboard, f, indent=2, ensure_ascii=False)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(processar, produtos)

    salvar_cache(cache_local)

    log("✅ ciclo finalizado")

# ================= START =================

if __name__ == "__main__":
    executar()