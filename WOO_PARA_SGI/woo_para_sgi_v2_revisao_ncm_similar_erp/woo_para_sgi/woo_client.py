# -*- coding: utf-8 -*-
import json
import time
from pathlib import Path
from typing import Dict, List

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    WOO_BASE_URL,
    WOO_CONSUMER_KEY,
    WOO_CONSUMER_SECRET,
    WOO_API_VERSION,
    WOO_STATUS,
    CACHE_DIR,
)
from logger_app import log
from normalizador import limpar_html, extrair_marca, escolher_subgrupo, montar_nome_sgi_com_detalhes, extrair_cor_voltagem_attrs

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WOO_CACHE_FILE = CACHE_DIR / "ultimo_woo_produtos.json"


def _woo_url(path: str) -> str:
    base = WOO_BASE_URL.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/wp-json/{WOO_API_VERSION}/{path}"


def testar_config_woo() -> None:
    if not WOO_CONSUMER_KEY or not WOO_CONSUMER_SECRET:
        raise RuntimeError("Configure WOO_CONSUMER_KEY e WOO_CONSUMER_SECRET nas variáveis de ambiente ou no config.py.")


def _criar_sessao_woo() -> requests.Session:
    """Sessão com retry para aguentar instabilidade/timeout SSL do site."""
    sess = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=2,
        status_forcelist=[408, 429, 500, 502, 503, 504, 520, 522, 524],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.headers.update({
        "User-Agent": "MDL-Woo-SGI/1.0 (+https://moveisdolar.com.br)",
        "Accept": "application/json",
        "Connection": "close",
    })
    return sess


def _salvar_cache_woo(produtos: List[Dict]) -> None:
    try:
        WOO_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WOO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(produtos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"⚠️ Não consegui salvar cache Woo: {e}")


def _carregar_cache_woo(limite: int) -> List[Dict]:
    try:
        if not WOO_CACHE_FILE.exists():
            return []
        with open(WOO_CACHE_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, list):
            return []
        log(f"♻️ Usando cache local do WooCommerce: {min(len(dados), limite)} produtos.")
        return dados[:limite]
    except Exception as e:
        log(f"⚠️ Não consegui ler cache Woo: {e}")
        return []


def buscar_produtos(limite: int = 5) -> List[Dict]:
    testar_config_woo()
    produtos: List[Dict] = []
    page = 1
    per_page = min(max(limite, 1), 25)  # menor para reduzir peso/timeout
    sess = _criar_sessao_woo()

    # Campos reduzidos para a consulta ficar leve. Mantém o necessário para SGI.
    campos = ",".join([
        "id", "name", "sku", "short_description", "description", "categories",
        "images", "attributes", "dimensions", "weight", "permalink"
    ])

    try:
        while len(produtos) < limite:
            params = {
                "consumer_key": WOO_CONSUMER_KEY,
                "consumer_secret": WOO_CONSUMER_SECRET,
                "status": WOO_STATUS,
                "per_page": per_page,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "_fields": campos,
            }
            url = _woo_url("products")
            log(f"🌐 Buscando produtos WooCommerce página {page}...")

            ultimo_erro = None
            resp = None
            for tentativa in range(1, 4):
                try:
                    # timeout separado: conexão maior para evitar falha no handshake SSL; leitura maior para Woo lento.
                    resp = sess.get(url, params=params, timeout=(30, 120), verify=False)
                    if resp.status_code in [502, 503, 504, 520, 522, 524]:
                        ultimo_erro = RuntimeError(f"status {resp.status_code}: {resp.text[:150]}")
                        log(f"⚠️ Woo instável na tentativa {tentativa}/3: status {resp.status_code}. Tentando novamente...")
                        time.sleep(3 * tentativa)
                        continue
                    resp.raise_for_status()
                    break
                except Exception as e:
                    ultimo_erro = e
                    log(f"⚠️ Erro/timeout buscando Woo página {page} tentativa {tentativa}/3: {e}")
                    time.sleep(3 * tentativa)
            else:
                raise ultimo_erro or RuntimeError("Falha desconhecida ao buscar WooCommerce")

            dados = resp.json()
            if not dados:
                break

            for item in dados:
                produtos.append(normalizar_produto_woo(item))
                if len(produtos) >= limite:
                    break
            page += 1

        log(f"✅ Produtos Woo carregados: {len(produtos)}")
        if produtos:
            _salvar_cache_woo(produtos)
        return produtos

    except Exception as e:
        log(f"❌ WooCommerce não respondeu agora: {e}")
        cache = _carregar_cache_woo(limite)
        if cache:
            log("⚠️ Seguindo com o último cache Woo salvo para não travar o teste de busca no SGI.")
            return cache
        raise RuntimeError(
            "Não consegui carregar produtos do WooCommerce e ainda não existe cache local. "
            "Tente rodar novamente em alguns minutos ou teste abrir /wp-json/wc/v3/products no navegador."
        ) from e


def normalizar_produto_woo(item: Dict) -> Dict:
    categorias = [c.get("name", "") for c in item.get("categories", []) if c.get("name")]
    imagens = [img.get("src", "") for img in item.get("images", []) if img.get("src")]
    nome = item.get("name", "") or ""

    attrs = {}
    for a in item.get("attributes", []) or []:
        nome_attr = (a.get("name") or "").strip()
        opcoes = a.get("options") or []
        if nome_attr:
            attrs[nome_attr] = ", ".join(opcoes)

    marca = attrs.get("Marca") or attrs.get("marca") or extrair_marca(nome)
    cor_voltagem = extrair_cor_voltagem_attrs(attrs)
    nome_sgi = montar_nome_sgi_com_detalhes(nome, attrs=attrs, marca=marca)

    return {
        "id_woo": item.get("id"),
        "sku": item.get("sku") or "",
        "nome_original_woo": nome,
        "nome": nome_sgi,
        "nome_sgi": nome_sgi,
        "cor_sgi": cor_voltagem.get("cor") or "",
        "voltagem_sgi": cor_voltagem.get("voltagem") or "",
        "descricao_curta": limpar_html(item.get("short_description") or ""),
        "descricao_completa": limpar_html(item.get("description") or ""),
        "categorias": categorias,
        "subgrupo_sugerido": escolher_subgrupo(categorias, nome),
        "marca": marca,
        "imagens": imagens,
        "altura": item.get("dimensions", {}).get("height") or "0",
        "largura": item.get("dimensions", {}).get("width") or "0",
        "profundidade": item.get("dimensions", {}).get("length") or "0",
        "peso": item.get("weight") or "0",
        "attributes": attrs,
        "permalink": item.get("permalink") or "",
    }
