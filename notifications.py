"""Email notifications for ShopPilot.

Currently: a post-design summary emailed after the design agent runs, listing
the newly-generated product titles and their image URLs.

Sending is best-effort — any failure (missing config, SMTP error) is logged as
a warning and swallowed so it never breaks the agent pipeline.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import config

logger = logging.getLogger("shoppilot.notifications")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
RECIPIENT = "geasterbunny768@gmail.com"


def send_design_notification(result: dict[str, Any]) -> None:
    """Email a summary of newly-designed products from a design_agent.run result."""
    products = result.get("products") or []
    if not products:
        logger.info("notifications: no new products designed — skipping email")
        return

    if not config.NOTIFICATION_EMAIL or not config.SMTP_PASSWORD:
        logger.warning(
            "notifications: NOTIFICATION_EMAIL / SMTP_PASSWORD not set — "
            "skipping design notification email"
        )
        return

    lines = []
    for p in products:
        title = p.get("title") or "(untitled)"
        url = p.get("image_url") or f"(Printify image id: {p.get('image_id')})"
        lines.append(f"- {title}\n  {url}")
    body = (
        f"ShopPilot designed {len(products)} new product(s):\n\n"
        + "\n".join(lines)
    )

    msg = EmailMessage()
    msg["Subject"] = f"ShopPilot: {len(products)} new product design(s)"
    # SMTP_FROM lets the visible From differ from the authenticating Gmail
    # account; fall back to NOTIFICATION_EMAIL (the login) when it's unset.
    msg["From"] = config.SMTP_FROM or config.NOTIFICATION_EMAIL
    msg["To"] = RECIPIENT
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(config.NOTIFICATION_EMAIL, config.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("notifications: design summary emailed to %s", RECIPIENT)
    except Exception as e:
        logger.warning("notifications: failed to send design email: %s", e)
