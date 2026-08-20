"""
Configuração central do monitor de produtos.

Credenciais vêm todas de variáveis de ambiente — nunca hardcode segredos aqui.
No GitHub Actions elas vêm de Secrets; localmente, de um arquivo .env (não
versionado).
"""
import os

# --- Planilha Google Sheets -------------------------------------------------
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1Fnv-dtRYB4lxOpiriOOEq9OhHvkfPYa0tgIARQcpSdY",
)

# gid da aba do dashboard de GMV (vem da URL: .../edit?gid=2103336496).
# Usamos o gid (não o nome) pra resolver a aba, porque o nome pode ser
# renomeado sem avisar e o gid nunca muda.
GID_MONITORAMENTO_GMV = 2103336496

# Aba do De-Para (essa já tem nome fixo, criada pela Amanda)
ABA_DEPARA = "GMV_id_prdmkt"

ABA_ALERTAS = "Alertas"

# --- Credenciais Google (OAuth como usuário, não service account) -----------
# Motivo: a política de compartilhamento externo do Workspace da MM bloqueia
# service accounts (identidade "de fora" do domínio). Autenticando como o
# próprio usuário (que já tem acesso à planilha) esse bloqueio não se aplica.
# Gerar o refresh token uma única vez localmente com scripts/get_token.py.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REFRESH_TOKEN = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")

# --- E-mail (Gmail convencional, com senha de app) --------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_RECIPIENTS = [
    e.strip() for e in os.environ.get("EMAIL_RECIPIENTS", "").split(",") if e.strip()
]

# --- CEP fictício usado para cotar frete -------------------------------------
CEP_TESTE = os.environ.get("CEP_TESTE", "01310-100")

# --- Canais em produção (escopo inicial: só os 2 confirmados) ----------------
# Cada bloco na aba de Monitoramento_GMV ocupa 8 colunas:
# ID Produto | Nome Produto | data1..data5 | Total geral
# Cada bloco na aba GMV_id_prdmkt ocupa 5 colunas (ordem confirmada com a Amanda):
CANAIS = {
    "mercado_livre": {
        "label": "Mercado Livre",
        "method": "api",  # API pública do Mercado Livre, não precisa de login
        "api_url": "https://api.mercadolibre.com/items/{id}",
        "gmv_col_inicio": "A",   # bloco na aba de Monitoramento_GMV
        "depara_col_inicio": "A",  # bloco na aba GMV_id_prdmkt
        # ordem confirmada: ID Marketplace | ID Produto | ID Produto Marketplace | Link no Marketplace | Nome do Marketplace
        "depara_offset_id_produto": 1,
        "depara_offset_id_marketplace_produto": 2,
        "depara_offset_link": 3,
    },
    "shopee": {
        "label": "Shopee",
        "method": "browser",  # Playwright — Shopee não tem API pública simples
        "url_produto": "{link}",  # o link já vem pronto da aba De-Para
        "gmv_col_inicio": "J",
        "depara_col_inicio": "G",
        # ordem confirmada: Nome do Marketplace | ID Marketplace | ID Produto | ID Produto Marketplace | Link no Marketplace
        "depara_offset_id_produto": 2,
        "depara_offset_id_marketplace_produto": 3,
        "depara_offset_link": 4,
    },
}
