# -*- coding: utf-8 -*-
"""
Robô WooCommerce -> SGI/Solidus via Selenium.

Primeira versão segura:
- Puxa produtos do WooCommerce.
- Abre SGI Produtos.
- Faz tentativas de busca em ordem reversa, usando % no SGI:
  1) Referência/modelo isolado, exemplo %XT2623 ou %A57
  2) Marca + modelo
  3) Palavras fortes
  4) Nome completo
  5) SKU/referência completa
- Classifica: MATCH_FORTE, MATCH_MEDIO, REVISAO, NOVO.
- Sugere NCM por regras.
- Por padrão NÃO salva nada: DRY_RUN=True.
"""

from typing import Dict, List
import traceback

from config import DRY_RUN, LIMITE_PRODUTOS_TESTE
from imagens_temp import baixar_imagens, limpar_temporarias
from logger_app import log, salvar_status
from ncm_sugestor import sugerir_ncm, sugerir_ncm_com_erp
from relatorios import salvar_relatorio
from sgi_driver import criar_driver, tentar_login
from sgi_produtos import (
    buscar_com_5_tentativas,
    atualizar_produto_existente,
    cadastrar_produto_novo,
)
from similaridade import classificar_match
from woo_client import buscar_produtos


PARAR = False


def processar_produto(driver, produto: Dict) -> Dict:
    log("=" * 80)
    log(f"📦 Produto Woo: {produto.get('nome')} | SKU: {produto.get('sku') or 'sem SKU'}")
    if produto.get("nome_original_woo") and produto.get("nome_original_woo") != produto.get("nome"):
        log(f"🏷️ Nome ajustado para SGI: {produto.get('nome_original_woo')} → {produto.get('nome')}")
    if produto.get("cor_sgi") or produto.get("voltagem_sgi"):
        log(f"🎨 Detalhes no nome SGI | Cor: {produto.get('cor_sgi') or '-'} | Voltagem: {produto.get('voltagem_sgi') or '-'}")

    ncm_regra = sugerir_ncm(produto)
    log(f"🧾 NCM inicial: {ncm_regra.get('ncm') or 'REVISAR'} | Confiança: {ncm_regra.get('confianca')} | Fonte: {ncm_regra.get('fonte')} | {ncm_regra.get('motivo')}")

    resultados_erp = buscar_com_5_tentativas(driver, produto)
    status_match, melhor_erp, score, motivo = classificar_match(produto, resultados_erp)

    log(f"🎯 Classificação: {status_match} | Score: {score:.2f} | {motivo}")
    if melhor_erp:
        log(f"   ↳ Melhor ERP: {melhor_erp.get('codigo')} | {melhor_erp.get('descricao')} | Ref: {melhor_erp.get('referencia')} | NCM: {melhor_erp.get('ncm') or '-'}")

    ncm_info = sugerir_ncm_com_erp(produto, melhor_erp, status_match, score, ncm_regra)
    log(f"🧾 NCM final V2: {ncm_info.get('ncm') or 'REVISAR'} | Confiança: {ncm_info.get('confianca')} | Fonte: {ncm_info.get('fonte')} | {ncm_info.get('motivo')}")

    imagens_locais = []
    acao_result = {"acao": "NENHUMA", "mensagem": "Nenhuma ação executada."}

    try:
        # No modo real, baixa as imagens temporariamente para upload via Selenium.
        # No DRY_RUN também baixa até 1 imagem só para validar URL? Melhor não baixar para ficar rápido.
        if not DRY_RUN and produto.get("imagens"):
            imagens_locais = baixar_imagens(produto.get("imagens") or [], prefixo=str(produto.get("id_woo") or "produto"))

        if status_match == "MATCH_FORTE":
            acao_result = atualizar_produto_existente(driver, produto, melhor_erp, ncm_info, imagens_locais)
        elif status_match in ["MATCH_MEDIO", "REVISAO"]:
            acao_result = {"acao": "REVISAO_HUMANA", "mensagem": "Produto parecido; exige conferência humana antes de atualizar/cadastrar."}
        elif status_match == "NOVO":
            acao_result = cadastrar_produto_novo(driver, produto, ncm_info, imagens_locais)
    finally:
        limpar_temporarias()

    return {
        "id_woo": produto.get("id_woo"),
        "sku": produto.get("sku"),
        "nome_original_woo": produto.get("nome_original_woo", ""),
        "nome": produto.get("nome"),
        "cor_sgi": produto.get("cor_sgi", ""),
        "voltagem_sgi": produto.get("voltagem_sgi", ""),
        "status": status_match,
        "acao": acao_result.get("acao"),
        "score": round(score, 4),
        "motivo_match": motivo,
        "erp_codigo": melhor_erp.get("codigo", "") if melhor_erp else "",
        "erp_descricao": melhor_erp.get("descricao", "") if melhor_erp else "",
        "erp_referencia": melhor_erp.get("referencia", "") if melhor_erp else "",
        "erp_marca": melhor_erp.get("marca", "") if melhor_erp else "",
        "erp_ncm": melhor_erp.get("ncm", "") if melhor_erp else "",
        "erp_edit_url": melhor_erp.get("edit_url", "") if melhor_erp else "",
        "ncm_sugerido": ncm_info.get("ncm"),
        "ncm_confianca": ncm_info.get("confianca"),
        "ncm_motivo": ncm_info.get("motivo"),
        "ncm_fonte": ncm_info.get("fonte", ""),
        "ncm_erp_codigo_base": ncm_info.get("erp_codigo_base", ""),
        "ncm_erp_descricao_base": ncm_info.get("erp_descricao_base", ""),
        "ncm_regra_original": ncm_info.get("ncm_regra_original", ""),
        "precisa_revisao_ncm": ncm_info.get("precisa_revisao"),
        "mensagem": acao_result.get("mensagem"),
    }


