# -*- coding: utf-8 -*-
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config import RELATORIO_DIR


def salvar_relatorio(resultados: List[Dict]) -> Dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RELATORIO_DIR / f"relatorio_woo_sgi_{ts}.json"
    csv_path = RELATORIO_DIR / f"relatorio_woo_sgi_{ts}.csv"

    json_path.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    campos = [
        "id_woo", "sku", "nome", "status", "acao", "score", "motivo_match",
        "erp_codigo", "erp_descricao", "erp_referencia", "erp_marca", "erp_ncm", "erp_edit_url",
        "ncm_sugerido", "ncm_confianca", "ncm_motivo", "ncm_fonte",
        "ncm_erp_codigo_base", "ncm_erp_descricao_base", "ncm_regra_original",
        "precisa_revisao_ncm", "mensagem"
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        for r in resultados:
            writer.writerow(r)

    return {"json": str(json_path), "csv": str(csv_path)}


def listar_relatorios() -> List[Dict]:
    itens = []
    for p in sorted(RELATORIO_DIR.glob("relatorio_woo_sgi_*.*"), reverse=True):
        itens.append({"nome": p.name, "caminho": str(p), "tamanho": p.stat().st_size})
    return itens[:20]


def ultimo_relatorio_json() -> Path | None:
    arquivos = sorted(RELATORIO_DIR.glob("relatorio_woo_sgi_*.json"), reverse=True)
    return arquivos[0] if arquivos else None


def ler_ultimo_relatorio() -> List[Dict]:
    p = ultimo_relatorio_json()
    if not p:
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def itens_para_revisao() -> List[Dict]:
    dados = ler_ultimo_relatorio()
    out = []
    for item in dados:
        status = (item.get("status") or "").upper()
        precisa_ncm = str(item.get("precisa_revisao_ncm", "")).lower() in ["true", "1", "sim", "yes"] or item.get("precisa_revisao_ncm") is True
        if status in {"MATCH_MEDIO", "REVISAO", "NOVO"} or precisa_ncm:
            out.append(item)
    return out
