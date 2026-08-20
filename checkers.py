"""
Verificação de status (ATIVO / INATIVO) por canal. Escopo atual: Mercado
Livre e Shopee (os 2 canais com De-Para pronto na aba GMV_id_prdmkt).

Critério (definido pela Amanda a partir do fluxo manual atual):
  - Botão "Comprar" / "Adicionar ao carrinho" habilitado, E
  - Cotação de frete retornando um valor ao informar um CEP fictício de teste

Mercado Livre usa a API pública oficial (não sofre bloqueio de anti-bot,
porque é a própria interface pretendida para máquinas). Shopee usa Playwright
(navegador headless real) — sites com proteção anti-bot agressiva podem
eventualmente bloquear mesmo assim; por isso toda checagem tem retry e um
status "NÃO VERIFICADO" em vez de forçar um resultado errado.
"""
import time
import requests

from config import CEP_TESTE

STATUS_ATIVO = "ATIVO"
STATUS_INATIVO = "INATIVO"
STATUS_NAO_VERIFICADO = "NÃO VERIFICADO"


def checar_produto(canal_key, id_marketplace_produto, link=""):
    for tentativa in range(3):
        try:
            if canal_key == "mercado_livre":
                return _checar_mercado_livre(id_marketplace_produto, link)
            elif canal_key == "shopee":
                return _checar_shopee(link)
            else:
                return _resultado(STATUS_NAO_VERIFICADO, link, f"Canal '{canal_key}' sem checador implementado")
        except Exception as e:  # noqa: BLE001
            if tentativa == 2:
                return _resultado(STATUS_NAO_VERIFICADO, link, f"Erro após 3 tentativas: {e}")
            time.sleep(2 * (tentativa + 1))


def _resultado(status, link, observacao=""):
    return {"status": status, "link": link, "observacao": observacao}


def _checar_mercado_livre(mlb_id, link):
    url = f"https://api.mercadolibre.com/items/{mlb_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 404:
        return _resultado(STATUS_INATIVO, link, "Item não encontrado na API (removido/inexistente)")
    resp.raise_for_status()
    status_ml = resp.json().get("status")  # active | paused | closed | under_review
    if status_ml == "active":
        return _resultado(STATUS_ATIVO, link)
    return _resultado(STATUS_INATIVO, link, f"status da API: {status_ml}")


def _checar_shopee(link):
    from playwright.sync_api import sync_playwright

    if not link:
        return _resultado(STATUS_NAO_VERIFICADO, link, "Sem link de produto na aba De-Para")

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
            pagina.goto(link, timeout=20000, wait_until="domcontentloaded")
            pagina.wait_for_timeout(1500)
            texto = pagina.content().lower()

            for termo in ("produto não encontrado", "esgotado", "indisponível"):
                if termo in texto:
                    return _resultado(STATUS_INATIVO, link, f"Página indica indisponibilidade ('{termo}')")

            botao_ok = False
            for sel in ["button:has-text('Adicionar ao carrinho')", "button:has-text('Comprar agora')"]:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() > 0 and loc.is_enabled(timeout=3000):
                        botao_ok = True
                        break
                except Exception:
                    continue

            # Shopee calcula frete pelo endereço salvo na conta logada, não por um
            # campo de CEP na página pública — então aqui o critério é só o botão.
            # Se quisermos replicar a cotação de frete com CEP fictício, precisamos
            # de uma conta Shopee logada no navegador (ajustar se for bloqueante).
            if botao_ok:
                return _resultado(STATUS_ATIVO, link)
            return _resultado(STATUS_INATIVO, link, "Botão de compra ausente/desabilitado")
        finally:
            browser.close()