def executar(limite: int = None) -> Dict:
    limite = limite or LIMITE_PRODUTOS_TESTE
    resultados: List[Dict] = []
    driver = None

    salvar_status({
        "rodando": True,
        "mensagem": "Iniciando execução.",
        "dry_run": DRY_RUN,
        "total": 0,
        "processados": 0,
        "match_forte": 0,
        "revisao": 0,
        "novos": 0,
        "erros": 0,
    })

    try:
        log(f"🚀 Iniciando robô Woo -> SGI | DRY_RUN={DRY_RUN} | limite={limite}")
        produtos = buscar_produtos(limite=limite)

        driver = criar_driver()
        tentar_login(driver)

        total = len(produtos)
        contadores = {"match_forte": 0, "revisao": 0, "novos": 0, "erros": 0}

        for idx, produto in enumerate(produtos, start=1):
            try:
                salvar_status({
                    "rodando": True,
                    "mensagem": f"Processando {idx}/{total}: {produto.get('nome')}",
                    "dry_run": DRY_RUN,
                    "total": total,
                    "processados": idx - 1,
                    **contadores,
                })
                res = processar_produto(driver, produto)
                resultados.append(res)

                if res["status"] == "MATCH_FORTE":
                    contadores["match_forte"] += 1
                elif res["status"] == "NOVO":
                    contadores["novos"] += 1
                else:
                    contadores["revisao"] += 1

                salvar_status({
                    "rodando": True,
                    "mensagem": f"Processado {idx}/{total}: {produto.get('nome')}",
                    "dry_run": DRY_RUN,
                    "total": total,
                    "processados": idx,
                    **contadores,
                })
            except Exception as e:
                contadores["erros"] += 1
                log(f"❌ Erro no produto {produto.get('nome')}: {e}")
                log(traceback.format_exc())
                resultados.append({
                    "id_woo": produto.get("id_woo"),
                    "sku": produto.get("sku"),
                    "nome": produto.get("nome"),
                    "status": "ERRO",
                    "acao": "ERRO",
                    "mensagem": str(e),
                })

        arquivos = salvar_relatorio(resultados)
        log(f"📄 Relatório salvo: {arquivos}")

        resumo = {
            "rodando": False,
            "mensagem": "Execução finalizada.",
            "dry_run": DRY_RUN,
            "total": total,
            "processados": total,
            **contadores,
            "relatorio_json": arquivos["json"],
            "relatorio_csv": arquivos["csv"],
        }
        salvar_status(resumo)
        return resumo

    except Exception as e:
        log(f"❌ Erro geral: {e}")
        log(traceback.format_exc())
        salvar_status({"rodando": False, "mensagem": f"Erro geral: {e}", "dry_run": DRY_RUN})
        raise
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    executar()
