# -*- coding: utf-8 -*-
import hashlib
import mimetypes
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import requests

from config import IMAGENS_TEMP_DIR
from logger_app import log


def _extensao_por_url_ou_content_type(url: str, content_type: str = "") -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        return ext
    ext2 = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    if ext2 in [".jpg", ".jpeg", ".png", ".webp"]:
        return ext2
    return ".jpg"


def baixar_imagem_temporaria(url: str, prefixo: str = "produto") -> Path:
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    ext = _extensao_por_url_ou_content_type(url, resp.headers.get("Content-Type", ""))
    destino = IMAGENS_TEMP_DIR / f"{prefixo}_{h}{ext}"
    destino.write_bytes(resp.content)
    return destino


def baixar_imagens(urls: List[str], prefixo: str = "produto") -> List[Path]:
    arquivos = []
    for i, url in enumerate(urls or [], start=1):
        try:
            arq = baixar_imagem_temporaria(url, f"{prefixo}_{i}")
            arquivos.append(arq)
            log(f"📸 Imagem baixada temporariamente: {arq.name}")
        except Exception as e:
            log(f"❌ Erro baixando imagem {url}: {e}")
    return arquivos


def limpar_temporarias() -> None:
    for arq in IMAGENS_TEMP_DIR.glob("*"):
        try:
            if arq.is_file():
                arq.unlink()
        except Exception:
            pass
