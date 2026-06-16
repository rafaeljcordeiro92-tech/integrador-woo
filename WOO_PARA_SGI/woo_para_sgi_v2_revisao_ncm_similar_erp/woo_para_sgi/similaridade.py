# -*- coding: utf-8 -*-
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from normalizador import limpar_texto, tokens_produto
from config import LIMIAR_MATCH_FORTE, LIMIAR_MATCH_MEDIO


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, limpar_texto(a), limpar_texto(b)).ratio()


def token_overlap(a: str, b: str) -> float:
    ta = set(tokens_produto(a))
    tb = set(tokens_produto(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def score_produto(woo: Dict, erp: Dict) -> float:
    nome_w = woo.get("nome", "")
    nome_e = erp.get("descricao", "")
    sku = limpar_texto(woo.get("sku", ""))
    ref = limpar_texto(erp.get("referencia", ""))
    marca_w = limpar_texto(woo.get("marca", ""))
    marca_e = limpar_texto(erp.get("marca", ""))

    score_nome = ratio(nome_w, nome_e)
    score_tokens = token_overlap(nome_w, nome_e)
    score = (score_nome * 0.55) + (score_tokens * 0.35)

    if sku and ref and sku == ref:
        score = max(score, 0.99)
    elif sku and ref and (sku in ref or ref in sku):
        score += 0.10

    if marca_w and marca_e and marca_w == marca_e:
        score += 0.08

    return min(score, 1.0)


def classificar_match(woo: Dict, resultados_erp: List[Dict]) -> Tuple[str, Dict, float, str]:
    """
    Retorna: status, melhor_resultado, score, motivo
    status: MATCH_FORTE, MATCH_MEDIO, NOVO, REVISAO
    """
    if not resultados_erp:
        return "NOVO", {}, 0.0, "Nenhum produto encontrado no ERP."

    avaliados = []
    for erp in resultados_erp:
        s = score_produto(woo, erp)
        avaliados.append((s, erp))
    avaliados.sort(key=lambda x: x[0], reverse=True)

    melhor_score, melhor = avaliados[0]
    sku = limpar_texto(woo.get("sku", ""))
    ref = limpar_texto(melhor.get("referencia", ""))

    if sku and ref and sku == ref:
        return "MATCH_FORTE", melhor, 0.99, "SKU Woo igual à Ref. Fornecedor/Produto do ERP."

    if melhor_score >= LIMIAR_MATCH_FORTE:
        return "MATCH_FORTE", melhor, melhor_score, "Nome/marca/modelo com alta similaridade."

    if melhor_score >= LIMIAR_MATCH_MEDIO:
        return "MATCH_MEDIO", melhor, melhor_score, "Produto parecido; recomenda revisão antes de alterar."

    return "REVISAO", melhor, melhor_score, "Resultados encontrados, mas similaridade baixa."
