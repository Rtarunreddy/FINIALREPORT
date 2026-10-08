from dataclasses import asdict
from datetime import datetime, timezone
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .. import stripe_client
from ..db_models import BillingEvent, Subscription, User
from ..deps import current_user, get_db
from ..plans import PLANS, effective_plan, lock_user, quota_view

router = APIRouter(prefix="/api/billing")

class CheckoutRequest(BaseModel):
    plan: str

@router.get("/plans")
def plans(request: Request):
    s = request.app.state.settings
    return {"plans": [asdict(p) for p in PLANS.values()], "billingEnabled": s.billing_enabled and not s.local_mode and bool(s.stripe_secret_key and s.stripe_webhook_secret and s.stripe_pro_price and s.stripe_team_price)}

@router.get("/status")
def status(request: Request, team_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return quota_view(db, user, team_id) | {"portalAvailable": bool(user.stripe_customer_id and request.app.state.settings.stripe_secret_key), "localMode": request.app.state.settings.local_mode}

@router.post("/checkout")
def checkout(body: CheckoutRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = request.app.state.settings
    if s.local_mode or not s.billing_enabled: raise HTTPException(503, "Billing is not open yet. The pilot is running without payments.")
    price = {"pro": s.stripe_pro_price, "team": s.stripe_team_price}.get(body.plan)
    if not price or not s.stripe_webhook_secret: raise HTTPException(400, "This plan is not available for purchase.")
    lock_user(db, user.id); db.refresh(user)
    if db.scalar(select(Subscription.id).where(Subscription.owner_id == user.id, Subscription.owner_type == "user", Subscription.status.in_(("active", "trialing", "past_due", "unpaid", "incomplete", "paused")))):
        raise HTTPException(409, "Manage your existing subscription in the billing portal.")
    api = stripe_client.client(s)
    try:
        if not user.stripe_customer_id:
            customer = api.v1.customers.create({"email": user.email, "metadata": {"user_id": user.id}}, options={"idempotency_key": "customer-" + user.id})
            user.stripe_customer_id = customer.id
            # Persist mapping before Checkout can emit any subscription webhook.
            db.commit(); lock_user(db, user.id); db.refresh(user)
        if user.checkout_session_id:
            prior = api.v1.checkout.sessions.retrieve(user.checkout_session_id)
            if prior.status == "open":
                if prior.metadata.get("plan") == body.plan: return {"url": prior.url}
                api.v1.checkout.sessions.expire(prior.id)
            if prior.status == "complete":
                previous = db.scalar(select(Subscription).where(Subscription.stripe_sub_id == prior.subscription))
                if not previous or previous.status not in ("canceled", "incomplete_expired"):
                    raise HTTPException(409, "Your payment is syncing. Refresh in a moment or use the billing portal.")
        session = api.v1.checkout.sessions.create({"mode": "subscription", "customer": user.stripe_customer_id,
            "line_items": [{"price": price, "quantity": 1}], "client_reference_id": user.id, "metadata": {"plan": body.plan},
            "subscription_data": {"metadata": {"user_id": user.id}},
            "success_url": s.public_url + "/?billing=success#plans", "cancel_url": s.public_url + "/?billing=cancelled#plans"},
            options={"idempotency_key": f"checkout-{user.id}-{user.checkout_session_id or 'first'}-{body.plan}"})
        user.checkout_session_id = session.id; db.commit()
        return {"url": session.url}
    except stripe.StripeError as exc:
        db.rollback(); raise HTTPException(502, "The payment service is unavailable. Please try again.") from exc

@router.post("/portal")
def portal(request: Request, user: User = Depends(current_user)):
    s = request.app.state.settings
    if s.local_mode or not user.stripe_customer_id: raise HTTPException(400, "No billing account exists yet.")
    try:
        session = stripe_client.client(s).v1.billing_portal.sessions.create({"customer": user.stripe_customer_id, "return_url": s.public_url + "/#plans"})
        return {"url": session.url}
    except stripe.StripeError as exc: raise HTTPException(502, "The billing portal is unavailable. Please try again.") from exc

def process_event(event, s, db):
    if db.get(BillingEvent, event["id"]): return {"received": True}
    if bool(event.get("livemode")) != s.stripe_secret_key.startswith("sk_live_"):
        raise HTTPException(400, "Webhook mode does not match the configured key.")
    if event["type"] not in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        return {"received": True}
    obj = event["data"]["object"]
    user = db.scalar(select(User).where(User.stripe_customer_id == obj.get("customer"))) if obj.get("customer") else None
    if user is None: return {"received": True}  # another product's customer
    lock_user(db, user.id)
    # Fetch after obtaining the per-customer lock: delayed events cannot restore stale access.
    try: sub = stripe_client.client(s).v1.subscriptions.retrieve(obj["id"])
    except stripe.StripeError as exc: raise HTTPException(503, "Subscription sync failed; retry this event.") from exc
    if sub.get("customer") != user.stripe_customer_id: raise HTTPException(400, "Subscription customer mismatch.")
    prices = {s.stripe_pro_price: "pro", s.stripe_team_price: "team"}
    items = sub.get("items", {}).get("data", [])
    plan = prices.get(items[0].get("price", {}).get("id")) if len(items) == 1 else None
    if not plan: plan = "free"  # unknown prices never grant paid access
    row = db.scalar(select(Subscription).where(Subscription.stripe_sub_id == sub["id"]))
    if row is None:
        row = Subscription(owner_type="user", owner_id=user.id, stripe_sub_id=sub["id"]); db.add(row)
    end = sub.get("current_period_end") or (items[0].get("current_period_end") if items else None)
    row.plan, row.status = plan, sub["status"]
    row.current_period_end = datetime.fromtimestamp(end, timezone.utc).replace(tzinfo=None) if end else None
    db.flush(); user.plan_id = effective_plan(db, user).id
    db.add(BillingEvent(id=event["id"]))
    try: db.commit()
    except IntegrityError:
        db.rollback()
        if not db.get(BillingEvent, event["id"]): raise
    return {"received": True}

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    s = request.app.state.settings
    payload = await request.body()
    if len(payload) > 1024 * 1024: raise HTTPException(413, "Webhook too large.")
    event = stripe_client.verify(s, payload, request.headers.get("stripe-signature", ""))
    return await run_in_threadpool(process_event, event, s, db)
