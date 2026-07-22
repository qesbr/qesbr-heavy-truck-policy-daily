from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from policy_daily.models import Report


def render_email(report: Report, site_url: str) -> str:
    cards = "".join(
        f'<section><h2>{html.escape(a.title_zh)}</h2><p>{html.escape(a.summary_zh)}</p><p>{html.escape(a.source_name)} · {a.published_at:%Y-%m-%d %H:%M}</p><a href="{html.escape(str(a.source_url))}">查看原文</a></section>'
        for a in report.articles
    )
    return f'<!doctype html><html><meta name="viewport" content="width=device-width"><body style="max-width:680px;margin:auto;font-family:sans-serif"><h1>{html.escape(report.title)}</h1><p>{html.escape(report.summary)}</p>{cards}<p><a href="{html.escape(site_url)}">访问政策法规日报网站</a></p></body></html>'


def deliver(report: Report, recipients: list[str], username: str, auth_code: str, site_url: str, preview: Path | None, send: bool, smtp_host: str = "smtp.qq.com", smtp_port: int = 465) -> str:
    if report.report_type != "daily":
        return "拒绝发送：仅日报允许发送邮件"
    if report.empty:
        return "跳过发送：日报无有效内容"
    body = render_email(report, site_url)
    if preview:
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(body, encoding="utf-8")
    if not send:
        return "dry-run：已生成邮件预览"
    if not recipients or not username or not auth_code:
        return "发送失败：邮件配置不完整"
    message = EmailMessage()
    message["Subject"] = report.title
    message["From"] = username
    message["To"] = ", ".join(recipients)
    message.set_content(report.summary)
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ssl.create_default_context()) as server:
        server.login(username, auth_code)
        server.send_message(message)
    return "邮件发送成功"

