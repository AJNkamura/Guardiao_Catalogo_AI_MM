"""
Lógica de verificação de status (ATIVO / INATIVO) por canal.

Critério combinado (definido pela Amanda a partir do fluxo manual atual):
  - Botão "Comprar" / "Adicionar ao carrinho" habilitado, E
  - Cotação de frete retornando um valor ao informar um CEP fictício de teste

Se qualquer uma das duas condições falhar (ou a página não existir/redirecionar
para busca vazia), o produto é marcado como INATIVO.

Duas estratégias:
  - "api": chamada HTTP direta a uma API pública/oficial do canal. Não sofre
    bloqueio de anti-bot porque é a própria interface pretendida para máquinas.
  - "browser": Playwright com um navegador real (headless), que renderiza JS
    e tem uma chance bem maior de passar por proteções básicas (Cloudflare/
    Akamai) do que uma requisição HTTP simples (era o problema do Apps Script).

IMPORTANTE — expectativa realista: mesmo com um navegador real, sites com
proteção anti-bot agressiva (ex.: Amazon, Shopee) podem eventualmente
bloquear, pedir captcha ou servir uma página diferente da usual. Por isso:
  - cada checagem tem retry com backoff e um "modo degradado" (marca como
    "NÃO VERIFICADO" em vez de forçar ATIVO/INATIVO errado);
  - o e-mail final separa claramente "INATIVO confirmado" de
    "não foi possível verificar" para não gerar falso alarme nem ocultar risco;
  - onde existir API oficial de seller (Amazon SP-API, por exemplo), migrar
    aquele canal de "browser" para "api" reduz drasticamente o risco de bloqueio.
"""
import time
import requests

from config import CANAIS, CEP_TESTE

STATUS_ATIVO = "ATIVO"
STATUS_INATIVO = "INATIVO"
STATUS_NAO_VERIFICADO = "NÃO VERIFICADO"


def checar_produto(canal_key, id_produto, link_planilha=""):
    """Ponto de entrada único: decide API vs browser e devolve um dict padronizado."""
    cfg = CANAIS.get(canal_key)
    if not cfg:
        return _resultado(STATUS_NAO_VERIFICADO, link_planilha, f"Canal '{canal_key}' não configurado")

    for tentativa in range(3):
        try:
            if cfg["method"] == "api":
                return _checar_via_api(canal_key, cfg, id_produto, link_planilha)
            else:
                return _checar_via_browser(canal_key, cfg, id_produto, link_planilha)
        except Exception as e:  # noqa: BLE001 — queremos capturar qualquer falha de rede/parse
            if tentativa == 2:
                return _resultado(STATUS_NAO_VERIFICADO, link_planilha, f"Erro após 3 tentativas: {e}")
            time.sleep(2 * (tentativa + 1))


def _resultado(status, link, observacao=""):
    return {"status": status, "link": link, "observacao": observacao}


# --------------------------------------------------------------------------
# Mercado Livre — API pública (sem necessidade de login/seller account)
# --------------------------------------------------------------------------
def _checar_via_api(canal_key, cfg, id_produto, link_planilha):
    url = cfg["api_url"].format(id=id_produto)
    resp = requests.get(url, timeout=10)
    link = link_planilha or cfg["url_produto"].format(id=id_produto)

    if resp.status_code == 404:
        return _resultado(STATUS_INATIVO, link, "Item não encontrado na API (removido/inexistente)")
    resp.raise_for_status()
    data = resp.json()
    status_ml = data.get("status")  # active | paused | closed | under_review
    if status_ml == "active":
        return _resultado(STATUS_ATIVO, link)
    return _resultado(STATUS_INATIVO, link, f"status da API: {status_ml}")


# --------------------------------------------------------------------------
# Demais canais — Playwright (navegador headless real)
# --------------------------------------------------------------------------
# Seletores por canal: ajustar conforme o HTML real de cada site (fazer uma
# inspeção manual — DevTools > Elements — em uma página de produto ativo e
# uma inativa/sem estoque para confirmar os textos/seletores abaixo).
SELETORES = {
    "amazon": {
        "botao_comprar": ["#buy-now-button", "#add-to-cart-button"],
        "indisponivel_textos": ["não está disponível", "no momento, este item está indisponível"],
        "cep_input": "#glow-ingress-line2",
    },
    "casas_bahia": {
        "botao_comprar": ["button[data-testid='buy-button']", "button:has-text('Comprar')"],
        "indisponivel_textos": ["produto indisponível", "produto não encontrado"],
        "cep_input": "input[name='cep']",
    },
    "shopee": {
        "botao_comprar": ["button:has-text('Adicionar ao carrinho')", "button:has-text('Comprar agora')"],
        "indisponivel_textos": ["produto não encontrado", "esgotado"],
        "cep_input": None,  # Shopee calcula frete pelo endereço da conta logada; ver observação no README
    },
    "magazine_luiza": {
        "botao_comprar": ["button[data-testid='comprar']", "button:has-text('Comprar')"],
        "indisponivel_textos": ["produto indisponível", "produto não encontrado"],
        "cep_input": "input[name='cep']",
    },
    "leroy_merlin": {
        "botao_comprar": ["button:has-text('Adicionar ao carrinho')", "button:has-text('Comprar')"],
        "indisponivel_textos": ["produto indisponível", "produto não encontrado"],
        "cep_input": "input[name='cep']",
    },
}


def _checar_via_browser(canal_key, cfg, id_produto, link_planilha):
    # import local para não exigir Playwright instalado em quem só usa a parte de API/planilha
    from playwright.sync_api import sync_playwright

    url = link_planilha or cfg["url_produto"].format(id=id_produto)
    seletor = SELETORES.get(canal_key, {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        contexto = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        pagina = contexto.new_page()
        try:
            pagina.goto(url, timeout=20000, wait_until="domcontentloaded")
            pagina.wait_for_timeout(1500)  # dá tempo pro JS renderizar

            texto_pagina = pagina.content().lower()
            for termo in seletor.get("indisponivel_textos", []):
                if termo.lower() in texto_pagina:
                    return _resultado(STATUS_INATIVO, url, f"Página indica indisponibilidade ('{termo}')")

            botao_ok = False
            for sel in seletor.get("botao_comprar", []):
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() > 0 and loc.is_enabled(timeout=3000):
                        botao_ok = True
                        break
                except Exception:
                    continue

            frete_ok = True  # default: canal sem cotação de frete configurada (ex.: Shopee)
            cep_sel = seletor.get("cep_input")
            if cep_sel:
                frete_ok = False
                try:
                    campo = pagina.locator(cep_sel).first
                    if campo.count() > 0:
                        campo.fill(CEP_TESTE)
                        pagina.keyboard.press("Enter")
                        pagina.wait_for_timeout(2500)
                        # heurística simples: se apareceu "R$" ou "grátis" perto da cotação, consideramos ok
                        conteudo_pos = pagina.content().lower()
                        frete_ok = ("r$" in conteudo_pos) or ("grátis" in conteudo_pos) or ("frete" in conteudo_pos)
                except Exception:
                    frete_ok = False

            if botao_ok and frete_ok:
                return _resultado(STATUS_ATIVO, url)
            elif not botao_ok:
                return _resultado(STATUS_INATIVO, url, "Botão de compra ausente/desabilitado")
            else:
                return _resultado(STATUS_INATIVO, url, "Frete não retornou cotação com o CEP de teste")
        finally:
            browser.close()
