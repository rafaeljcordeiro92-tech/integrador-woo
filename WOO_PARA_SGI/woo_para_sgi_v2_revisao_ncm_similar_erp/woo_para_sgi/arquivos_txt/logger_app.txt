# -*- coding: utf-8 -*-
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from config import LOG_DIR

LOG_FILE = LOG_DIR / f"execucao_{datetime.now().strftime('%Y%m%d')}.log"
STATUS_FILE = LOG_DIR / "status_atual.json"


def agora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def log(msg: str) -> None:
    linha = f"[{agora()}] {msg}"
    print(linha)
    sys.stdout.flush()
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def salvar_status(status: Dict[str, Any]) -> None:
    status = dict(status)
    status["atualizado_em"] = agora()
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def ler_status() -> Dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"rodando": False, "mensagem": "Nenhuma execução ainda."}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"rodando": False, "mensagem": "Status indisponível."}
