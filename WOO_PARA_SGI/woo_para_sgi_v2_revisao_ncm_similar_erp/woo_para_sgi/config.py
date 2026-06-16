# -*- coding: utf-8 -*-
"""
Configurações do robô WooCommerce -> SGI/Solidus.

IMPORTANTE:
- Não coloque senhas direto no código em produção.
- Use variáveis de ambiente no Railway/GitHub.
- Por padrão, DRY_RUN=True: o sistema SIMULA e NÃO salva/cadastra.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
LOG_DIR = STORAGE_DIR / "logs"
RELATORIO_DIR = STORAGE_DIR / "relatorios"
CACHE_DIR = STORAGE_DIR / "cache"
IMAGENS_TEMP_DIR = STORAGE_DIR / "imagens_temp"

for pasta in [STORAGE_DIR, LOG_DIR, RELATORIO_DIR, CACHE_DIR, IMAGENS_TEMP_DIR]:
    pasta.mkdir(parents=True, exist_ok=True)

# =========================
# MODO DE EXECUÇÃO
# =========================
# True = apenas simula, gera relatório e NÃO salva no ERP.
# False = executa alterações reais no ERP.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ["1", "true", "sim", "yes"]

# Quantidade de produtos para testar no começo.
# Primeiro teste ampliado para 15 itens.
LIMITE_PRODUTOS_TESTE = int(os.getenv("LIMITE_PRODUTOS_TESTE", "20"))

# =========================
# WOOCOMMERCE
# =========================
WOO_BASE_URL = os.getenv("WOO_BASE_URL", "https://moveisdolar.com.br")
WOO_CONSUMER_KEY = os.getenv("WOO_CONSUMER_KEY", "ck_6c160463d72b37d1783ef97b09d19e6eefcc2293")
WOO_CONSUMER_SECRET = os.getenv("WOO_CONSUMER_SECRET", "cs_a9b7cee49457d1a7839ab2c83a4d1dd9ccee8f0f")
WOO_API_VERSION = os.getenv("WOO_API_VERSION", "wc/v3")

# Busca apenas produtos publicados por padrão.
WOO_STATUS = os.getenv("WOO_STATUS", "publish")

# WordPress / mídia — extraído do integrador anterior.
# Esta V1 ainda usa principalmente a API Woo, mas deixei pronto para futura etapa de imagens/mídia.
WP_USER = os.getenv("WP_USER", "admin")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "UcLe k2Ir ZIdt lVJO 6wtx 2F5H")
WP_MEDIA_URL = os.getenv("WP_MEDIA_URL", f"{WOO_BASE_URL}/wp-json/wp/v2/media")

# =========================
# SGI / SOLIDUS SMART
# =========================
SGI_BASE_URL = os.getenv("SGI_BASE_URL", "https://smart.sgisistemas.com.br")
SGI_PRODUTOS_URL = f"{SGI_BASE_URL}/produtos"
SGI_NOVO_PRODUTO_URL = f"{SGI_BASE_URL}/produtos/new"
SGI_LOGIN_URL = os.getenv("SGI_LOGIN_URL", f"{SGI_BASE_URL}/login")
SGI_USUARIO = os.getenv("SGI_USUARIO", "administrativo01.moveisdolar")
SGI_SENHA = os.getenv("SGI_SENHA", "mdladm01")

# Se já estiver logado em um perfil local do Chrome, pode usar False e abrir manualmente.
SGI_TENTAR_LOGIN_AUTOMATICO = os.getenv("SGI_TENTAR_LOGIN_AUTOMATICO", "true").lower() in ["1", "true", "sim", "yes"]

# Dados do integrador fornecedor antigo, mantidos apenas para referência/futuras integrações.
FORNECEDOR_BASE_URL = os.getenv("FORNECEDOR_BASE_URL", "https://portal.juntossomosimbativeis.com.br")
FORNECEDOR_EMPRESA = int(os.getenv("FORNECEDOR_EMPRESA", "272"))
FORNECEDOR_USUARIO = os.getenv("FORNECEDOR_USUARIO", "00905486986")
FORNECEDOR_SENHA = os.getenv("FORNECEDOR_SENHA", "Rafael2026@")

# =========================
# SELENIUM
# =========================
HEADLESS = os.getenv("HEADLESS", "false").lower() in ["1", "true", "sim", "yes"]
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")
SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "25"))
PAUSA_ENTRE_ACOES = float(os.getenv("PAUSA_ENTRE_ACOES", "0.35"))

# =========================
# PADRÕES DE CADASTRO SGI
# =========================
ORIGEM_PADRAO = "Nacional, exceto as indicadas nos códigos 3 a 5."
UNIDADE_PADRAO = "Unidade"
SUBGRUPO_PADRAO = "MÓVEIS"
MARCA_PADRAO = "DIVERSOS"

# Atualizações habilitadas na primeira fase.
ATUALIZAR_DESCRICAO = True
ATUALIZAR_IMAGENS = True
ATUALIZAR_MEDIDAS = True
ATUALIZAR_TRIBUTACAO = True

# Cadastro real só será feito se DRY_RUN=False.
PERMITIR_CADASTRO_NOVO = os.getenv("PERMITIR_CADASTRO_NOVO", "false").lower() in ["1", "true", "sim", "yes"]
PERMITIR_ATUALIZACAO = os.getenv("PERMITIR_ATUALIZACAO", "false").lower() in ["1", "true", "sim", "yes"]

# =========================
# MATCH / SIMILARIDADE
# =========================
LIMIAR_MATCH_FORTE = float(os.getenv("LIMIAR_MATCH_FORTE", "0.88"))
LIMIAR_MATCH_MEDIO = float(os.getenv("LIMIAR_MATCH_MEDIO", "0.72"))

# Palavras genéricas que atrapalham busca inteligente.
STOPWORDS_PRODUTO = {
    "DE", "DA", "DO", "DAS", "DOS", "COM", "C", "P", "PARA", "E", "A", "O", "AS", "OS",
    "SMART", "LED", "WIFI", "USB", "HDMI", "BIV", "BIVOLT", "VOLTS", "VOLT", "POLEGADAS"
}

# Mapeamento inicial Woo -> SGI. Ajuste conforme suas categorias reais do Woo.
MAPA_SUBGRUPO = {
    "moveis": "MÓVEIS",
    "móveis": "MÓVEIS",
    "cozinha": "MÓVEIS",
    "sala": "MÓVEIS",
    "quarto": "MÓVEIS",
    "eletro": "ELETRODOMÉSTICOS",
    "eletrodomesticos": "ELETRODOMÉSTICOS",
    "eletrodomésticos": "ELETRODOMÉSTICOS",
    "eletronicos": "ELETROELETRÔNICOS",
    "eletrônicos": "ELETROELETRÔNICOS",
    "celular": "ELETROELETRÔNICOS",
    "smartphone": "ELETROELETRÔNICOS",
    "tv": "ELETROELETRÔNICOS",
}

MARCAS_CONHECIDAS = [
    "ELECTROLUX", "PHILCO", "BRITANIA", "BRITÂNIA", "MOTOROLA", "LUCIANE", "MOVEIS SUL", "MÓVEIS SUL",
    "CAEMMUN", "JS CABECEIRAS", "GAZIN", "CONSUL", "BRASTEMP", "SAMSUNG", "LG", "MONDIAL",
    "MIDEA", "AGRATTO", "CADENCE", "MULTILASER", "POSITIVO", "XIAOMI", "APPLE"
]
