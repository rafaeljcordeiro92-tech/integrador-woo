import json
import os
from datetime import datetime

STATS_FILE = "stats.json"

def carregar_stats():
    if not os.path.exists(STATS_FILE):
        return {"updates": 0, "novos": 0, "erros": 0, "historico": []}
    return json.load(open(STATS_FILE))

def salvar_stats(stats):
    json.dump(stats, open(STATS_FILE, "w"))

def registrar_evento(tipo):
    stats = carregar_stats()
    stats[tipo] += 1
    stats["historico"].append({
        "tipo": tipo,
        "hora": datetime.now().strftime("%H:%M:%S")
    })
    stats["historico"] = stats["historico"][-50:]
    salvar_stats(stats)