# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from config import (
    DRY_RUN,
    ORIGEM_PADRAO,
    PERMITIR_ATUALIZACAO,
    PERMITIR_CADASTRO_NOVO,
    SGI_NOVO_PRODUTO_URL,
    SGI_PRODUTOS_URL,
    UNIDADE_PADRAO,
)
from logger_app import log
from normalizador import marca_modelo, palavras_fortes, extrair_modelos_referencias, numero_br
from sgi_driver import abrir, clicar, elemento, preencher, preencher_autocomplete, set_contenteditable, dormir
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def aplicar_curinga_sgi(termo: str) -> str:
    """No SGI, colocar % no começo melhora a busca por palavra-chave/modelo.
    Ex.: A57 -> %A57. Se já vier com %, mantém como está.
    """
    termo = (termo or "").strip()
    if not termo:
        return termo
    if termo.startswith("%"):
        return termo
    return f"%{termo}"


def pesquisar_produto(driver, termo: str) -> List[Dict]:
    abrir(driver, SGI_PRODUTOS_URL)
    termo_sgi = aplicar_curinga_sgi(termo)
    preencher(driver, By.CSS_SELECTOR, "#descricao_ilike", termo_sgi, limpar=True)
    clicar(driver, By.XPATH, "//button[contains(., 'Filtrar') or .//span[contains(@class,'glyphicon-search')]]")
    dormir(1.5)
    return ler_tabela_produtos(driver)


def ler_tabela_produtos(driver) -> List[Dict]:
    resultados: List[Dict] = []
    try:
        tabela = elemento(driver, By.CSS_SELECTOR, "#lista_padrao_produto", timeout=8)
    except Exception:
        return resultados

    linhas = tabela.find_elements(By.CSS_SELECTOR, "tbody tr")
    for tr in linhas:
        def pegar(css: str, attr: str = "data-value") -> str:
            try:
                el = tr.find_element(By.CSS_SELECTOR, css)
                return (el.get_attribute(attr) or el.text or "").strip()
            except Exception:
                return ""

        link_edit = ""
        try:
            a = tr.find_element(By.CSS_SELECTOR, "td.campo_codigo a[href*='/edit']")
            href = a.get_attribute("href") or ""
            link_edit = href
        except Exception:
            pass

        resultados.append({
            "codigo": pegar("td.campo_codigo"),
            "descricao": pegar("td.campo_descricao"),
            "subgrupo": pegar("td.campo_descricao_subgrupo"),
            "marca": pegar("td.campo_descricao_marca"),
            "referencia": pegar("td.campo_referencia_fornecedor"),
            "ncm": pegar("td.campo_numero_ncm"),
            "unidade": pegar("td.campo_descricao_unidade_medida"),
            "origem": pegar("td.campo_descricao_origem_produto"),
            "estoque": pegar("td.campo_quantidade_disponivel_estoque"),
            "preco": pegar("td.campo_produto_preco_padrao"),
            "edit_url": link_edit,
        })

    return resultados


def escolher_referencia_principal(nome: str, sku: str = "") -> str:
    """Escolhe 1 referência/modelo principal para manter só 2 tentativas no SGI.

    Prioridade: códigos com letras+números do nome, evitando SKU numérico completo
    e evitando capacidades/voltagens. Ex.: XT2623, A57, A576, CWN16, P50CRB.
    """
    refs = extrair_modelos_referencias(nome, sku)
    for ref in refs:
        r = (ref or "").strip().upper()
        if not r or "." in r:
            continue
        if any(ch.isalpha() for ch in r) and any(ch.isdigit() for ch in r):
            return r
    for ref in refs:
        r = (ref or "").strip().upper()
        if r and "." not in r:
            return r
    return ""


