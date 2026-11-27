"""In-memory QR generation for ticket credentials."""

from __future__ import annotations

import base64
import io

import qrcode


def generate_ticket_qr_png(raw_token: str) -> bytes:
    """Render a PNG QR code whose only payload is the raw ticket token."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(raw_token)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def qr_png_to_base64(qr_png: bytes) -> str:
    """Return the base64 payload accepted by Resend attachments."""
    return base64.b64encode(qr_png).decode("ascii")
