"""Per-request client, never a global API key; SDK verifies the unmodified body."""
import stripe
from fastapi import HTTPException

def client(settings):
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Billing is not configured.")
    return stripe.StripeClient(settings.stripe_secret_key, max_network_retries=2)

def verify(settings, payload, signature):
    if not settings.stripe_webhook_secret: raise HTTPException(503, "Webhook is not configured.")
    try: return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret, tolerance=300)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid webhook signature or payload.") from exc
