#!/usr/bin/env python3
"""
Push notification module for the news monitor.
Supports Telegram Bot and Email, including Chinese content and weekly briefings.
"""
import html
import logging
import smtplib
from email.mime.text import MIMEText

import config

log = logging.getLogger(f"{config.LOGGER_NAME}.notifier")


def _esc_md(text: str) -> str:
    """Escape Telegram Markdown special characters in user-supplied text."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def fmt_msg(article: dict) -> str:
    """Format article for notification — prefer Chinese translation if available."""
    title = _esc_md(article.get("translated_title") or article["title"])
    summary = _esc_md(article.get("translated_summary") or article.get("summary", ""))
    pub = _esc_md(article.get("published", "") or "recent")
    kw = _esc_md(article.get("matched_kw", ""))
    source = _esc_md(article.get("source", ""))
    url = article.get("url", "")
    relevance = article.get("relevance", 0)

    # Check if the title is Chinese
    import re
    has_cjk = bool(re.search(r"[一-鿿]", article.get("translated_title") or article["title"]))

    prefix = config.TELEGRAM_MSG_CJK if has_cjk else config.TELEGRAM_MSG_EN
    alert_line = f"*{prefix}*\n\n"
    if has_cjk:
        summary_text = f"{summary}..." if len(summary) >= 300 else summary
        return alert_line + (
            f"*{title}*\n"
            f"来源: {source}\n"
            f"日期: {pub}\n"
            f"相关度: {relevance}/100\n"
            f"关键词: {kw}\n\n"
            f"{summary_text}\n\n"
            f"{url}"
        )
    else:
        summary_text = f"{summary}..." if len(summary) >= 300 else summary
        return alert_line + (
            f"*{title}*\n"
            f"Source: {source}\n"
            f"Date: {pub}\n"
            f"Relevance: {relevance}/100\n"
            f"Keywords: {kw}\n\n"
            f"{summary_text}\n\n"
            f"{url}"
        )


def fmt_html(article: dict) -> str:
    """Format article as HTML email — with Chinese if available."""
    title = html.escape(article.get("translated_title") or article["title"])
    summary = html.escape(article.get("translated_summary") or article.get("summary", ""))
    orig_title = html.escape(article.get("title", ""))
    source = html.escape(article.get("source", ""))
    published = html.escape(article.get("published", ""))
    kw = html.escape(article.get("matched_kw", ""))
    url = html.escape(article.get("url", ""), quote=True)
    relevance = article.get("relevance", 0)
    has_translation = bool(article.get("translated_title"))

    orig_line = ""
    if has_translation:
        orig_line = f"<p><small>原文: {orig_title}</small></p>"

    return f"""<h2>{html.escape(config.EMAIL_HTML_PREFIX)}</h2>
<h3>{title}</h3>
{orig_line}
<table>
<tr><td><b>Source</b></td><td>{source}</td></tr>
<tr><td><b>Date</b></td><td>{published}</td></tr>
<tr><td><b>Relevance</b></td><td>{relevance}/100</td></tr>
<tr><td><b>Keywords</b></td><td>{kw}</td></tr>
</table>
<p>{summary}</p>
<p><a href="{url}">Read original article →</a></p>"""


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
        log.info(f"Article saved (no notification channel configured): {article.get('title', '')[:60]}...")


def send_batch_digest(articles: list[dict]) -> bool:
    """Send a single digest email with all new articles listed."""
    if not config.SMTP_SERVER or not config.EMAIL_TO:
        return False
    try:
        items_html = ""
        for i, a in enumerate(articles, 1):
            title = a.get("translated_title") or a["title"]
            summary = a.get("translated_summary") or a.get("summary", "")
            url = a.get("url", "")
            source = a.get("source", "")
            kw = a.get("matched_kw", "")
            items_html += f"""
            <tr><td style="padding:0.8rem 0;border-bottom:1px solid #e2e8f0;">
              <p style="margin:0 0 0.3rem;"><strong>{i}.</strong>&nbsp;
                <a href="{html.escape(url)}" style="color:#2563eb;text-decoration:none;">{html.escape(title)}</a>
              </p>
              <p style="margin:0;color:#64748b;font-size:0.85rem;">{html.escape(source)}</p>
              <p style="margin:0;color:#64748b;font-size:0.85rem;">{html.escape(summary[:200])}</p>
              <p style="margin:0;color:#94a3b8;font-size:0.8rem;">{' '.join(kw.split(', ')[:5])}</p>
            </td></tr>"""

        body = f"""<div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
