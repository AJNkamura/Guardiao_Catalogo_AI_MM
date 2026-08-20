"""
Leitura/escrita na planilha Google Sheets via service account.

Setup necessário (uma vez só):
  1. No Google Cloud Console, criar um projeto (ou usar um existente da MM) e
     ativar a "Google Sheets API".
  2. Criar uma Service Account e gerar uma chave JSON.
  3. Compartilhar a planilha "Monitoramento_GMV" com o e-mail da service
     account (algo como monitor-produtos@<projeto>.iam.gserviceaccount.com),
     dando permissão de Editor.
  4. Guardar o conteúdo do JSON como secret GOOGLE_SERVICE_ACCOUNT_JSON no
     GitHub Actions (ou em .env local para testes).
"""
import json
from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from config import SPREADSHEET_ID, ABA_GMV, ABA_ALERTAS, GOOGLE_SERVICE_ACCOUNT_JSON

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

ALERTAS_HEADER = [
    "ID Produto",
    "Canal",
    "Data verificação",
    "Dias sem venda",
    "Status",
    "Link do produto",
    "Observação",
]


def _client():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON não configurado. Veja o docstring deste "
            "arquivo para o passo a passo de setup."
        )
    # aceita tanto o caminho de um arquivo quanto o JSON direto na env var
    if GOOGLE_SERVICE_ACCOUNT_JSON.strip().startswith("{"):
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    else:
        with open(GOOGLE_SERVICE_ACCOUNT_JSON) as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def ler_produtos_zerados():
    """
    Lê a aba Monitoramento_GMV e retorna a lista de produtos cujo GMV do dia
    anterior está zerado em algum canal.

    Espera colunas (ajustar nomes conforme o cabeçalho real da planilha):
      ID Produto | Canal | Link do produto | GMV D-1 | Dias sem venda
    """
    sh = _client().open_by_key(SPREADSHEET_ID)
    aba = sh.worksheet(ABA_GMV)
    registros = aba.get_all_records()  # lista de dicts, usando a 1a linha como header

    zerados = []
    for r in registros:
        gmv = r.get("GMV D-1", r.get("GMV", 0))
        try:
            gmv = float(str(gmv).replace(",", ".").replace("R$", "").strip() or 0)
        except ValueError:
            gmv = 0
        if gmv == 0:
            zerados.append(
                {
                    "id_produto": str(r.get("ID Produto", "")).strip(),
                    "canal": str(r.get("Canal", "")).strip(),
                    "link": str(r.get("Link do produto", "")).strip(),
                    "dias_sem_venda": r.get("Dias sem venda", ""),
                }
            )
    return zerados


def escrever_alertas(resultados):
    """
    resultados: lista de dicts com chaves
      id_produto, canal, dias_sem_venda, status, link, observacao
    Sobrescreve a aba Alertas do zero a cada execução (histórico fica no
    Looker via snapshot diário, se necessário manter histórico completo,
    trocar para "append" em vez de limpar).
    """
    sh = _client().open_by_key(SPREADSHEET_ID)
    try:
        aba = sh.worksheet(ABA_ALERTAS)
    except gspread.WorksheetNotFound:
        aba = sh.add_worksheet(title=ABA_ALERTAS, rows=1000, cols=len(ALERTAS_HEADER))

    hoje = date.today().isoformat()
    linhas = [ALERTAS_HEADER]
    for r in resultados:
        linhas.append(
            [
                r["id_produto"],
                r["canal"],
                hoje,
                r.get("dias_sem_venda", ""),
                r["status"],
                r.get("link", ""),
                r.get("observacao", ""),
            ]
        )

    aba.clear()
    aba.update(values=linhas, range_name="A1")
    return len(resultados)
