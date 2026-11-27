"""Professional ticket email rendering; never embeds the raw token as text."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QR_CONTENT_ID = "ticket-qr.png"
QR_FILENAME = "ticket-qr.png"


@dataclass(frozen=True)
class TicketEmailContext:
    """Safe display data assembled by the worker from committed rows."""

    attendee_name: str
    event_name: str
    event_description: str | None
    starts_at: datetime
    ends_at: datetime
    timezone_name: str
    venue: str | None
    ticket_code: str


def _localize(value: datetime, timezone_name: str) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    try:
        return aware.astimezone(ZoneInfo(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        return aware


def _format_date(value: datetime, timezone_name: str) -> str:
    local = _localize(value, timezone_name)
    return local.strftime("%A, %d %B %Y at %H:%M %Z").strip()


def render_ticket_email(context: TicketEmailContext) -> tuple[str, str]:
    """Return ``(html, plain_text)`` ticket email bodies."""
    attendee = html.escape(context.attendee_name)
    event_name = html.escape(context.event_name)
    venue = html.escape(context.venue) if context.venue else "Venue to be confirmed"
    description = (
        f'<p class="muted">{html.escape(context.event_description)}</p>'
        if context.event_description
        else ""
    )
    starts = html.escape(_format_date(context.starts_at, context.timezone_name))
    ends = html.escape(_format_date(context.ends_at, context.timezone_name))
    ticket_code = html.escape(context.ticket_code)

    html_body = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            "    <style>",
            "      body{margin:0;padding:32px 16px;background:#f3f4f6;color:#111827}",
            "      .shell{max-width:620px;margin:0 auto;background:#fff;border-radius:12px}",
            "      .header{padding:28px 32px;background:#111827;color:#fff}",
            "      .eyebrow{font-size:13px;letter-spacing:2px;text-transform:uppercase}",
            "      h1{margin:8px 0 0;font-size:26px}",
            "      .body{padding:32px}",
            "      .muted{color:#4b5563;line-height:1.6}",
            "      .meta{margin:0 0 24px;border:1px solid #e5e7eb;border-radius:8px}",
            "      .meta td{padding:14px 18px;border-bottom:1px solid #e5e7eb}",
            "      .qrbox{text-align:center;padding:20px;background:#f9fafb;border-radius:8px}",
            "      .qr{display:block;margin:0 auto;width:220px;height:220px}",
            "      .small{font-size:12px;color:#6b7280}",
            "      .footer{padding:18px 32px;text-align:center}",
            "    </style>",
            "  </head>",
            "  <body>",
            '    <table class="shell" role="presentation">',
            '      <tr><td class="header">',
            '        <div class="eyebrow">Your event ticket</div>',
            f"        <h1>{event_name}</h1>",
            "      </td></tr>",
            '      <tr><td class="body">',
            f"        <p>Hello {attendee},</p>",
            '        <p class="muted">Your registration is confirmed.</p>',
            '        <p class="muted">Present the QR code below at check-in.</p>',
            f"        {description}",
            '        <table class="meta" role="presentation">',
            f"          <tr><td><strong>Starts</strong><br>{starts}</td></tr>",
            f"          <tr><td><strong>Ends</strong><br>{ends}</td></tr>",
            f"          <tr><td><strong>Venue</strong><br>{venue}</td></tr>",
            "        </table>",
            '        <div class="qrbox">',
            f'          <img src="cid:{QR_CONTENT_ID}" alt="Ticket QR code"',
            '               width="220" height="220" class="qr">',
            f'          <div class="small">Ticket reference: {ticket_code}</div>',
            "        </div>",
            '        <p class="small">Keep this QR code private.</p>',
            '        <p class="small">Anyone holding it can use your ticket.</p>',
            "      </td></tr>",
            '      <tr><td class="footer small">',
            "        Sent automatically by the event management system.",
            "      </td></tr>",
            "    </table>",
            "  </body>",
            "</html>",
        ]
    )

    text_body = (
        f"Your registration is confirmed.\n\n"
        f"Event: {context.event_name}\n"
        f"Attendee: {context.attendee_name}\n"
        f"Starts: {_format_date(context.starts_at, context.timezone_name)}\n"
        f"Ends: {_format_date(context.ends_at, context.timezone_name)}\n"
        f"Venue: {context.venue or 'Venue to be confirmed'}\n"
        f"Ticket reference: {context.ticket_code}\n\n"
        f"Open the attached QR code and present it at check-in. Keep it private.\n"
    )
    return html_body, text_body
