"""
Configuração central do monitor de produtos.

Todas as credenciais/segredos vêm de variáveis de ambiente — nunca hardcode
valores aqui. No GitHub Actions elas vêm de Secrets; localmente, de um
arquivo .env (não versionado).
"""
import os

# --- Planilha Google Sheets -------------------------------------------------
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1Fnv-dtRYB4lxOpiriOOEq9OhHvkfPYa0tgIARQcpSdY",  # planilha "Monitoramento_GMV"
)
ABA_GMV = "Monitoramento_GMV"
ABA_ALERTAS = "Alertas"

# Caminho (ou conteúdo, ver sheets.py) do JSON da service account do Google Cloud
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# --- E-mail ------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")          # conta que envia o e-mail
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # app password / senha SMTP
EMAIL_RECIPIENTS = [
    e.strip() for e in os.environ.get("EMAIL_RECIPIENTS", "").split(",") if e.strip()
]

# --- CEP fictício usado para cotar frete -------------------------------------
# Use um CEP real de um centro de distribuição/loja para que a cotação de frete
# funcione (CEPs totalmente inválidos são rejeitados por alguns sites).
CEP_TESTE = os.environ.get("CEP_TESTE", "01310-100")

# --- Regras de negócio ---------------------------------------------------------
DIAS_HISTORICO_SEM_VENDA = 6  # "dias sem vendas (últimos 6 dias)" — conforme doc do projeto

# --- Canais --------------------------------------------------------------------
# method: "api"       -> chamada HTTP direta a uma API pública/oficial (mais confiável)
#         "browser"   -> Playwright, simula navegação real (mitiga anti-bot básico)
CANAIS = {
    "mercado_livre": {
        "label": "Mercado Livre",
        "method": "api",
        # API pública do Mercado Livre — não precisa de login/seller account.
        # status possíveis: "active", "paused", "closed", "under_review"
        "api_url": "https://api.mercadolibre.com/items/{id}",
        "url_produto": "https://produto.mercadolivre.com.br/{id}",
    },
    "amazon": {
        "label": "Amazon",
        "method": "browser",
        "url_produto": "https://www.amazon.com.br/dp/{id}",
        # Se a MadeiraMadeira tiver acesso à Amazon Selling Partner API (SP-API),
        # trocar este canal para method="api" é MUITO mais confiável que scraping.
    },
    "casas_bahia": {
        "label": "Casas Bahia",
        "method": "browser",
        "url_produto": "https://www.casasbahia.com.br/produto/{id}",
    },
    "shopee": {
        "label": "Shopee",
        "method": "browser",
        # formato observado no doc: shopee.com.br/product/{shop_id}/{item_id}
        # o ID no sheet precisa vir como "shop_id-item_id" (ver sheets.py: parse_shopee_id)
        "url_produto": "https://shopee.com.br/product/{shop_id}/{item_id}",
    },
    "magazine_luiza": {
        "label": "Magazine Luiza",
        "method": "browser",
        # PENDENTE: confirmar com a Amanda o padrão de URL/ID usado na planilha.
        # Padrão mais comum do Magalu é https://www.magazineluiza.com.br/p/{id}/
        "url_produto": "https://www.magazineluiza.com.br/p/{id}/",
    },
    "leroy_merlin": {
        "label": "Leroy Merlin",
        "method": "browser",
        # PENDENTE: doc do projeto não trouxe exemplo de URL. Ajustar quando tivermos
        # um link de produto real para inspecionar o padrão.
        "url_produto": "https://www.leroymerlin.com.br/{id}",
    },
}