def gerar_tentativas_busca(produto: Dict) -> List[Dict]:
    """Gera somente 2 tentativas de busca no SGI.

    Regra atual MDL:
    1) Referência/modelo isolado com % na frente: %A57, %XT2623, %CWN16
    2) Marca + modelo com % na frente: %SAMSUNG A57

    O caractere % é aplicado em pesquisar_produto(), para aproveitar a busca parcial do SGI.
    """
    sku = (produto.get("sku") or "").strip()
    nome = produto.get("nome") or ""
    tentativas = []

    ref = escolher_referencia_principal(nome, sku)
    if ref:
        tentativas.append({"tipo": "Referência/modelo isolado", "termo": ref})

    mm = marca_modelo(nome, sku)
    if mm:
        tentativas.append({"tipo": "Marca + modelo", "termo": mm})

    # Remove duplicadas mantendo ordem.
    saida = []
    vistos = set()
    for t in tentativas:
        chave = t["termo"].strip().upper()
        if chave and chave not in vistos:
            vistos.add(chave)
            saida.append(t)
    return saida

def buscar_com_5_tentativas(driver, produto: Dict) -> List[Dict]:
    todos: List[Dict] = []
    vistos = set()
    tentativas = gerar_tentativas_busca(produto)

    for i, tentativa in enumerate(tentativas, start=1):
        termo = tentativa["termo"]
        tipo = tentativa["tipo"]
        log(f"🔎 Tentativa {i}/{len(tentativas)} ({tipo}): {termo}")
        try:
            encontrados = pesquisar_produto(driver, termo)
        except Exception as e:
            log(f"⚠️ Erro na busca '{termo}': {e}")
            encontrados = []

        log(f"   ↳ Resultados encontrados: {len(encontrados)}")
        for r in encontrados:
            chave = r.get("edit_url") or r.get("codigo") or r.get("descricao")
            if chave and chave not in vistos:
                vistos.add(chave)
                r["tentativa_origem"] = tipo
                r["termo_origem"] = termo
                todos.append(r)

        # Como agora começamos pela referência/modelo isolado, se encontrar resultado já podemos parar.
        # Isso evita buscas mais amplas que podem trazer duplicados ou confundir a decisão.
        if encontrados and tipo in ["Referência/modelo isolado", "Marca + modelo", "SKU/referência completa"]:
            break

    return todos


def abrir_edicao(driver, edit_url: str) -> None:
    if not edit_url:
        raise RuntimeError("Produto encontrado sem link de edição.")
    abrir(driver, edit_url)


def abrir_aba(driver, texto_aba: str) -> bool:
    try:
        clicar(driver, By.XPATH, f"//a[contains(normalize-space(.), '{texto_aba}')]")
        dormir(0.6)
        return True
    except Exception:
        return False


def preencher_formulario_produto(driver, produto: Dict, ncm_info: Dict, imagens_locais: Optional[List[Path]] = None) -> None:
    """Preenche dados principais. Só salva se a função salvar_produto for chamada depois."""
    imagens_locais = imagens_locais or []

    # Dados básicos
    abrir_aba(driver, "Dados Básicos")
    # Nome SGI já vem normalizado com cor/voltagem quando esses atributos existem no Woo.
    preencher(driver, By.CSS_SELECTOR, "#descricao", produto.get("nome_sgi") or produto.get("nome", ""), limpar=True)
    preencher_autocomplete(driver, "#autocompletar_subgrupo_produto_id", produto.get("subgrupo_sugerido") or "MÓVEIS")
    preencher_autocomplete(driver, "#autocompletar_marca_produto_id", produto.get("marca") or "DIVERSOS")
    preencher_autocomplete(driver, "#autocompletar_unidade_medida_id", UNIDADE_PADRAO)

    descricao = montar_descricao_completa(produto, ncm_info)
    try:
        set_contenteditable(driver, ".note-editable[contenteditable='true']", descricao)
    except Exception as e:
        log(f"⚠️ Não consegui preencher informações adicionais: {e}")

    # Imagem principal: primeiro botão de upload de arquivo encontrado.
    if imagens_locais:
        try:
            inputs_file = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if inputs_file:
                inputs_file[0].send_keys(str(imagens_locais[0].resolve()))
                log("📸 Imagem principal enviada.")
                dormir(1.5)
            else:
                log("⚠️ Nenhum input[type=file] visível para imagem principal. Pode exigir clique no botão Escolher.")
        except Exception as e:
            log(f"⚠️ Erro enviando imagem principal: {e}")

    # Tributação
    abrir_aba(driver, "Tributação")
    preencher_autocomplete(driver, "#autocompletar_origem_produto_id", ORIGEM_PADRAO)
    if ncm_info.get("ncm"):
        preencher_autocomplete(driver, "#autocompletar_ncm_id", ncm_info.get("ncm"))

    # Anexos extras
    if len(imagens_locais) > 1:
        abrir_aba(driver, "Anexos")
        enviar_anexos(driver, imagens_locais[1:])

    # Informações complementares
    abrir_aba(driver, "Informações Complementares")
    preencher(driver, By.CSS_SELECTOR, "#altura", numero_br(produto.get("altura") or 0), limpar=True)
    preencher(driver, By.CSS_SELECTOR, "#largura", numero_br(produto.get("largura") or 0), limpar=True)
    preencher(driver, By.CSS_SELECTOR, "#profundidade", numero_br(produto.get("profundidade") or 0), limpar=True)


