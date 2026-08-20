"""
Rode este script UMA ÚNICA VEZ, no SEU COMPUTADOR (não funciona no Claude nem
no GitHub Actions — precisa abrir seu navegador de verdade).

Uso:
    pip install google-auth-oauthlib
    python get_token.py caminho/para/client_secret.json

O que acontece:
  1. Abre uma aba do seu navegador pedindo pra você logar com a conta que
     tem acesso à planilha (a sua da MadeiraMadeira) e autorizar o app.
  2. Depois de autorizar, o script imprime 3 valores: client_id,
     client_secret e refresh_token.
  3. Guarde esses 3 valores como Secrets no GitHub (Settings → Secrets and
     variables → Actions): GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
     GOOGLE_OAUTH_REFRESH_TOKEN.

Isso só precisa ser feito uma vez. O refresh_token não expira por uso (só se
você revogar o acesso do app na sua conta Google, ou passar muito tempo sem
usar).
"""
import sys
import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main():
    if len(sys.argv) != 2:
        print("Uso: python get_token.py caminho/para/client_secret.json")
        sys.exit(1)

    client_secret_path = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n\n=== Guarde estes 3 valores como Secrets no GitHub ===\n")
    print("GOOGLE_OAUTH_CLIENT_ID     =", creds.client_id)
    print("GOOGLE_OAUTH_CLIENT_SECRET =", creds.client_secret)
    print("GOOGLE_OAUTH_REFRESH_TOKEN =", creds.refresh_token)
    print("\n=====================================================\n")

    with open(client_secret_path) as f:
        info = json.load(f)
    print("(client_id/client_secret também estão em", client_secret_path, "caso precise depois)")


if __name__ == "__main__":
    main()
