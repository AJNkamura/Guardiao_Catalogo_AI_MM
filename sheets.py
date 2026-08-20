"""
Leitura/escrita na planilha via Google Sheets API, autenticado como o próprio
usuário (OAuth), não como service account.

Setup necessário (uma vez só, ver scripts/get_token.py):
  1. No projeto do Google Cloud (o que a Amanda já criou na conta pessoal),
     configurar a tela de consentimento OAuth (External, modo Testing,
     adicionando o e-mail da MM como test user) e criar um "OAuth Client ID"
     do tipo Desktop app. Baixar o client_secret.json.
  2. Rodar `python get_token.py client_secret.json` NO SEU COMPUTADOR (não
     funciona dentro do Claude nem do GitHub Actions — precisa abrir o
     navegador de verdade pra você logar e autorizar).
  3. Isso imprime um refresh_token. Guardar client_id, client_secret e
     refresh_token como secrets no GitHub: GOOGLE_OAUTH_CLIENT_ID,
     GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN.

Por que isso e não service account: a política de compartilhamento externo do
Workspace da MadeiraMadeira bloqueia dar acesso a uma identidade "de fora"
(qualquer conta @*.iam.gserviceaccount.com). Autenticando como o próprio
usuário — que já tem acesso à planilha — não é um novo compartilhamento,
então essa trava não se aplica.
"""
from datetime import date

import gspread
from google.oauth2.credentials import Credentials

from config import (
    SPREADSHEET_ID,
    GID_MONITORAMENTO_GMV,
    ABA_DEPARA,
    ABA_ALERTAS,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REFRESH_TOKEN,
    CANAIS,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

ALERTAS_HEADER = [
    "ID Produto",
    "Canal",
    "Data verificação",
    "ID no Marketplace",
    "Link do produto",
    "Status",
    "Observação",
]


def _client():
    faltando = [
        nome
        for nome, val in [
            ("GOOGLE_OAUTH_CLIENT_ID", GOOGLE_OAUTH_CLIENT_ID),
            ("GOOGLE_OAUTH_CLIENT_SECRET", GOOGLE_OAUTH_CLIENT_SECRET),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", GOOGLE_OAUTH_REFRESH_TOKEN),
        ]
        if not val
    ]
    if faltando:
        raise RuntimeError(
            f"Faltam variáveis de ambiente: {', '.join(faltando)}. "
            "Veja o docstring deste arquivo / README para o passo a passo."
        )
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_OAUTH_REFRESH_TOKEN,
        client_id=GOOGLE_OAUTH_CLIENT_ID,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _worksheet_by_gid(sh, gid):
    for ws in sh.worksheets():
        if ws.id == gid:
            return ws
    raise RuntimeError(f"Nenhuma aba encontrada com gid={gid}")


def _col_letter_to_index(letter):
    """'A' -> 0, 'J' -> 9, etc."""
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def ler_produtos_zerados():
    """
    Lê, para cada canal em CANAIS, o bloco correspondente na aba de
    Monitoramento_GMV (resolvida por gid) e retorna os produtos cujo GMV na
    última coluna de data (a mais recente = ontem) é zero.
    """
    sh = _client().open_by_key(SPREADSHEET_ID)
    aba = _worksheet_by_gid(sh, GID_MONITORAMENTO_GMV)
    todas_linhas = aba.get_all_values()  # lista de listas, 1 por linha da planilha

    zerados = []
    for canal_key, cfg in CANAIS.items():
        col0 = _col_letter_to_index(cfg["gmv_col_inicio"])
        # localizar a linha de cabeçalho ("ID Produto") dentro dessa faixa de colunas
        header_row_idx = None
        for i, linha in enumerate(todas_linhas):
            if len(linha) > col0 and linha[col0].strip() == "ID Produto":
                header_row_idx = i
                break
        if header_row_idx is None:
            raise RuntimeError(
                f"Não achei o cabeçalho 'ID Produto' na coluna {cfg['gmv_col_inicio']} "
                f"para o canal {cfg['label']} — a planilha pode ter mudado de layout."
            )
        header = todas_linhas[header_row_idx][col0 : col0 + 8]
        datas = header[2:7]
        ultima_data = datas[-1] if datas else ""

        for linha in todas_linhas[header_row_idx + 1 :]:
            if len(linha) <= col0 or not linha[col0].strip().isdigit():
                break  # fim do bloco contínuo desse canal
            seg = linha[col0 : col0 + 8]
            gmv_ultima_data = seg[6] if len(seg) > 6 else ""
            gmv_valor = _parse_moeda(gmv_ultima_data)
            if gmv_valor == 0:
                zerados.append(
                    {
                        "id_produto": seg[0].strip(),
                        "nome_produto": seg[1].strip() if len(seg) > 1 else "",
                        "canal": canal_key,
                        "data": ultima_data,
                    }
                )
    return zerados


def _parse_moeda(txt):
    txt = (txt or "").replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(txt or 0)
    except ValueError:
        return None  # célula vazia/estranha — não assumir nem zero nem não-zero


def ler_depara():
    """
    Lê a aba GMV_id_prdmkt e devolve, para cada canal, um dict
    id_produto -> {id_marketplace_produto, link}
    """
    sh = _client().open_by_key(SPREADSHEET_ID)
    aba = sh.worksheet(ABA_DEPARA)
    todas_linhas = aba.get_all_values()

    resultado = {canal_key: {} for canal_key in CANAIS}
    for canal_key, cfg in CANAIS.items():
        col0 = _col_letter_to_index(cfg["depara_col_inicio"])
        off_id = cfg["depara_offset_id_produto"]
        off_mkt = cfg["depara_offset_id_marketplace_produto"]
        off_link = cfg["depara_offset_link"]
        for linha in todas_linhas:
            if len(linha) <= col0 + off_id:
                continue
            id_produto = linha[col0 + off_id].strip()
            if not id_produto.isdigit():
                continue
            id_mkt = linha[col0 + off_mkt].strip() if len(linha) > col0 + off_mkt else ""
            link = linha[col0 + off_link].strip() if len(linha) > col0 + off_link else ""
            resultado[canal_key][id_produto] = {
                "id_marketplace_produto": id_mkt,
                "link": link,
            }
    return resultado


def escrever_alertas(resultados):
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
                CANAIS.get(r["canal"], {}).get("label", r["canal"]),
                hoje,
                r.get("id_marketplace_produto", ""),
                r.get("link", ""),
                r["status"],
                r.get("observacao", ""),
            ]
        )
    aba.clear()
    aba.update(values=linhas, range_name="A1")
    return len(resultados)
