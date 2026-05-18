#!/usr/bin/env python3
"""
Push notification module for the news monitor.
Supports Telegram Bot and Email, including Chinese content and weekly briefings.
"""
import logging
import smtplib
from email.mime.text import MIMEText

import config

log = logging.getLogger(f"{config.LOGGER_NAME}.notifier")


def fmt_msg(article: dict) -> str:
    """Format article for notification — prefer Chinese translation if available."""
    title = article.get("translated_title") or article["title"]
    summary = article.get("translated_summary") or article.get("summary", "")
    pub = article.get("published", "") or "recent"
    kw = article.get("matched_kw", "")

    # Check if the title is Chinese
    import re
    has_cjk = bool(re.search(r"[一-鿿]", title))

    prefix = config.TELEGRAM_MSG_CJK if has_cjk else config.TELEGRAM_MSG_EN
    alert_line = f"*{prefix}*\n\n"
    if has_cjk:
        return alert_line + (
            f"*{title}*\n"
            f"来源: {article['source']}\n"
            f"日期: {pub}\n"
            f"相关度: {article.get('relevance', 0)}/100\n"
            f"关键词: {kw}\n\n"
            f"{summary[:300]}...\n\n"
            f"{article['url']}"
        )
    else:
        return alert_line + (
            f"*{title}*\n"
            f"Source: {article['source']}\n"
            f"Date: {pub}\n"
            f"Relevance: {article.get('relevance', 0)}/100\n"
            f"Keywords: {kw}\n\n"
            f"{summary[:300]}...\n\n"
            f"{article['url']}"
        )


def fmt_html(article: dict) -> str:
    """Format article as HTML email — with Chinese if available."""
    title = article.get("translated_title") or article["title"]
    summary = article.get("translated_summary") or article.get("summary", "")
    orig_title = article["title"]
    has_translation = bool(article.get("translated_title"))

    orig_line = ""
    if has_translation:
        orig_line = f"<p><small>原文: {orig_title}</small></p>"

    return f"""<h2>{config.EMAIL_HTML_PREFIX}</h2>
<h3>{title}</h3>
{orig_line}
<table>
<tr><td><b>Source</b></td><td>{article['source']}</td></tr>
<tr><td><b>Date</b></td><td>{article.get('published', '')}</td></tr>
<tr><td><b>Relevance</b></td><td>{article.get('relevance', 0)}/100</td></tr>
<tr><td><b>Keywords</b></td><td>{article.get('matched_kw', '')}</td></tr>
</table>
<p>{summary}</p>
<p><a href="{article['url']}">Read original article →</a></p>"""


def send_telegram(article: dict) -> bool:
    """Send notification via Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    try:
        import requests as req
        msg = fmt_msg(article)
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = req.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=10)
        if resp.status_code == 200:
            log.info(f"Telegram notification sent")
            return True
        else:
            log.warning(f"Telegram API error: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"Telegram send error: {e}")
        return False


def send_email(article: dict) -> bool:
    """Send notification via Email."""
    if not config.SMTP_SERVER or not config.EMAIL_TO:
        return False
    try:
        title = article.get("translated_title") or article["title"]
        msg = MIMEText(fmt_html(article), "html", "utf-8")
        msg["Subject"] = f"{config.EMAIL_SUBJECT_PREFIX} {title[:80]}"
        msg["From"] = config.EMAIL_FROM or config.SMTP_USER
        msg["To"] = config.EMAIL_TO

        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASS)
            server.send_message(msg)
        log.info(f"Email notification sent to {config.EMAIL_TO}")
        return True
    except Exception as e:
        log.warning(f"Email send error: {e}")
        return False


def notify_all(article: dict):
    """Send notification through all configured channels."""
    sent = False
    if send_telegram(article):
        sent = True
    if send_email(article):
        sent = True
    if not sent:
        log.info(f"Article saved (no notification channel configured): {article['title'][:60]}...")


def notify_briefing(briefing_text: str):
    """Send weekly briefing via email."""
    if not config.SMTP_SERVER or not config.EMAIL_TO:
        log.info("No email configured, skipping briefing notification")
        return False
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        date_range = f"过去7天 - {now}"

        html_body = briefing_text.replace("\n", "<br>\n")
        msg = MIMEText(
            f"<div style='font-family:sans-serif;line-height:1.8;'>{html_body}</div>",
            "html", "utf-8",
        )
        subject = config.BRIEFING_SUBJECT.format(date_range=date_range)
        msg["Subject"] = f"📊 {subject}"
        msg["From"] = config.EMAIL_FROM or config.SMTP_USER
        msg["To"] = config.EMAIL_TO

        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASS)
            server.send_message(msg)
        log.info(f"Briefing email sent to {config.EMAIL_TO}")
        return True
    except Exception as e:
        log.warning(f"Briefing email error: {e}")
        return False
