"""Monta e envia o e-mail resumo diário."""
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_RECIPIENTS
from checkers import STATUS_ATIVO, STATUS_INATIVO, STATUS_NAO_VERIFICADO


def montar_html(resultados):
    hoje = date.today().strftime("%d/%m/%Y")
    inativos = [r for r in resultados if r["status"] == STATUS_INATIVO]
    nao_verificados = [r for r in resultados if r["status"] == STATUS_NAO_VERIFICADO]
    ativos = [r for r in resultados if r["status"] == STATUS_ATIVO]

    def linha(r):
        link = f'<a href="{r.get("link","")}">link</a>' if r.get("link") else ""
        return (
            f"<tr><td>{r['id_produto']}</td><td>{r['canal']}</td>"
            f"<td>{r.get('dias_sem_venda','')}</td><td>{link}</td>"
            f"<td>{r.get('observacao','')}</td></tr>"
        )

    def tabela(lista, cor):
        if not lista:
            return "<p><i>Nenhum item.</i></p>"
        linhas = "".join(linha(r) for r in lista)
        return (
            f'<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">'
            f'<tr style="background:{cor};color:#fff"><th>ID Produto</th><th>Canal</th>'
            f"<th>Dias sem venda</th><th>Link</th><th>Observação</th></tr>{linhas}</table>"
        )

    html = f"""
    <html><body style="font-family:Arial,sans-serif;font-size:14px">
    <h2>Monitoramento Top 100 Produtos — {hoje}</h2>
    <p>Verificação automática dos produtos sem venda no dia anterior, em todos os canais.</p>

    <h3 style="color:#c0392b">🔴 Inativos confirmados ({len(inativos)})</h3>
    <p>Produtos sem venda cujo status no canal foi confirmado como INATIVO — ação recomendada.</p>
    {tabela(inativos, '#c0392b')}

    <h3 style="color:#e67e22">⚠️ Não verificados ({len(nao_verificados)})</h3>
    <p>Não foi possível confirmar o status automaticamente (possível bloqueio anti-bot ou instabilidade do site) — vale checar manualmente.</p>
    {tabela(nao_verificados, '#e67e22')}

    <h3 style="color:#27ae60">🟢 Ativos, sem venda por outro motivo ({len(ativos)})</h3>
    <p>Página está ativa e comprável — o GMV zerado provavelmente reflete falta de demanda, não indisponibilidade.</p>
    {tabela(ativos, '#27ae60')}

    <p style="color:#888;font-size:12px">Gerado automaticamente. A aba "Alertas" da planilha foi atualizada com o mesmo resultado.</p>
    </body></html>
    """
    return html


def enviar(resultados, destinatarios=None):
    destinatarios = destinatarios or EMAIL_RECIPIENTS
    if not destinatarios:
        raise RuntimeError("EMAIL_RECIPIENTS não configurado — nenhum destinatário definido.")

    hoje = date.today().strftime("%d/%m/%Y")
    inativos = sum(1 for r in resultados if r["status"] == STATUS_INATIVO)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Monitor Produtos] {hoje} — {inativos} inativo(s) encontrado(s)"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(destinatarios)
    msg.attach(MIMEText(montar_html(resultados), "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())
