# -*- coding: utf-8 -*-
import re
import unicodedata
from typing import Iterable, List, Optional

from config import MARCAS_CONHECIDAS, STOPWORDS_PRODUTO, MAPA_SUBGRUPO, SUBGRUPO_PADRAO, MARCA_PADRAO


def sem_acentos(txt: str) -> str:
    txt = txt or ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(ch))


def limpar_texto(txt: str) -> str:
    txt = sem_acentos(txt or "").upper()
    txt = re.sub(r"[^A-Z0-9]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def tokens_produto(nome: str) -> List[str]:
    tokens = limpar_texto(nome).split()
    return [t for t in tokens if t and t not in STOPWORDS_PRODUTO and len(t) >= 2]


def extrair_marca(nome: str, marcas: Optional[Iterable[str]] = None) -> str:
    nome_limpo = limpar_texto(nome)
    marcas = marcas or MARCAS_CONHECIDAS
    for marca in sorted(marcas, key=len, reverse=True):
        if limpar_texto(marca) in nome_limpo:
            return marca.replace("BRITÂNIA", "BRITANIA").replace("MÓVEIS", "MOVEIS")
    return MARCA_PADRAO


def extrair_modelos_referencias(nome: str, sku: str = "") -> List[str]:
    """
    Extrai referências/modelos fortes, como XT2623, ME36S, P50CRB, BEC07R, PPR10, 5737TAV.
    Essa lista alimenta a 5ª tentativa: buscar somente a referência isolada.
    """
    texto = limpar_texto(f"{nome} {sku}")
    encontrados = []

    padroes = [
        r"\b[A-Z]{1,4}\d{2,6}[A-Z]{0,4}\b",       # XT2623, ME36S, P50CRB, BEC07R
        r"\b\d{3,8}[A-Z]{2,5}\b",                 # 5737TAV, 4855AOF
        r"\b\d{4,8}\.\d{1,6}\.\d{1,6}\b",       # 76472.10.0
        r"\b\d{6,12}\b",                          # refs numéricas
    ]
    for padrao in padroes:
        for m in re.findall(padrao, texto):
            if m not in encontrados:
                encontrados.append(m)

    # Evita referências muito genéricas de capacidade/medida.
    bloqueados = {"220V", "110V", "127V", "256GB", "128GB", "64GB", "32GB", "50", "32", "40"}
    return [x for x in encontrados if x not in bloqueados]


def palavras_fortes(nome: str, limite: int = 5) -> str:
    toks = tokens_produto(nome)
    # Prioriza tokens com letras/números misturados ou mais longos.
    toks = sorted(toks, key=lambda t: (bool(re.search(r"[A-Z]", t) and re.search(r"\d", t)), len(t)), reverse=True)
    saida = []
    for t in toks:
        if t not in saida:
            saida.append(t)
        if len(saida) >= limite:
            break
    return " ".join(saida)


def marca_modelo(nome: str, sku: str = "") -> str:
    marca = extrair_marca(nome)
    refs = extrair_modelos_referencias(nome, sku)
    if marca != MARCA_PADRAO and refs:
        return f"{marca} {refs[0]}"
    if refs:
        return refs[0]
    if marca != MARCA_PADRAO:
        return f"{marca} {palavras_fortes(nome, 3)}"
    return palavras_fortes(nome, 3)


def escolher_subgrupo(categorias: List[str], nome: str) -> str:
    base = " ".join(categorias or []) + " " + (nome or "")
    base_limpa = sem_acentos(base).lower()
    for chave, subgrupo in MAPA_SUBGRUPO.items():
        if sem_acentos(chave).lower() in base_limpa:
            return subgrupo
    return SUBGRUPO_PADRAO


def dinheiro_br(valor) -> str:
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def numero_br(valor) -> str:
    try:
        return f"{float(valor):.2f}".replace(".", ",")
    except Exception:
        return "0,00"


def limpar_html(html: str) -> str:
    html = html or ""
    html = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p\s*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


# ================= COR / VOLTAGEM NO NOME SGI =================
# Regra MDL/SGI: no ERP a cor e a voltagem precisam estar dentro do NOME do produto.
# No WooCommerce esses dados podem vir como atributos separados, então juntamos aqui.

CHAVES_COR = {"COR", "COLOR", "CORES", "COLORES", "PA_COR", "PA COLOR", "ACABAMENTO"}
CHAVES_VOLTAGEM = {"VOLTAGEM", "VOLTAGENS", "TENSAO", "TENSÃO", "VOLT", "VOLTS", "PA_VOLTAGEM", "PA TENSAO"}

CORES_CONHECIDAS = {
    "BRANCO", "BRANCA", "PRETO", "PRETA", "CINZA", "GRAFITE", "PRATA", "INOX",
    "VERMELHO", "VERMELHA", "AZUL", "ROXO", "ROXA", "ROSA", "VERDE", "AMARELO",
    "MARROM", "BEGE", "OFF WHITE", "OFFWHITE", "NATURAL", "FREIJO", "FREIJÓ",
    "AVELÃ", "AVELA", "ANGELIN", "CASTANHO", "CARVALHO", "NOGUEIRA", "IMBUIA",
    "VANILA", "VANILLA", "TAUARI", "JEQUITIBA", "JEQUITIBÁ", "CACAU", "CANELA"
}


def _normalizar_chave_attr(chave: str) -> str:
    return limpar_texto(chave).replace(" ", "_")


def _partes_attr(valor: str) -> List[str]:
    valor = valor or ""
    partes = re.split(r"[,;/|]+", str(valor))
    return [p.strip() for p in partes if p and p.strip()]


def normalizar_voltagem_para_nome(valor: str) -> str:
    """Converte voltagem do Woo para o padrão curto do nome SGI: BIV, 127V, 220V."""
    txt = limpar_texto(valor)
    if not txt:
        return ""
    # Alguns produtos sem voltagem chegam do Woo como S/N, SIM, NA ou apenas S.
    # Isso NÃO deve entrar no nome do SGI.
    if txt in {"S", "N", "V", "SN", "S N", "NA", "N A", "N/A", "SIM", "NAO", "NÃO", "SEM", "SEM VOLTAGEM"}:
        return ""
    if any(x in txt for x in ["BIVOLT", "BIVOL", "BIV ", " BIV", "BIV"]):
        return "BIV"
    if "127" in txt or "110" in txt:
        return "127V"
    if "220" in txt:
        return "220V"
    # Caso venha algo como 12V, 24V etc.
    m = re.search(r"\b(\d{2,3})\s*V\b", txt)
    if m:
        return f"{m.group(1)}V"
    return txt


def normalizar_cor_para_nome(valor: str) -> str:
    txt = limpar_texto(valor)
    if not txt:
        return ""
    # Mantém cores compostas usuais.
    txt = txt.replace("OFFWHITE", "OFF WHITE")
    return txt


def extrair_cor_voltagem_attrs(attrs: dict) -> dict:
    """Lê atributos do Woo e devolve {'cor': ..., 'voltagem': ...} já no padrão de nome SGI."""
    cor = ""
    voltagem = ""
    attrs = attrs or {}

    for chave, valor in attrs.items():
        chave_norm = limpar_texto(chave)
        chave_norm_under = _normalizar_chave_attr(chave)
        valores = _partes_attr(valor)

        if chave_norm in CHAVES_COR or chave_norm_under in CHAVES_COR:
            for v in valores:
                c = normalizar_cor_para_nome(v)
                if c and c not in {"PADRAO", "PADRÃO", "UNICO", "ÚNICO"}:
                    cor = c
                    break

        if chave_norm in CHAVES_VOLTAGEM or chave_norm_under in CHAVES_VOLTAGEM:
            for v in valores:
                vv = normalizar_voltagem_para_nome(v)
                if vv:
                    voltagem = vv
                    break

    return {"cor": cor, "voltagem": voltagem}


def nome_ja_tem_detalhe(nome: str, detalhe: str) -> bool:
    if not nome or not detalhe:
        return True
    nome_limpo = limpar_texto(nome)
    detalhe_limpo = limpar_texto(detalhe)
    if detalhe_limpo in nome_limpo:
        return True
    # Equivalências de voltagem.
    if detalhe_limpo == "BIV" and any(x in nome_limpo for x in ["BIV", "BIVOLT", "BIVOL"]):
        return True
    if detalhe_limpo == "127V" and ("127V" in nome_limpo or "110V" in nome_limpo or "127 V" in nome_limpo):
        return True
    if detalhe_limpo == "220V" and ("220V" in nome_limpo or "220 V" in nome_limpo):
        return True
    return False


def inserir_detalhes_antes_da_marca(nome: str, detalhes: List[str], marca: str = "") -> str:
    """Insere cor/voltagem antes da marca quando a marca estiver no fim do nome."""
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    detalhes = [d for d in detalhes if d]
    if not detalhes:
        return nome

    bloco = " ".join(detalhes)
    marca_limpa = limpar_texto(marca)
    nome_limpo = limpar_texto(nome)

    if marca and marca_limpa and nome_limpo.endswith(marca_limpa):
        # Remove a marca do fim preservando o texto original antes dela.
        padrao = re.compile(rf"\s+{re.escape(marca)}\s*$", re.I)
        if padrao.search(nome):
            base = padrao.sub("", nome).strip()
            return f"{base} {bloco} {marca}".strip()

    return f"{nome} {bloco}".strip()


def montar_nome_sgi_com_detalhes(nome: str, attrs: dict = None, marca: str = "") -> str:
    """
    Garante que o nome final do SGI contenha cor e voltagem quando vierem separadas no Woo.
    Ex.: nome='SECADOR DE CABELOS 2200W PSC2300 PHILCO', Voltagem='Bivolt', Cor='Vermelho'
    -> 'SECADOR DE CABELOS 2200W PSC2300 VERMELHO BIV PHILCO'
    """
    nome_original = re.sub(r"\s+", " ", (nome or "").strip()).upper()
    dados = extrair_cor_voltagem_attrs(attrs or {})
    detalhes = []

    cor = dados.get("cor") or ""
    voltagem = dados.get("voltagem") or ""

    if cor and not nome_ja_tem_detalhe(nome_original, cor):
        detalhes.append(cor)
    if voltagem and not nome_ja_tem_detalhe(nome_original, voltagem):
        detalhes.append(voltagem)

    nome_final = inserir_detalhes_antes_da_marca(nome_original, detalhes, marca=marca)
    nome_final = re.sub(r"\s+", " ", nome_final).strip()
    return nome_final
