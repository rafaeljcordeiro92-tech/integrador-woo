# -*- coding: utf-8 -*-
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (
    CHROME_USER_DATA_DIR,
    HEADLESS,
    PAUSA_ENTRE_ACOES,
    SELENIUM_TIMEOUT,
    SGI_BASE_URL,
    SGI_LOGIN_URL,
    SGI_SENHA,
    SGI_TENTAR_LOGIN_AUTOMATICO,
    SGI_USUARIO,
)
from logger_app import log


def criar_driver() -> webdriver.Chrome:
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=pt-BR")
    options.add_argument("--start-maximized")

    # Ajuda em algumas telas novas do Chrome/Selenium.
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if CHROME_USER_DATA_DIR:
        options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)
    return driver


def wait(driver, timeout: Optional[int] = None) -> WebDriverWait:
    return WebDriverWait(driver, timeout or SELENIUM_TIMEOUT)


def dormir(segundos: Optional[float] = None) -> None:
    time.sleep(segundos if segundos is not None else PAUSA_ENTRE_ACOES)


def abrir(driver, url: str) -> None:
    driver.get(url)
    dormir(0.8)


def elemento(driver, by: By, seletor: str, timeout: Optional[int] = None):
    return wait(driver, timeout).until(EC.presence_of_element_located((by, seletor)))


def clicavel(driver, by: By, seletor: str, timeout: Optional[int] = None):
    return wait(driver, timeout).until(EC.element_to_be_clickable((by, seletor)))


def clicar(driver, by: By, seletor: str, timeout: Optional[int] = None) -> None:
    el = clicavel(driver, by, seletor, timeout)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    dormir(0.1)
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)
    dormir()


def preencher(driver, by: By, seletor: str, valor: str, limpar: bool = True, enter: bool = False) -> None:
    el = elemento(driver, by, seletor)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    if limpar:
        try:
            el.clear()
        except Exception:
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
    el.send_keys(str(valor or ""))
    if enter:
        el.send_keys(Keys.ENTER)
    dormir()


def preencher_autocomplete(driver, css: str, valor: str) -> None:
    preencher(driver, By.CSS_SELECTOR, css, valor, limpar=True, enter=False)
    dormir(1.1)
    try:
        ativo = driver.switch_to.active_element
        ativo.send_keys(Keys.ARROW_DOWN)
        dormir(0.1)
        ativo.send_keys(Keys.ENTER)
        dormir(0.5)
    except Exception:
        pass


def set_contenteditable(driver, css: str, texto: str) -> None:
    el = elemento(driver, By.CSS_SELECTOR, css)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].innerHTML = arguments[1];", el, (texto or "").replace("\n", "<br>"))
    dormir()



def _clicar_prosseguir_local_trabalho(driver) -> bool:
    """Após login, o Sólidus pode pedir seleção de filial/local de trabalho.
    Quando aparecer /login/informa_local_de_trabalho, clica no botão PROSSEGUIR.
    """
    try:
        url = (driver.current_url or "").lower()
        html = (driver.page_source or "").lower()
        if "informa_local_de_trabalho" not in url and "botao_prosseguir_informa_local_trabalho" not in html:
            return False

        log("🏢 Tela de local de trabalho detectada. Clicando em PROSSEGUIR...")
        seletores = [
            "#botao_prosseguir_informa_local_trabalho",
            "input[value='PROSSEGUIR']",
            "input[type='submit'][value*='PROSSEGUIR']",
            "button[type='submit']",
        ]
        for css in seletores:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, css):
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        dormir(0.2)
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        dormir(2.0)
                        return True
            except Exception:
                pass
    except Exception as e:
        log(f"⚠️ Não consegui confirmar local de trabalho automaticamente: {e}")
    return False


def _ir_para_produtos_apos_login(driver) -> bool:
    """Garante que passou por login/local de trabalho e chegou em /produtos."""
    for _ in range(5):
        _clicar_prosseguir_local_trabalho(driver)
        try:
            driver.get(SGI_BASE_URL.rstrip("/") + "/produtos")
            dormir(1.5)
            url = (driver.current_url or "").lower()
            html = (driver.page_source or "").lower()
            if "informa_local_de_trabalho" in url or "botao_prosseguir_informa_local_trabalho" in html:
                _clicar_prosseguir_local_trabalho(driver)
                continue
            if "login" in url:
                return False
            if "descricao_ilike" in html or "lista_padrao_produto" in html or "/produtos/new" in html:
                return True
            if "produtos" in url and "login" not in url:
                return True
        except Exception:
            pass
        dormir(1.0)
    return False

