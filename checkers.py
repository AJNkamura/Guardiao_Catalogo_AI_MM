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
import json
import os
import re
import time
import requests

from config import CEP_TESTE, GEMINI_API_KEY, GEMINI_MODEL

STATUS_ATIVO = "ATIVO"
STATUS_INATIVO = "INATIVO"
STATUS_NAO_VERIFICADO = "NÃO VERIFICADO"

PASTA_DEBUG_SCREENSHOTS = "debug_screenshots"


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
    if not link:
        return _resultado(STATUS_NAO_VERIFICADO, link, "Sem link de produto na aba De-Para")

    # 1) tenta primeiro o endpoint interno que o próprio site da Shopee usa
    #    pra carregar os dados do produto (sem abrir navegador nenhum) — mais
    #    rápido e não passa pela parede de login/idioma da página pública.
    #    Se não der pra extrair o ID do link, ou a chamada não devolver um
    #    status claro (bloqueada, formato mudou, etc.), cai pro método via
    #    navegador abaixo.
    resultado_api = None
    try:
        resultado_api = _checar_shopee_api(link)
    except Exception as e:
        print(f"  (aviso: API interna da Shopee falhou, tentando via navegador: {e})")
    if resultado_api is not None:
        return resultado_api

    # 2) fallback: navegador real (Playwright) — mais lento e sujeito à
    #    parede de login/idioma, mas cobre o caso de a API interna ter
    #    mudado ou não ter devolvido nada.
    from playwright.sync_api import sync_playwright

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
            pagina.wait_for_timeout(2000)

            _fechar_tela_idioma(pagina)

            _salvar_screenshot_debug(pagina, link)

            texto_visivel = ""
            try:
                texto_visivel = pagina.inner_text("body")
            except Exception:
                pass

            # A Shopee pode exigir login pra mostrar a página do produto quando
            # detecta acesso automatizado (visto nos prints de debug) — isso não
            # é o mesmo que o produto estar inativo, então checa isso ANTES de
            # qualquer outra lógica e devolve NÃO VERIFICADO (não INATIVO) pra
            # não gerar falso alarme.
            texto_lower_check = texto_visivel.lower()
            if any(
                termo in texto_lower_check
                for termo in ("login necessário", "faça login", "ainda não está logado")
            ):
                return _resultado(
                    STATUS_NAO_VERIFICADO, link,
                    "Shopee exigiu login pra ver a página (bloqueio de acesso automatizado) [via navegador]",
                )

            # 1) tenta a IA primeiro (mais robusta a falso positivo por palavra-chave
            #    solta na página) — se não tiver GEMINI_API_KEY configurada, ou se a
            #    chamada falhar por qualquer motivo, cai no método por palavra-chave.
            # Guarda SEMPRE o motivo de não ter usado a IA (não configurada, erro na
            # chamada, ou a própria IA achou que a página não é de produto real) —
            # isso aparece na observação, pra não precisar abrir o log do GitHub
            # Actions pra saber o que aconteceu.
            resultado_ia = None
            motivo_sem_ia = "GEMINI_API_KEY não configurada"
            if GEMINI_API_KEY:
                try:
                    resultado_ia = _perguntar_gemini(texto_visivel)
                    if resultado_ia is not None and resultado_ia.get("disponivel") is None:
                        motivo_sem_ia = (
                            "IA identificou a página como bloqueio/captcha/erro, não um "
                            f"produto real ({resultado_ia.get('motivo', 'sem detalhe')})"
                        )
                except Exception as e:
                    resultado_ia = None
                    motivo_sem_ia = f"chamada à IA falhou: {e}"
                    print(f"  (aviso: chamada à IA falhou, usando método por palavra-chave: {e})")

            if resultado_ia is not None and resultado_ia.get("disponivel") is not None:
                motivo = f"(IA) {resultado_ia.get('motivo', '')}"
                if resultado_ia["disponivel"]:
                    return _resultado(STATUS_ATIVO, link, motivo)
                return _resultado(STATUS_INATIVO, link, motivo)

            # 2) método antigo, por palavra-chave (fallback) — sempre explica no
            #    final da observação por que não usou a IA nessa checagem.
            texto = texto_visivel.lower() or pagina.content().lower()
            for termo in ("produto não encontrado", "esgotado", "indisponível"):
                if termo in texto:
                    return _resultado(
                        STATUS_INATIVO, link,
                        f"Página indica indisponibilidade ('{termo}') [sem IA: {motivo_sem_ia}]",
                    )

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
            if botao_ok:
                return _resultado(STATUS_ATIVO, link, f"[sem IA: {motivo_sem_ia}]")
            return _resultado(
                STATUS_INATIVO, link,
                f"Botão de compra ausente/desabilitado [sem IA: {motivo_sem_ia}]",
            )
        finally:
            browser.close()


