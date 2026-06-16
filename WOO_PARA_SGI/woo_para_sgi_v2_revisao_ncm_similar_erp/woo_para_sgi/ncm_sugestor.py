# -*- coding: utf-8 -*-
"""Sugestão de NCM em camadas.

Prioridade MDL para a V2:
1) Se houver match forte no ERP, usar o NCM do próprio ERP encontrado.
2) Se houver similar no ERP com NCM, usar como sugestão, mas manter revisão.
3) Aplicar regras internas conservadoras.
4) Se continuar incerto, marcar REVISAR.

Obs.: NCM é dado fiscal. Esta etapa sugere e registra a fonte, mas não deve salvar
automaticamente quando a confiança estiver baixa/média ou quando a fonte for similar.
"""
from typing import Dict

from normalizador import limpar_texto

# Regras seguras/recorrentes já vistas no ERP do usuário.
REGRAS_NCM = [
    ("8528.72.00", "Alta", ["TV", "TELEVISOR", "SMART TV", "ROKU", "LED 4K", "UHD 4K"], "Televisores/Smart TVs"),
    ("8516.50.00", "Alta", ["MICRO ONDAS", "MICROONDAS", "FORNO MICRO"], "Micro-ondas"),
    ("8516.32.00", "Alta", ["ESCOVA SECADORA", "PRANCHA", "ALISADORA", "MODELADORA", "SECADOR DE CABELO", "SECADOR CABELO"], "Aparelhos eletrotérmicos para cabelo"),
    ("8517.62.62", "Alta", ["SMARTPHONE", "CELULAR", "MOTOROLA", "IPHONE", "XIAOMI", "SAMSUNG A", "GALAXY"], "Aparelhos de telefonia/celular"),
    ("9403.40.00", "Alta", ["BALCAO", "BALCÃO", "ARMARIO COZINHA", "ARMÁRIO COZINHA", "COZINHA COMPACTA", "COOKTOP", "PANELEIRO"], "Móveis de madeira para cozinha"),
    ("9403.50.00", "Média", ["CABECEIRA", "CAMA", "CRIADO", "GUARDA ROUPA", "G ROUPA", "ROUPEIRO", "COMODA", "CÔMODA"], "Móveis de madeira para quarto"),
    ("9403.60.00", "Média", ["MESA", "RACK", "PAINEL", "ESTANTE", "MULTIUSO", "ESCRIVANINHA", "SAPATEIRA"], "Outros móveis de madeira"),
]

# Termos que NÃO devem cair em NCM de móveis só porque a categoria tem cozinha/casa.
TERMOS_EXIGEM_REVISAO = [
    ("LIQUIDIFICADOR", "Eletroportátil: revisar NCM antes de cadastrar."),
    ("MIXER", "Eletroportátil: revisar NCM antes de cadastrar."),
    ("FRITADEIRA", "Eletroportátil/air fryer: revisar NCM antes de cadastrar."),
    ("AIR FRYER", "Eletroportátil/air fryer: revisar NCM antes de cadastrar."),
    ("GRILL", "Eletroportátil/grill: revisar NCM antes de cadastrar."),
    ("SANDUICHEIRA", "Eletroportátil/sanduicheira: revisar NCM antes de cadastrar."),
    ("LAVADORA", "Lavadora/tanquinho: preferir NCM de produto similar no ERP ou revisão fiscal."),
    ("TANQUINHO", "Lavadora/tanquinho: preferir NCM de produto similar no ERP ou revisão fiscal."),
    ("BICICLETA", "Bicicleta: revisar NCM antes de cadastrar."),
]


def _base_retorno(ncm: str, confianca: str, motivo: str, precisa: bool, fonte: str, **extra) -> Dict:
    out = {
        "ncm": ncm or "",
        "confianca": confianca,
        "motivo": motivo,
        "precisa_revisao": bool(precisa),
        "fonte": fonte,
    }
    out.update(extra)
    return out


def sugerir_ncm(produto: Dict) -> Dict:
    nome = produto.get("nome") or produto.get("descricao") or ""
    categorias = " ".join(produto.get("categorias", []) or [])
    texto = limpar_texto(f"{nome} {categorias}")

    # Primeiro trava produtos conhecidos como perigosos para classificação errada por palavra genérica.
    for termo, motivo in TERMOS_EXIGEM_REVISAO:
        if limpar_texto(termo) in texto:
            return _base_retorno("", "Baixa", motivo, True, "regra_conservadora")

    for ncm, confianca, termos, motivo in REGRAS_NCM:
        for termo in termos:
            if limpar_texto(termo) in texto:
                return _base_retorno(
                    ncm,
                    confianca,
                    motivo,
                    confianca.lower() != "alta",
                    "regra_interna",
                )

    return _base_retorno(
        "",
        "Baixa",
        "Não foi possível identificar NCM com segurança pelas regras atuais.",
        True,
        "sem_regra",
    )


def sugerir_ncm_com_erp(produto: Dict, melhor_erp: Dict, status_match: str, score: float, ncm_regra: Dict) -> Dict:
    """Melhora a sugestão usando o NCM do produto similar encontrado no ERP."""
    melhor_erp = melhor_erp or {}
    ncm_erp = (melhor_erp.get("ncm") or "").strip()
    codigo = (melhor_erp.get("codigo") or "").strip()
    descricao = (melhor_erp.get("descricao") or "").strip()

    if ncm_erp and status_match == "MATCH_FORTE":
        return _base_retorno(
            ncm_erp,
            "Alta",
            f"NCM herdado do produto ERP correspondente ({codigo}) por match forte.",
            False,
            "erp_match_forte",
            erp_codigo_base=codigo,
            erp_descricao_base=descricao,
            ncm_regra_original=ncm_regra.get("ncm") or "",
        )

    if ncm_erp and status_match in {"MATCH_MEDIO", "REVISAO"}:
        # Similar ajuda bastante, mas não deve salvar automaticamente.
        conf = "Média" if float(score or 0) >= 0.55 else "Baixa"
        return _base_retorno(
            ncm_erp,
            conf,
            f"NCM sugerido pelo produto similar no ERP ({codigo}); revisar antes de salvar.",
            True,
            "erp_similar",
            erp_codigo_base=codigo,
            erp_descricao_base=descricao,
            ncm_regra_original=ncm_regra.get("ncm") or "",
        )

    # Sem ERP útil: mantém regra interna.
    return ncm_regra
