"""WhatsApp Business Platform (Cloud API) integration — sends OTP codes via
an approved "Authentication" category template. Unlike notifications'
send_web_push (fire-and-forget, best-effort), this raises on failure so the
calling view can tell the user the send actually failed instead of silently
pretending an OTP went out."""
import requests
from django.conf import settings


class WhatsAppSendError(Exception):
    pass


def send_whatsapp_otp(phone, otp):
    """Send a WhatsApp Authentication-template message containing `otp` to
    `phone` (digits only, with country code, no leading +). Raises
    WhatsAppSendError on any failure — missing config, Meta API error,
    network error — with a message safe to show the user."""
    token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    template = settings.WHATSAPP_OTP_TEMPLATE

    if not token or not phone_number_id:
        raise WhatsAppSendError('WhatsApp OTP is not configured on this server yet.')

    url = f'https://graph.facebook.com/v21.0/{phone_number_id}/messages'
    payload = {
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'template',
        'template': {
            'name': template,
            'language': {'code': 'en'},
            'components': [
                {'type': 'body', 'parameters': [{'type': 'text', 'text': otp}]},
                # Standard Meta prebuilt Authentication templates also carry
                # a "copy code" button that needs the same code as its
                # parameter — harmless if your template has no buttons.
                {'type': 'button', 'sub_type': 'url', 'index': '0',
                 'parameters': [{'type': 'text', 'text': otp}]},
            ],
        },
    }
    try:
        resp = requests.post(
            url,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json=payload,
            timeout=10,
        )
    except requests.RequestException:
        raise WhatsAppSendError('Could not reach WhatsApp right now — try again in a moment.')

    if resp.status_code >= 400:
        raise WhatsAppSendError('Failed to send the WhatsApp code — check the number and try again.')
