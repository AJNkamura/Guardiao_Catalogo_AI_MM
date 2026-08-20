"""
Orquestrador do monitoramento diário.

Uso:
  python main.py            # roda o fluxo completo
  python main.py --dry-run  # lê a planilha de verdade e roda a checagem, mas
                             # NÃO escreve na aba Alertas nem envia e-mail
                             # (só imprime o que faria)
"""
import sys

import sheets
import email_report
from checkers import checar_produto


def rodar():
    zerados = sheets.ler_produtos_zerados()
    print(f"{len(zerados)} produto(s) com GMV zerado na última data (Mercado Livre + Shopee)")

    depara = sheets.ler_depara()

    resultados = []
    for p in zerados:
        canal = p["canal"]
        mapa = depara.get(canal, {}).get(p["id_produto"])
        if not mapa:
            resultados.append(
                {**p, "status": "NÃO VERIFICADO", "observacao": "ID não encontrado na aba De-Para (GMV_id_prdmkt)"}
            )
            continue

        r = checar_produto(canal, mapa["id_marketplace_produto"], mapa["link"])
        resultados.append({**p, **mapa, **r})

    return resultados


def main():
    dry_run = "--dry-run" in sys.argv
    resultados = rodar()

    for r in resultados:
        print(f"- {r['id_produto']} [{r['canal']}] -> {r['status']} ({r.get('observacao','')})")

    if dry_run:
        print("\n--dry-run: não escrevi na planilha nem enviei e-mail.")
        print("\n--- Prévia do e-mail (HTML) ---")
        print(email_report.montar_html(resultados))
        return

    n = sheets.escrever_alertas(resultados)
    print(f"Aba 'Alertas' atualizada com {n} linha(s).")

    email_report.enviar(resultados)
    print("E-mail resumo enviado.")


if __name__ == "__main__":
    main()
