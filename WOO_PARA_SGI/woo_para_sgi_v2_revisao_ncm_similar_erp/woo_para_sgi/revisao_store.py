# -*- coding: utf-8 -*-
"""Armazena decisões humanas de revisão/aprovação sem alterar o ERP.

Esta V2 continua segura: as decisões ficam em JSON para a próxima etapa,
quando o modo real for liberado conscientemente.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config import STORAGE_DIR

REVISAO_DIR = STORAGE_DIR / "revisoes"
REVISAO_DIR.mkdir(parents=True, exist_ok=True)
DECISOES_FILE = REVISAO_DIR / "decisoes_revisao.json"
VINCULOS_FILE = REVISAO_DIR / "vinculos_woo_sgi.json"


def _ler_json(path: Path, default):
    try:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        return default


def _salvar_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def listar_decisoes() -> List[Dict]:
    data = _ler_json(DECISOES_FILE, [])
    return data if isinstance(data, list) else []


def listar_vinculos() -> Dict:
    data = _ler_json(VINCULOS_FILE, {})
    return data if isinstance(data, dict) else {}


def salvar_decisao(payload: Dict) -> Dict:
    """Salva decisão humana.

    Ações esperadas:
    - APROVAR_ATUALIZACAO
    - CADASTRAR_NOVO
    - IGNORAR
    - REVISAR_NCM
    """
    decisoes = listar_decisoes()
    payload = dict(payload or {})
    sku = str(payload.get("sku") or "").strip()
    acao = str(payload.get("acao") or "").strip().upper()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    registro = {
        "data_hora": agora,
        "sku": sku,
        "id_woo": payload.get("id_woo") or "",
        "nome": payload.get("nome") or "",
        "acao": acao,
        "erp_codigo": payload.get("erp_codigo") or "",
        "erp_edit_url": payload.get("erp_edit_url") or "",
        "erp_descricao": payload.get("erp_descricao") or "",
        "ncm_aprovado": payload.get("ncm_aprovado") or payload.get("ncm_sugerido") or "",
        "observacao": payload.get("observacao") or "",
        "origem": "dashboard_revisao_v2",
    }
    decisoes.append(registro)
    _salvar_json(DECISOES_FILE, decisoes[-1000:])

    # Quando o usuário aprova atualização contra um produto ERP, grava vínculo permanente.
    if acao == "APROVAR_ATUALIZACAO" and sku and registro["erp_codigo"]:
        vinculos = listar_vinculos()
        vinculos[sku] = {
            "data_hora": agora,
            "codigo_erp": registro["erp_codigo"],
            "edit_url": registro["erp_edit_url"],
            "descricao_erp": registro["erp_descricao"],
            "ncm": registro["ncm_aprovado"],
            "observacao": registro["observacao"],
        }
        _salvar_json(VINCULOS_FILE, vinculos)

    return registro