def enviar_anexos(driver, imagens: List[Path]) -> None:
    for img in imagens:
        try:
            # Clica em adicionar anexo para cada imagem extra.
            try:
                clicar(driver, By.CSS_SELECTOR, ".adiciona-linha", timeout=4)
            except Exception:
                pass
            inputs_file = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if not inputs_file:
                log("⚠️ Não encontrei input file para anexo.")
                continue
            inputs_file[-1].send_keys(str(img.resolve()))
            log(f"📎 Anexo enviado: {img.name}")
            dormir(1.2)
        except Exception as e:
            log(f"⚠️ Erro enviando anexo {img.name}: {e}")


def montar_descricao_completa(produto: Dict, ncm_info: Dict) -> str:
    partes = []
    if produto.get("descricao_completa"):
        partes.append(produto["descricao_completa"])
    elif produto.get("descricao_curta"):
        partes.append(produto["descricao_curta"])

    detalhes = [
        f"Marca: {produto.get('marca') or ''}",
        f"Cor considerada no nome SGI: {produto.get('cor_sgi') or ''}",
        f"Voltagem considerada no nome SGI: {produto.get('voltagem_sgi') or ''}",
        f"Nome original WooCommerce: {produto.get('nome_original_woo') or produto.get('nome') or ''}",
        f"SKU/Referência WooCommerce: {produto.get('sku') or ''}",
        f"Categorias WooCommerce: {', '.join(produto.get('categorias') or [])}",
        f"NCM sugerido: {ncm_info.get('ncm') or 'Revisar'}",
        f"Motivo NCM: {ncm_info.get('motivo') or ''}",
    ]
    partes.append("\n".join([d for d in detalhes if d.strip()]))
    return "\n\n".join(partes).strip()


def salvar_produto(driver) -> None:
    if DRY_RUN:
        log("🧪 DRY_RUN=True: não cliquei em Salvar.")
        return
    clicar(driver, By.CSS_SELECTOR, "input.btn-salvar-produto")
    dormir(2)
    log("💾 Clique em Salvar executado.")


def atualizar_produto_existente(driver, produto: Dict, erp: Dict, ncm_info: Dict, imagens_locais: List[Path]) -> Dict:
    if DRY_RUN or not PERMITIR_ATUALIZACAO:
        return {"acao": "SIMULAR_ATUALIZACAO", "mensagem": "Atualização simulada; nada foi salvo."}
    abrir_edicao(driver, erp.get("edit_url", ""))
    preencher_formulario_produto(driver, produto, ncm_info, imagens_locais)
    salvar_produto(driver)
    return {"acao": "ATUALIZADO", "mensagem": "Produto atualizado no ERP."}


def cadastrar_produto_novo(driver, produto: Dict, ncm_info: Dict, imagens_locais: List[Path]) -> Dict:
    if DRY_RUN or not PERMITIR_CADASTRO_NOVO:
        return {"acao": "SIMULAR_CADASTRO", "mensagem": "Cadastro simulado; nada foi salvo."}
    abrir(driver, SGI_NOVO_PRODUTO_URL)
    preencher_formulario_produto(driver, produto, ncm_info, imagens_locais)
    salvar_produto(driver)
    return {"acao": "CADASTRADO", "mensagem": "Produto cadastrado no ERP."}
