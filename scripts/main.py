"""
Orquestrador do monitoramento diário.

Uso:
  python main.py            # roda o fluxo completo (planilha -> checagem -> planilha + e-mail)
  python main.py --dry-run  # usa dados de exemplo, não escreve na planilha nem envia e-mail
"""
import sys
import re

import sheets
import email_report
from checkers import checar_produto
from config import CANAIS

EXEMPLO_DRY_RUN = [
    {"id_produto": "MLB3822025057", "canal": "mercado_livre", "link": "", "dias_sem_venda": 2},
    {"id_produto": "B0DJCK5GPP", "canal": "amazon", "link": "", "dias_sem_venda": 1},
]


def normalizar_canal(nome_canal):
    """Mapeia o texto livre da planilha (ex.: 'Mercado Livre') para a chave em config.CANAIS."""
    chave = re.sub(r"[^a-z0-9]+", "_", nome_canal.strip().lower()).strip("_")
    aliases = {
        "mercadolivre": "mercado_livre",
        "ml": "mercado_livre",
        "magalu": "magazine_luiza",
        "magazineluiza": "magazine_luiza",
        "casasbahia": "casas_bahia",
        "leroymerlin": "leroy_merlin",
    }
    return aliases.get(chave, chave)


def rodar(produtos_zerados):
    resultados = []
    for p in produtos_zerados:
        canal_key = normalizar_canal(p["canal"])
        if canal_key not in CANAIS:
            resultados.append(
                {**p, "status": "NÃO VERIFICADO", "observacao": f"Canal '{p['canal']}' sem checador configurado"}
            )
            continue
        r = checar_produto(canal_key, p["id_produto"], p.get("link", ""))
        resultados.append({**p, **r})
    return resultados


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("Rodando em modo --dry-run (dados de exemplo, sem escrever na planilha/enviar e-mail)")
        produtos = EXEMPLO_DRY_RUN
    else:
        produtos = sheets.ler_produtos_zerados()
        print(f"{len(produtos)} produto(s) com GMV zerado encontrados na aba Monitoramento_GMV")

    resultados = rodar(produtos)

    for r in resultados:
        print(f"- {r['id_produto']} [{r['canal']}] -> {r['status']} ({r.get('observacao','')})")

    if dry_run:
        print("\n--- Prévia do e-mail (HTML) ---")
        print(email_report.montar_html(resultados))
        return

    n = sheets.escrever_alertas(resultados)
    print(f"Aba 'Alertas' atualizada com {n} linha(s).")

    email_report.enviar(resultados)
    print("E-mail resumo enviado.")


if __name__ == "__main__":
    main()
