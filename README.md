# Monitor de Produtos — Mercado Livre + Shopee

Automação do fluxo manual: detectar produtos (do painel de GMV por canal) sem
venda no dia anterior e verificar se estão INATIVOS no canal, atualizando a
aba **Alertas** da planilha e disparando um e-mail resumo diário.

**Escopo atual: Mercado Livre e Shopee.** Os outros canais (Amazon, Leroy
Merlin, Casas Bahia, Magazine Luiza) ainda não têm De-Para (ID interno →
ID/link do marketplace) pronto — dá pra adicionar depois seguindo o mesmo
padrão em `config.py`.

## Por que rodar no GitHub Actions (e não no Claude)

Esse script faz chamadas de rede reais para o Mercado Livre/Shopee
(Playwright) e para a API do Google Sheets — coisas que o ambiente do Claude
não alcança (rede de saída restrita por allowlist) e que, mais importante,
precisam ser um sistema compartilhado que o time consiga ver/rodar/manter,
não algo amarrado a uma conversa individual. Por isso: **GitHub Actions roda
o pipeline inteiro**, com cron diário.

## Como a leitura da planilha funciona

Em vez de "service account" do Google Cloud (que a política de
compartilhamento externo do Workspace da MadeiraMadeira bloqueia — só aceita
compartilhar com contas @madeiramadeira.com.br), a automação se autentica
**como o próprio usuário** (você), usando OAuth. Isso não é um novo
compartilhamento — é o script usando o acesso que você já tem — então a
trava do TI não se aplica.

Duas abas são lidas, ambas resolvidas de forma resiliente (por `gid` ou nome
exato, não por posição fixa):

- **Monitoramento_GMV** (gid `2103336496`): bloco do Mercado Livre a partir
  da coluna A, bloco do Shopee a partir da coluna J. Cada bloco: `ID Produto
  | Nome Produto | 5 datas | Total geral`. Um produto é "zerado" quando a
  coluna da data mais recente é R$ 0,00.
- **GMV_id_prdmkt** (De-Para): bloco Meli em A2:E2 (`ID Marketplace | ID
  Produto | ID Produto Marketplace | Link no Marketplace | Nome do
  Marketplace`), bloco Shopee em G2:K2 (mesma info, ordem diferente).

## Setup necessário (uma vez só)

### 1. Repositório GitHub
Copiar esta pasta para dentro do repo `Guardiao_Catalogo_AI_MM` (ou onde
preferir), mantendo a estrutura `.github/workflows/`, `scripts/`,
`requirements.txt`.

### 2. Autorização do Google (OAuth, não service account)
No projeto do Google Cloud que você já criou na sua conta pessoal
(`guardiao-catalogo-mm`):

1. Vá em **APIs e Serviços → Tela de consentimento OAuth**. Tipo: **Externo**.
   Preencha nome do app e e-mail de suporte. Em "Test users", adicione o seu
   e-mail da MadeiraMadeira.
2. Em **APIs e Serviços → Credenciais → Criar credenciais → ID do cliente
   OAuth**. Tipo de aplicativo: **App para computador (Desktop app)**. Baixe
   o JSON gerado (`client_secret_XXXX.json`).
3. **No SEU COMPUTADOR** (isso não funciona no Claude nem no GitHub Actions
   — precisa abrir seu navegador de verdade):
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_token.py caminho/para/client_secret_XXXX.json
   ```
   Vai abrir o navegador pedindo pra você logar (use a conta da MM que já
   tem acesso à planilha) e autorizar. No final, o script imprime 3 valores.
4. Guardar esses 3 valores como Secrets no GitHub (Settings → Secrets and
   variables → Actions): `GOOGLE_OAUTH_CLIENT_ID`,
   `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`.
5. Guardar também `SPREADSHEET_ID` como secret (valor:
   `1Fnv-dtRYB4lxOpiriOOEq9OhHvkfPYa0tgIARQcpSdY`).

Isso só precisa ser feito uma vez — o refresh token continua valendo depois.

### 3. E-mail (Gmail convencional)
Na conta Gmail que vai enviar o e-mail diário: ativar verificação em duas
etapas e gerar uma **Senha de app** em myaccount.google.com/apppasswords (a
senha normal da conta não funciona para SMTP). Secrets:
`SMTP_USER` (e-mail completo), `SMTP_PASSWORD` (senha de app, 16 caracteres),
`EMAIL_RECIPIENTS` (lista separada por vírgula — confirmar quem mais deve
receber, ex.: Damaris, que hoje faz a checagem manual).

### 4. Testar
Na aba **Actions** do repositório, rodar o workflow manualmente
("Run workflow") antes de esperar o cron das 9h — assim dá pra ver o
resultado sem esperar o dia seguinte.

## Rodando localmente para testar (opcional)

```bash
cd scripts
pip install -r ../requirements.txt
playwright install chromium
export SPREADSHEET_ID=...
export GOOGLE_OAUTH_CLIENT_ID=...
export GOOGLE_OAUTH_CLIENT_SECRET=...
export GOOGLE_OAUTH_REFRESH_TOKEN=...
python main.py --dry-run   # roda a checagem de verdade, mas não escreve na planilha nem manda e-mail
```

## Estrutura

- `scripts/config.py` — configuração central (canais, ranges das abas, CEP de teste).
- `scripts/sheets.py` — leitura de `Monitoramento_GMV` + `GMV_id_prdmkt` e escrita de `Alertas`, via Google Sheets API (OAuth do usuário).
- `scripts/get_token.py` — script de uso único para gerar o refresh token (roda no seu computador).
- `scripts/checkers.py` — verificação por canal: API pública do Mercado Livre + Playwright para o Shopee.
- `scripts/email_report.py` — monta e envia o e-mail HTML resumo.
- `scripts/main.py` — orquestra o fluxo completo.
- `.github/workflows/monitor-diario.yml` — cron diário do GitHub Actions.

## Critério de ATIVO/INATIVO

- Mercado Livre: status da API pública (`active` = ativo, qualquer outro valor ou 404 = inativo).
- Shopee: botão "Adicionar ao carrinho"/"Comprar agora" habilitado na página do produto. (A cotação de frete com CEP fictício não é usada aqui porque o Shopee calcula frete pelo endereço salvo na conta logada, não por um campo público na página — ajustar se isso for essencial.)

Se a checagem falhar tecnicamente (timeout, bloqueio, seletor não encontrado)
→ **NÃO VERIFICADO**, para não gerar falso alarme nem mascarar um bloqueio
real — vem separado no e-mail.

## Pendências conhecidas

- Amazon, Leroy Merlin, Casas Bahia, Magazine Luiza: sem De-Para ainda, fora do escopo por ora.
- Confirmar se o painel `Monitoramento_GMV` realmente lista só ~40 produtos por canal nesse recorte, ou se são mais (o teste inicial via leitura por IA cortou os dados; a leitura via Sheets API neste script não tem esse limite, mas vale confirmar visualmente).