<h2>{config.EMAIL_HTML_PREFIX}</h2>
<p style="color:#475569;">发现 <strong>{len(articles)}</strong> 篇新文章</p>
<table style="width:100%;border-collapse:collapse;">{items_html}</table>
</div>"""
        msg = MIMEText(body, "html", "utf-8")
        msg["Subject"] = f"{config.EMAIL_SUBJECT_PREFIX} {len(articles)} 篇新文章"
        msg["From"] = config.EMAIL_FROM or config.SMTP_USER
        msg["To"] = config.EMAIL_TO

        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASS)
            server.send_message(msg)
        log.info(f"Digest email sent to {config.EMAIL_TO} ({len(articles)} articles)")
        return True
    except Exception as e:
        log.warning(f"Digest email send error: {e}")
        return False


# ── Apprise multi-channel notification ─────────────────────────────────────

def _notify_apprise(articles: list[dict]):
    """Send notification via Apprise to all configured channels."""
    if not config.APPRISE_URLS:
        return
    try:
        import apprise
        apobj = apprise.Apprise()
        for url in config.APPRISE_URLS.split(","):
            url = url.strip()
            if url:
                apobj.add(url)

        if not len(apobj):
            return

        lines = [f"{config.NOTIFICATION_PREFIX} 新发现 {len(articles)} 篇文章\n"]
        for i, a in enumerate(articles[:15], 1):
            title = a.get("translated_title") or a["title"]
            source = a.get("source", "")
            kw = a.get("matched_kw", "")
            lines.append(f"{i}. [{title}]({a['url']}) — {source}")
            if kw:
                lines.append(f"   `{kw[:50]}`")
        if len(articles) > 15:
            lines.append(f"\n...还有 {len(articles) - 15} 篇")

        body = "\n".join(lines)
        title = f"{config.NOTIFICATION_PREFIX} {config.APP_NAME}"

        apobj.notify(body=body, title=title, body_format=apprise.BodyFormat.Markdown)
        log.info(f"Apprise notification sent ({len(articles)} articles)")
    except Exception as e:
        log.warning(f"Apprise notification error: {e}")


def _notify_apprise_briefing(briefing_text: str, days: int = 7):
    """Send briefing via Apprise."""
    if not config.APPRISE_URLS:
        return
    try:
        import apprise
        from datetime import datetime, timedelta, timezone

        apobj = apprise.Apprise()
        for url in config.APPRISE_URLS.split(","):
            url = url.strip()
            if url:
                apobj.add(url)

        if not len(apobj):
            return

        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        date_range = f"{start} ~ {end}"

        body = briefing_text[:2000] if len(briefing_text) > 2000 else briefing_text
        title = config.NOTIFICATION_PREFIX + " 周报 - " + date_range

        apobj.notify(body=body, title=title, body_format=apprise.BodyFormat.Markdown)
        log.info("Apprise briefing notification sent")
    except Exception as e:
        log.warning(f"Apprise briefing notification error: {e}")


def notify_apprise_message(title: str, body: str):
    """Send a custom message via Apprise to all configured channels."""
    if not config.APPRISE_URLS:
        return
    try:
        import apprise
        apobj = apprise.Apprise()
        for url in config.APPRISE_URLS.split(","):
            url = url.strip()
            if url:
                apobj.add(url)
        if len(apobj):
            apobj.notify(body=body, title=title, body_format=apprise.BodyFormat.Markdown)
            log.info(f"Apprise message sent: {title}")
    except Exception as e:
        log.warning(f"Apprise message error: {e}")


def notify_batch(articles: list[dict]):
    """Send batch notification — one digest email + one Telegram message + Apprise per batch."""
    if not articles:
        return
    log.info(f"Notifying {len(articles)} new articles")

    # Single digest email instead of N individual emails
    send_batch_digest(articles)

    # Batch Telegram into a single summary message
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        if len(articles) == 1:
            send_telegram(articles[0])
        else:
            _send_batch_telegram(articles)

    # Apprise multi-channel notification
    _notify_apprise(articles)


def _send_batch_telegram(articles: list[dict]):
    """Send a single Telegram message with multiple articles."""
    lines = [f"🔔 *新发现 {len(articles)} 篇文章*\n"]
    for i, a in enumerate(articles[:15], 1):
        title = _esc_md(a.get("translated_title") or a["title"])
        source = _esc_md(a.get("source", ""))
        kw = _esc_md(a.get("matched_kw", ""))
        title_trunc = title[:60]
        lines.append(f"{i}. [{title_trunc}]({a['url']}) — {source}")
        if kw:
            lines.append(f"   `{kw[:50]}`")
    if len(articles) > 15:
        lines.append(f"\n...还有 {len(articles)-15} 篇")
    try:
        import requests as req
        resp = req.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": "\n".join(lines),
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            log.info(f"Batch Telegram notification sent ({len(articles)} articles)")
        else:
            log.warning(f"Batch Telegram API error: {resp.status_code}")
    except Exception as e:
        log.warning(f"Batch Telegram send error: {e}")


def notify_briefing(briefing_text: str, days: int = 7):
    """Send weekly briefing via email and Apprise."""
    sent = False

    # Email
    if config.SMTP_SERVER and config.EMAIL_TO:
        try:
            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)
            start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            end = now.strftime("%Y-%m-%d")
            date_range = f"{start} ~ {end}"

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
            sent = True
        except Exception as e:
            log.warning(f"Briefing email error: {e}")

    # Apprise
    _notify_apprise_briefing(briefing_text, days)

    if not sent:
        log.info("No notification channel configured, skipping briefing notification")
    return sent
