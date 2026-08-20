# Monitor de Produtos — Top 100 por Canal

Automação do fluxo manual: detectar produtos do top 100 com GMV zerado no dia
anterior e verificar se estão INATIVOS no canal (Mercado Livre, Amazon, Leroy
Merlin, Shopee, Casas Bahia, Magazine Luiza), atualizando a aba **Alertas** da
planilha e disparando um e-mail resumo diário.

## ⚠️ Onde isso PRECISA rodar

Este script faz chamadas de rede reais para os marketplaces (Playwright) e
para a API do Google Sheets. Testei rodá-lo dentro do ambiente do Claude
(nuvem da Anthropic) e **a rede de saída daqui é bloqueada por uma allowlist**
— nem `mercadolivre.com.br`, nem `googleapis.com`, nem sequer `google.com`
respondem (só domínios como PyPI/npm). Ou seja: **o Claude não consegue
executar a raspagem/checagem em si** a partir de uma tarefa agendada própria
— só o GitHub Actions (ou outro servidor/VM com internet normal) consegue.

Por isso a recomendação é:

- **GitHub Actions roda o pipeline inteiro** (checagem + planilha + e-mail) —
  é o mesmo caminho que já estava no plano de vocês como alternativa ao Apps
  Script, e é o único viável tecnicamente para a parte de scraping.
- O papel do Claude nessa automação fica sendo: manter/evoluir o script, e
  opcionalmente rodar uma tarefa agendada "de vigia" que confere se o e-mail
  do dia chegou na caixa de entrada (via Gmail) e avisa se não chegou — não
  substitui o GitHub Actions.

## Setup necessário

1. **Repositório GitHub** com Actions habilitado — ainda não criado. Quando
   tiverem um repositório: copiar esta pasta inteira para dentro dele
   (mantendo a estrutura `.github/workflows/`, `scripts/`, `requirements.txt`),
   configurar os secrets abaixo em Settings → Secrets and variables → Actions,
   e o cron diário já roda sozinho.
2. **Google Cloud Service Account** com a Sheets API ativada:
   - Criar a service account, gerar chave JSON.
   - Compartilhar a planilha com o e-mail da service account (permissão
     Editor).
   - Guardar o JSON inteiro como secret `GOOGLE_SERVICE_ACCOUNT_JSON` no
     repositório (Settings → Secrets → Actions).
3. **Envio de e-mail**: via uma conta Gmail convencional (`config.py` já usa
   `smtp.gmail.com:587` como default, não precisa mudar host/porta). Passos:
   - Na conta Gmail que vai enviar (pode ser a própria da Amanda ou uma conta
     dedicada ao robô), ativar a verificação em duas etapas e gerar uma
     **"Senha de app"** em myaccount.google.com/apppasswords (a senha normal
     da conta não funciona para SMTP).
   - Guardar como secrets no GitHub: `SMTP_USER` (o e-mail Gmail completo) e
     `SMTP_PASSWORD` (a senha de app gerada, 16 caracteres).
   - `EMAIL_RECIPIENTS`: lista de destinatários do e-mail diário, separados
     por vírgula (confirmar com a Amanda quem mais deve receber, ex.:
     Damaris, que hoje faz a checagem manual).
4. **IDs/URLs pendentes**: preciso de 1 link de produto real de **Leroy
   Merlin** e **Magazine Luiza** para confirmar o padrão de URL e ajustar os
   seletores em `scripts/checkers.py` (por enquanto estão com o melhor
   palpite, não testados).
5. (Opcional, recomendado) Se a MadeiraMadeira tiver acesso à **Amazon
   Selling Partner API (SP-API)** como seller, trocar o canal `amazon` de
   `method: "browser"` para uma chamada de API — muito mais confiável que
   scraping.

## Rodando localmente para testar

```bash
cd scripts
pip install -r ../requirements.txt
playwright install chromium
python main.py --dry-run   # não escreve na planilha nem manda e-mail
```

## Estrutura

- `scripts/config.py` — configuração central (canais, planilha, CEP de teste).
- `scripts/sheets.py` — leitura da aba `Monitoramento_GMV` e escrita da aba `Alertas`.
- `scripts/checkers.py` — lógica de verificação por canal (API do Mercado Livre + Playwright para os demais).
- `scripts/email_report.py` — monta e envia o e-mail HTML resumo.
- `scripts/main.py` — orquestra o fluxo completo.
- `.github/workflows/monitor-diario.yml` — cron diário do GitHub Actions.

## Critério de ATIVO/INATIVO

- Botão "Comprar"/"Adicionar ao carrinho" habilitado, **e**
- Cotação de frete retornando valor ao informar um CEP de teste (`CEP_TESTE` em `config.py`)

Se qualquer condição falhar → **INATIVO**. Se a checagem falhar tecnicamente
(timeout, bloqueio, seletor não encontrado) → **NÃO VERIFICADO** (para não
gerar falso alarme nem mascarar um bloqueio real — vem separado no e-mail).