def esta_logado(driver) -> bool:
    """Confirma login tentando abrir diretamente a tela de produtos.
    Também trata a etapa extra do Sólidus: /login/informa_local_de_trabalho.
    """
    try:
        return _ir_para_produtos_apos_login(driver)
    except Exception:
        return False


def _primeiro_visivel(driver, seletores):
    for css in seletores:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, css)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    return el, css
        except Exception:
            pass
    return None, None


def _set_valor_input(driver, el, valor):
    """Preenche input disparando eventos JS, porque algumas telas do SGI ignoram send_keys simples."""
    try:
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        el.send_keys(str(valor or ""))
    except Exception:
        pass

    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            el.focus();
            el.value = val;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
            """,
            el,
            str(valor or ""),
        )
    except Exception:
        pass
    dormir(0.2)


def _clicar_entrar(driver) -> bool:
    seletores = [
        "button[type='submit']",
        "input[type='submit']",
        "button.btn",
        ".btn",
        "button",
        "input[type='button']",
    ]
    for css in seletores:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, css):
                if not el.is_displayed() or not el.is_enabled():
                    continue
                texto = ((el.text or "") + " " + (el.get_attribute("value") or "")).upper()
                if "ENTRAR" in texto or "LOGIN" in texto or css in ["button[type='submit']", "input[type='submit']"]:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    dormir(0.1)
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    return True
        except Exception:
            pass
    return False


def aguardar_login_manual(driver, segundos: int = 120) -> bool:
    """Fallback: deixa a janela aberta para o usuário logar manualmente."""
    log(f"⏳ Aguardando login manual no SGI por até {segundos}s...")
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            url = (driver.current_url or "").lower()
            if "informa_local_de_trabalho" in url:
                _clicar_prosseguir_local_trabalho(driver)
            if "login" not in url or "informa_local_de_trabalho" in url:
                if esta_logado(driver):
                    log("✅ Login manual confirmado.")
                    return True
            # Se ainda está na tela login, apenas aguarda.
        except Exception:
            pass
        time.sleep(2)
    log("⚠️ Tempo de login manual esgotado.")
    return False


def tentar_login(driver) -> None:
    if esta_logado(driver):
        log("✅ SGI já está logado.")
        return

    abrir(driver, SGI_LOGIN_URL)

    if not SGI_TENTAR_LOGIN_AUTOMATICO:
        log("ℹ️ Login automático desativado. Faça login manual na janela aberta.")
        aguardar_login_manual(driver, 180)
        return

    log("🔐 Tentando login automático no SGI...")

    if not SGI_USUARIO or not SGI_SENHA:
        log("⚠️ SGI_USUARIO/SGI_SENHA não configurados. Faça login manual na janela aberta.")
        aguardar_login_manual(driver, 180)
        return

    # A tela do Sólidus Smart pode vir apenas com placeholder 'Usuário' e 'Senha'.
    possiveis_usuarios = [
        "input[placeholder*='Usuário']",
        "input[placeholder*='Usuario']",
        "input[placeholder*='usuário']",
        "input[placeholder*='usuario']",
        "input[name='usuario']",
        "input[name='login']",
        "input[name='email']",
        "input[type='email']",
        "#usuario",
        "#email",
        "#login",
        "input[type='text']",
        "input:not([type])",
    ]
    possiveis_senhas = [
        "input[placeholder*='Senha']",
        "input[placeholder*='senha']",
        "input[name='senha']",
        "input[name='password']",
        "input[type='password']",
        "#senha",
        "#password",
    ]

    campo_user, seletor_user = _primeiro_visivel(driver, possiveis_usuarios)
    campo_senha, seletor_senha = _primeiro_visivel(driver, possiveis_senhas)

    if not campo_user or not campo_senha:
        log("⚠️ Não encontrei os campos de login automaticamente. Faça login manual.")
        aguardar_login_manual(driver, 180)
        return

    log(f"✅ Campos de login encontrados: usuário={seletor_user} | senha={seletor_senha}")

    _set_valor_input(driver, campo_user, SGI_USUARIO)
    _set_valor_input(driver, campo_senha, SGI_SENHA)

    if not _clicar_entrar(driver):
        try:
            campo_senha.send_keys(Keys.ENTER)
        except Exception:
            pass

    dormir(4)

    if esta_logado(driver):
        log("✅ Login SGI realizado.")
        return

    log("⚠️ Login SGI automático não confirmou. Pode ser senha diferente, captcha, 2FA ou seletor do botão.")
    log("👉 Faça o login manual nessa mesma janela; o robô vai continuar quando detectar /produtos.")
    aguardar_login_manual(driver, 180)