def _extrair_shopid_itemid(link):
    """Links de produto da Shopee têm o formato
    '.../nome-do-produto-i.<shopid>.<itemid>' — extrai os 2 números. Se o
    link for um encurtado (ex.: s.shopee.com.br/...), tenta seguir o
    redirecionamento primeiro pra chegar no link canônico."""
    if not link:
        return None, None
    m = re.search(r"-i\.(\d+)\.(\d+)", link)
    if m:
        return m.group(1), m.group(2)
    try:
        resp = requests.get(link, timeout=10, allow_redirects=True)
        m = re.search(r"-i\.(\d+)\.(\d+)", resp.url)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None, None


def _checar_shopee_api(link):
    """Chama direto o endpoint interno que o próprio site da Shopee usa pra
    carregar os dados do produto (o mesmo que o navegador chamaria por
    baixo dos panos) — sem abrir navegador, então não passa pela parede de
    login/idioma. Não é uma API pública documentada/oficial: pode parar de
    funcionar se a Shopee mudar o formato. Retorna None se não conseguir um
    status confiável (aí quem chamou cai pro método via navegador)."""
    shopid, itemid = _extrair_shopid_itemid(link)
    if not shopid or not itemid:
        return None

    url = f"https://shopee.com.br/api/v4/item/get?itemid={itemid}&shopid={shopid}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": link,
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
    try:
        corpo = resp.json()
    except ValueError:
        return None

    dados = corpo.get("data")
    if not dados:
        # resposta sem "data" costuma ser erro/bloqueio (ex.: {"error": 4, ...})
        return None

    item_status = dados.get("item_status", "")
    if item_status == "NORMAL":
        return _resultado(STATUS_ATIVO, link, "(API interna Shopee) status: NORMAL")
    if item_status:
        return _resultado(STATUS_INATIVO, link, f"(API interna Shopee) status: {item_status}")
    return None


def _fechar_tela_idioma(pagina):
    """A Shopee às vezes mostra uma tela inicial de 'Selecione seu idioma'
    antes da página do produto — normalmente na primeira visita da sessão,
    quando não há cookie de idioma salvo (é sempre o caso aqui, já que cada
    checagem abre uma sessão nova). Se aparecer, clica em 'Português (BR)' e
    espera a página do produto real carregar. Se não aparecer, não faz nada
    (já deve estar direto na página do produto)."""
    try:
        botao = pagina.locator("text=Português (BR)").first
        if botao.count() > 0 and botao.is_visible(timeout=3000):
            botao.click()
            pagina.wait_for_timeout(3000)
            try:
                pagina.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
    except Exception:
        pass


def _salvar_screenshot_debug(pagina, link):
    """Salva um print da página pra inspeção manual (sobe como artifact no
    GitHub Actions) — ajuda a diagnosticar se o site está bloqueando o
    navegador automático (página de captcha/erro) em vez de mostrar o produto."""
    try:
        os.makedirs(PASTA_DEBUG_SCREENSHOTS, exist_ok=True)
        nome = re.sub(r"[^0-9]", "", link)[-15:] or "shopee"
        pagina.screenshot(path=f"{PASTA_DEBUG_SCREENSHOTS}/shopee_{nome}.png", full_page=True)
    except Exception:
        pass  # debug não pode quebrar a checagem principal


def _perguntar_gemini(texto_pagina):
    """Manda o texto visível da página pro Gemini e pede pra julgar se o
    produto está disponível. Retorna None se GEMINI_API_KEY não estiver
    configurada (aí quem chamou cai no método por palavra-chave)."""
    if not GEMINI_API_KEY or not texto_pagina:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )
    prompt = (
        "Você está analisando o texto visível (extraído por um navegador automático) de uma "
        "página de produto de e-commerce (Shopee). Baseado SOMENTE no texto abaixo, determine "
        "se esse produto está disponível para compra agora (tem botão de comprar/adicionar ao "
        "carrinho habilitado, sem aviso de esgotado/indisponível/anúncio removido).\n\n"
        "Se o texto parecer ser uma página de erro, bloqueio, captcha, verificação de robô, ou "
        "não parecer ser a página de um produto de verdade, marque \"disponivel\" como null.\n\n"
        f"TEXTO DA PÁGINA:\n{texto_pagina[:8000]}\n\n"
        'Responda SOMENTE com um JSON, sem markdown, no formato exato: '
        '{"disponivel": true, "motivo": "razão em até 15 palavras"} '
        "(disponivel pode ser true, false ou null)."
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=body, timeout=20)
    resp.raise_for_status()
    texto_resp = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    texto_resp = texto_resp.strip()
    if texto_resp.startswith("```"):
        texto_resp = texto_resp.strip("`")
        texto_resp = texto_resp.replace("json\n", "", 1).replace("json", "", 1)
    return json.loads(texto_resp)
