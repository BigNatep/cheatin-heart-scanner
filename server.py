"""
Aussie Cheaters Exposed — Production Web App
=============================================
Safe, secure, and people can actually use it.
Web UI + Stripe Checkout + rate limiting.
"""

import asyncio
import hashlib
import json
import re
import os
import time
import hmac
import base64
from pathlib import Path
from datetime import datetime, timedelta

import stripe
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from cheatin_scanner.core import scan_all, PLATFORMS

# ── Config ─────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")  # Fallback one-time
# Subscription price IDs — set these in your Stripe dashboard
STRIPE_PRICE_1M = os.environ.get("STRIPE_PRICE_1M", "")   # $25/mo
STRIPE_PRICE_3M = os.environ.get("STRIPE_PRICE_3M", "")   # $12/mo x3 = $36
STRIPE_PRICE_6M = os.environ.get("STRIPE_PRICE_6M", "")   # $8.99/mo x6 = $53.94
STRIPE_PRICE_OT = os.environ.get("STRIPE_PRICE_OT", "")   # $19.99 one-time
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
stripe.api_key = STRIPE_SECRET_KEY

# ── Subscription Store (simple JSON file) ──────────────────────────────
SUBS_FILE = Path(__file__).parent / "subscriptions.json"

def _load_subs() -> dict:
    if SUBS_FILE.exists():
        return json.loads(SUBS_FILE.read_text())
    return {}

def _save_subs(subs: dict):
    SUBS_FILE.write_text(json.dumps(subs, indent=2))

def _get_customer_email(session_id: str) -> str | None:
    """Retrieve the customer email from a Stripe Checkout session."""
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["customer"])
        if session.customer:
            if isinstance(session.customer, dict):
                return session.customer.get("email")
            # If it's a string ID
            cust = stripe.Customer.retrieve(session.customer)
            return cust.get("email")
        return None
    except Exception:
        return None

def _check_subscription(email: str) -> bool:
    """Check if an email has an active Stripe subscription."""
    subs = _load_subs()
    sub_id = subs.get(email)
    if not sub_id:
        return False
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        return sub.status in ("active", "trialing", "past_due")
    except Exception:
        return False

# ── Auth ────────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET", "cheatin-heart-jwt-secret-2026")
JWT_EXPIRY_HOURS = 72
USERS_FILE = Path(__file__).parent / "users.json"


def _load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}


def _save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, indent=2))


def _make_token(username: str) -> str:
    payload = json.dumps({"u": username, "t": time.time() + JWT_EXPIRY_HOURS * 3600})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


def _verify_token(token: str) -> str | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        encoded, sig = parts
        expected = hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=="))
        if payload["t"] < time.time():
            return None
        return payload["u"]
    except Exception:
        return None


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Ensure admin user exists
users = _load_users()
if "ruff_admin" not in users:
    users["ruff_admin"] = {
        "password": _hash_password("ruff_admin"),
        "role": "admin",
        "created": time.time(),
    }
    _save_users(users)
    print("✅ Created admin user: ruff_admin / ruff_admin")


# ── Rate limiting ──────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["10/hour"])
app = FastAPI(title="Aussie Cheaters Exposed", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Landing page ───────────────────────────────────────────────────────
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aussie Cheaters Exposed — Who's the Dirty Mongrel?</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }

    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: #0b0b12;
      color: #e5e5e5;
      min-height: 100vh;
    }

    /* ── Nav ── */
    nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      max-width: 1100px;
      margin: 0 auto;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }

    nav .logo {
      font-size: 20px;
      font-weight: 800;
      color: #fff;
    }
    nav .logo span { color: #ef4444; }

    nav .nav-links {
      display: flex;
      gap: 24px;
      align-items: center;
    }
    nav .nav-links a {
      color: rgba(255,255,255,0.5);
      text-decoration: none;
      font-size: 14px;
      font-weight: 500;
      transition: color 0.2s;
    }
    nav .nav-links a:hover { color: #fff; }
    nav .nav-cta {
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: #fff;
      padding: 10px 24px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 14px;
      text-decoration: none;
      transition: all 0.2s;
    }
    nav .nav-cta:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(239,68,68,0.3); }

    /* ── Hero ── */
    .hero {
      max-width: 1100px;
      margin: 0 auto;
      padding: 60px 24px 40px;
      display: flex;
      align-items: center;
      gap: 60px;
    }

    .hero-left { flex: 1; }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(239,68,68,0.1);
      border: 1px solid rgba(239,68,68,0.2);
      border-radius: 20px;
      padding: 6px 14px;
      font-size: 13px;
      color: #fca5a5;
      margin-bottom: 20px;
    }
    .hero-badge .dot {
      width: 6px; height: 6px;
      background: #22c55e;
      border-radius: 50%;
      animation: blink 1.5s infinite;
    }
    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .hero h1 {
      font-size: 52px;
      font-weight: 900;
      line-height: 1.1;
      margin-bottom: 16px;
      letter-spacing: -1px;
    }
    .hero h1 span { color: #ef4444; }
    .hero h1 .aus { color: #fbbf24; }

    .hero p {
      font-size: 18px;
      color: rgba(255,255,255,0.5);
      line-height: 1.6;
      max-width: 480px;
      margin-bottom: 32px;
    }

    .hero-stats {
      display: flex;
      gap: 32px;
      margin-bottom: 32px;
    }
    .hero-stat { text-align: left; }
    .hero-stat .num {
      font-size: 28px;
      font-weight: 800;
      color: #fff;
    }
    .hero-stat .label {
      font-size: 13px;
      color: rgba(255,255,255,0.35);
      margin-top: 2px;
    }

    .hero-cta {
      display: inline-block;
      padding: 18px 40px;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: #fff;
      font-size: 18px;
      font-weight: 700;
      border-radius: 12px;
      text-decoration: none;
      box-shadow: 0 8px 32px rgba(239,68,68,0.25);
      transition: all 0.3s;
      border: none;
      cursor: pointer;
    }
    .hero-cta:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(239,68,68,0.4); }
    .hero-cta .sub {
      display: block;
      font-size: 13px;
      font-weight: 400;
      opacity: 0.7;
      margin-top: 4px;
    }

    .hero-right {
      flex: 0 0 320px;
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 16px;
      padding: 24px;
    }
    .hero-right .result-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      font-size: 14px;
    }
    .hero-right .result-row:last-child { border-bottom: none; }
    .found-badge { color: #22c55e; font-weight: 700; font-size: 13px; }
    .miss-badge { color: #6b7280; }
    .hero-right .score-text {
      text-align: center;
      font-size: 12px;
      color: rgba(255,255,255,0.3);
      margin-top: 8px;
    }

    /* ── Social Proof ── */
    .social-proof {
      max-width: 1100px;
      margin: 0 auto;
      padding: 40px 24px;
      text-align: center;
    }
    .social-proof h2 {
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .social-proof .sub {
      color: rgba(255,255,255,0.4);
      font-size: 15px;
      margin-bottom: 32px;
    }
    .testimonials {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 700px) {
      .testimonials { grid-template-columns: 1fr; }
      .hero { flex-direction: column; padding: 40px 24px; }
      .hero h1 { font-size: 36px; }
      .hero-right { flex: unset; width: 100%; }
    }
    .tweet {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px;
      padding: 20px;
      text-align: left;
    }
    .tweet .head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .tweet .avatar {
      width: 36px; height: 36px;
      border-radius: 50%;
      background: linear-gradient(135deg, #ef444433, #f9731633);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 14px;
      color: #fca5a5;
    }
    .tweet .name { font-size: 14px; font-weight: 600; }
    .tweet .handle { font-size: 12px; color: rgba(255,255,255,0.3); }
    .tweet .body { font-size: 14px; line-height: 1.5; color: rgba(255,255,255,0.7); }
    .tweet .icons {
      display: flex; gap: 16px; margin-top: 12px;
      font-size: 12px; color: rgba(255,255,255,0.2);
    }

    /* ── How It Works ── */
    .how-it-works {
      max-width: 1100px;
      margin: 0 auto;
      padding: 60px 24px;
      text-align: center;
    }
    .how-it-works h2 {
      font-size: 32px;
      font-weight: 800;
      margin-bottom: 12px;
    }
    .how-it-works > p {
      color: rgba(255,255,255,0.4);
      font-size: 16px;
      margin-bottom: 48px;
    }
    .steps {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 24px;
    }
    @media (max-width: 700px) { .steps { grid-template-columns: 1fr; } }
    .step {
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 16px;
      padding: 32px 24px;
      text-align: center;
    }
    .step .num {
      width: 40px; height: 40px;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      margin: 0 auto 16px;
    }
    .step h3 { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
    .step p { font-size: 14px; color: rgba(255,255,255,0.45); line-height: 1.6; }
    .step .icon { font-size: 36px; margin-bottom: 12px; }

    /* ── Platforms ── */
    .platforms {
      max-width: 1100px;
      margin: 0 auto;
      padding: 40px 24px;
      text-align: center;
    }
    .platforms p {
      font-size: 14px;
      color: rgba(255,255,255,0.3);
      margin-bottom: 16px;
    }
    .platform-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: center;
    }
    .plat-tag {
      padding: 8px 16px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      font-size: 14px;
      color: rgba(255,255,255,0.5);
    }

    /* ── FAQ ── */
    .faq {
      max-width: 700px;
      margin: 0 auto;
      padding: 60px 24px;
    }
    .faq h2 {
      text-align: center;
      font-size: 28px;
      font-weight: 800;
      margin-bottom: 32px;
    }
    .faq-item {
      border-bottom: 1px solid rgba(255,255,255,0.05);
      padding: 20px 0;
    }
    .faq-q {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 600;
      font-size: 16px;
      cursor: pointer;
    }
    .faq-q .toggle { color: rgba(255,255,255,0.2); font-size: 20px; }
    .faq-a {
      margin-top: 12px;
      font-size: 14px;
      color: rgba(255,255,255,0.45);
      line-height: 1.6;
      display: none;
    }
    .faq-a.open { display: block; }

    /* ── CTA Section ── */
    .cta-section {
      max-width: 1100px;
      margin: 0 auto;
      padding: 60px 24px 80px;
      text-align: center;
    }
    .cta-section h2 {
      font-size: 36px;
      font-weight: 900;
      margin-bottom: 12px;
    }
    .cta-section p {
      color: rgba(255,255,255,0.4);
      font-size: 16px;
      margin-bottom: 32px;
    }

    /* ── Footer ── */
    footer {
      text-align: center;
      padding: 32px 24px;
      border-top: 1px solid rgba(255,255,255,0.04);
      font-size: 13px;
      color: rgba(255,255,255,0.15);
    }
    footer a { color: rgba(239,68,68,0.4); text-decoration: none; }
    footer a:hover { color: rgba(239,68,68,0.8); }

    /* ── Scanner form ── */
    .scanner-card {
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 16px;
      padding: 32px;
      max-width: 480px;
      margin: 32px auto 0;
      text-align: left;
    }
    .scanner-card label {
      display: block;
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #ccc;
    }
    .scanner-card input {
      width: 100%;
      padding: 14px 16px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.1);
      background: #0b0b12;
      color: #fff;
      font-size: 16px;
      outline: none;
      transition: border-color 0.2s;
    }
    .scanner-card input:focus { border-color: #ef4444; }
    .scanner-card .hint {
      font-size: 13px;
      color: rgba(255,255,255,0.3);
      margin: 8px 0 20px;
    }
    .scanner-card button {
      width: 100%;
      padding: 16px;
      border: none;
      border-radius: 10px;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: #fff;
      transition: all 0.2s;
    }
    .scanner-card button:hover { opacity: 0.9; }
    .scanner-card button:disabled { opacity: 0.5; cursor: not-allowed; }

    /* ── Responsive ── */
    @media (max-width: 480px) {
      .hero h1 { font-size: 28px; }
      .hero-stats { gap: 16px; }
      .hero-stat .num { font-size: 22px; }
      nav .nav-links a:not(.nav-cta) { display: none; }
    }
  </style>
</head>
<body>

  <!-- Nav -->
  <nav>
    <div class="logo">💔 Aussie <span>Cheaters</span></div>
    <div class="nav-links">
      <a href="#how">How It Works</a>
      <a href="#faq">FAQ</a>
      <a href="#scan" class="nav-cta">🔍 Scan Now</a>
    </div>
  </nav>

  <!-- Hero -->
  <div class="hero">
    <div class="hero-left">
      <div class="hero-badge">
        <span class="dot"></span>
        Trusted by suspicious Aussies nationwide
      </div>
      <h1>Found a <span>cheating</span> <span class="aus">mongrel</span>?<br/>We'll find the proof.</h1>
      <p>Search 12 Australian dating & social platforms by email, username, or phone. See if they're being faithful — or if they're full of shit.</p>
      <div class="hero-stats">
        <div class="hero-stat">
          <div class="num">12</div>
          <div class="label">Aussie Platforms</div>
        </div>
        <div class="hero-stat">
          <div class="num">∞</div>
          <div class="label">Unlimited</div>
        </div>
        <div class="hero-stat">
          <div class="num">🔒</div>
          <div class="label">Discreet & Encrypted</div>
        </div>
      </div>
      <a href="/pricing" class="hero-cta">
        🔍 Start Searching
        <span class="sub">From $8.99/mo · Unlimited searches · Cancel anytime</span>
      </a>
    </div>
    <div class="hero-right">
      <div style="font-size:13px;font-weight:600;margin-bottom:12px;color:rgba(255,255,255,0.5);">Example Result</div>
      <div class="result-row">
        <span>📸 Instagram</span>
        <span class="found-badge">✅ Profile found</span>
      </div>
      <div class="result-row">
        <span>💕 RSVP</span>
        <span class="found-badge">✅ Profile found</span>
      </div>
      <div class="result-row">
        <span>🎣 Plenty of Fish</span>
        <span class="found-badge">✅ Profile found</span>
      </div>
      <div class="result-row">
        <span>💬 Telegram</span>
        <span class="miss-badge">❌ Not found</span>
      </div>
      <div class="result-row">
        <span>🔞 OnlyFans</span>
        <span class="miss-badge">❌ Not found</span>
      </div>
      <div class="score-text">⚠️ 3/5 profiles found — might be worth a closer look, mate.</div>
    </div>
  </div>

  <!-- Social Proof -->
  <div class="social-proof">
    <h2>The word on the street</h2>
    <p class="sub">Real talk from real people who found out the hard way.</p>
    <div class="testimonials">
      <div class="tweet">
        <div class="head">
          <div class="avatar">SW</div>
          <div>
            <div class="name">Sheila W.</div>
            <div class="handle">@sheila_westie</div>
          </div>
        </div>
        <div class="body">Found my fiance on RSVP and Plenty of Fish. $1 well bloody spent. Cheatin' Heart is mad 👊</div>
        <div class="icons">❤️ 24 🔄 8 💬 3</div>
      </div>
      <div class="tweet">
        <div class="head">
          <div class="avatar">DB</div>
          <div>
            <div class="name">Darren B.</div>
            <div class="handle">@darren_bne</div>
          </div>
        </div>
        <div class="body">Mate I said I was just on Telegram for the groups. Cheatin' Heart outed my RedHotPie profile in 3 seconds. Deadset cooked.</div>
        <div class="icons">❤️ 56 🔄 12 💬 18</div>
      </div>
      <div class="tweet">
        <div class="head">
          <div class="avatar">TJ</div>
          <div>
            <div class="name">Tanya J.</div>
            <div class="handle">@tanya_adl</div>
          </div>
        </div>
        <div class="body">Ex said he wasn't on any apps. Three profiles later and I had all the evidence I needed. Best dollar I ever spent 🔥</div>
        <div class="icons">❤️ 42 🔄 7 💬 9</div>
      </div>
    </div>
  </div>

  <!-- How It Works -->
  <div class="how-it-works" id="how">
    <h2>How It Works</h2>
    <p>Three steps. One dollar. No drama.</p>
    <div class="steps">
      <div class="step">
        <div class="icon">🔍</div>
        <div class="num">1</div>
        <h3>Enter their details</h3>
        <p>Type in their email, username, or phone number. We'll handle the rest — even just a username is enough to start.</p>
      </div>
      <div class="step">
        <div class="icon">🦘</div>
        <div class="num">2</div>
        <h3>We scan 12 platforms</h3>
        <p>Snapchat, Telegram, TikTok, Instagram, X, RSVP, Plenty of Fish, RedHotPie, AdultFriendFinder, OnlyFans, FetLife, OKCupid — all in seconds.</p>
      </div>
      <div class="step">
        <div class="icon">📋</div>
        <div class="num">3</div>
        <h3>Get the full report</h3>
        <p>See exactly which platforms have profiles, with links and evidence. Clean, discreet, and nothing is stored.</p>
      </div>
    </div>
  </div>

  <!-- Platforms -->
  <div class="platforms">
    <p>Platforms we check</p>
    <div class="platform-grid">
      <span class="plat-tag">💬 Telegram</span>
      <span class="plat-tag">👻 Snapchat</span>
      <span class="plat-tag">🎵 TikTok</span>
      <span class="plat-tag">📸 Instagram</span>
      <span class="plat-tag">🐦 X / Twitter</span>
      <span class="plat-tag">❤️ RedHotPie</span>
      <span class="plat-tag">🔥 AdultFriendFinder</span>
      <span class="plat-tag">💕 RSVP</span>
      <span class="plat-tag">🎣 Plenty of Fish</span>
      <span class="plat-tag">🔞 OnlyFans</span>
      <span class="plat-tag">🔗 FetLife</span>
      <span class="plat-tag">💘 OKCupid</span>
    </div>
  </div>

  <!-- Scanner Form -->
  <div class="cta-section" id="scan">
    <h2>Find the truth. <span style="color:#ef4444;">Subscribe.</span></h2>
    <p>Enter their details for a free preview — subscribe to unlock all 12 platforms.</p>
    <div class="scanner-card">
      <form id="scanForm" onsubmit="return doScan(event)">
        <label for="username">Email, Username or Phone</label>
        <input type="text" id="username" name="username" placeholder="e.g. johnno84 or johnno@bigpond.com" required />
        <div class="hint">Just one is enough — we'll figure out the rest.</div>
        <button type="submit" id="submitBtn">🔍 Sniff Around</button>
      </form>
      <div id="results" style="margin-top:16px;"></div>
    </div>
  </div>

  <!-- FAQ -->
  <div class="faq" id="faq">
    <h2>FAQs</h2>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Is this anonymous? <span class="toggle">+</span></div>
      <div class="faq-a">100%. Your search is encrypted via Stripe. No results stored and we never see your card details. Your secret's safe with us.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">How does it work? <span class="toggle">+</span></div>
      <div class="faq-a">Enter a username, email or phone and we scan 12 Aussie dating & social platforms in real-time. We check if they have an active public profile — no login needed.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">What platforms do you check? <span class="toggle">+</span></div>
      <div class="faq-a">Snapchat, Instagram, Telegram, X/Twitter, TikTok, RedHotPie, AdultFriendFinder, RSVP, Plenty of Fish, OKCupid, OnlyFans and FetLife. Adding more regularly.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">How much does it cost? <span class="toggle">+</span></div>
      <div class="faq-a">2 free preview results. One-time full report is $19.99. Prefer unlimited? Subscriptions from $8.99/mo — cancel anytime.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Is this legal? <span class="toggle">+</span></div>
      <div class="faq-a">We only check publicly available info — the same profiles anyone can find by searching. We don't hack, steal or access private accounts. For informational purposes only.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Can I search by phone number? <span class="toggle">+</span></div>
      <div class="faq-a">Yes! Enter any number and we'll check across all platforms. Enhanced phone OSINT with carrier and location data coming soon.</div>
    </div>
  </div>

  <!-- Bottom CTA -->
  <div class="cta-section" style="padding-top:0;">
    <a href="/pricing" class="hero-cta">🔍 Start Searching — From $8.99/mo</a>
  </div>

  <footer>
    <p>Rough Guts Media · <a href="/pricing">Pricing</a> · <a href="/privacy">Privacy</a> · <a href="#" onclick="alert('Email: info@aussiecheatersexposed.com.au');return false;">Contact</a></p>
    <p style="margin-top:4px;">🔒 Discreet · Encrypted · Australian-owned</p>
  </footer>

  <script>
    const PLATFORMS = {platforms_json};

    function toggleFaq(el) {
      const answer = el.nextElementSibling;
      const toggle = el.querySelector('.toggle');
      answer.classList.toggle('open');
      toggle.textContent = answer.classList.contains('open') ? '\u2212' : '+';
    }

    async function doScan(e) {
      e.preventDefault();
      const username = document.getElementById('username').value.trim();
      if (!username) return;
      const submitBtn = document.getElementById('submitBtn');
      submitBtn.disabled = true;
      submitBtn.textContent = '\U0001f998 Scanning...';
      document.getElementById('results').innerHTML = '<div style="text-align:center;padding:1rem;font-size:2rem;">\U0001f998</div>';

      try {
        const resp = await fetch('/scan?username=' + encodeURIComponent(username) + '&preview=true');
        if (!resp.ok) throw new Error('Scan failed');
        const data = await resp.json();
        renderPreview(data, username);
      } catch (err) {
        document.getElementById('results').innerHTML =
          '<div style="color:#f87171;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:1rem;margin-top:1rem;">\u274c ' + err.message + '</div>';
        submitBtn.disabled = false;
        submitBtn.textContent = '\U0001f50d Sniff Around';
      }
    }

    function renderPreview(data, username) {
      const results = data.results || [];
      const total = data.total_platforms || 0;
      let html = '<h2 style="margin:1.5rem 0 1rem;font-size:24px;">\U0001f4ca Preview</h2>';
      html += '<div style="text-align:center;font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:16px;">Found <strong style="color:#fff;">' + total + '</strong> profiles found — here\'s 2 for free:</div>';

      for (const item of results) {
        const icon = item.profileFound ? '\u2705' : item.error ? '\u26a0\ufe0f' : '\u274c';
        const cls = item.profileFound ? '#22c55e' : item.error ? '#f59e0b' : '#6b7280';
        html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:0.8rem 1rem;margin-bottom:0.4rem;display:flex;justify-content:space-between;align-items:center;">';
        html += '<span>' + icon + ' ' + item.platformLabel + '</span>';
        html += '<span style="color:' + cls + '">' + (item.evidence || '') + '</span></div>';
      }

      // Paywall CTA
      html += '<div style="background:linear-gradient(180deg,rgba(239,68,68,0.1),transparent);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:24px;text-align:center;margin-top:20px;">';
      html += '<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">\U0001f512 ' + (total - 2) + ' results locked</div>';
      html += '<div style="font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:16px;">Subscribe or pay once to unlock all results.</div>';
      html += '<a href="/pricing" style="display:block;width:100%;padding:16px;border:none;border-radius:10px;font-size:16px;font-weight:700;text-align:center;text-decoration:none;cursor:pointer;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;box-shadow:0 8px 24px rgba(239,68,68,0.3);">\U0001f513 Unlock Full Results</a>';
      html += '<div style="margin-top:10px;font-size:12px;color:rgba(255,255,255,0.2);">From $8.99/mo or $19.99 one search</div>';
      html += '</div>';
      html += '<button onclick="document.getElementById(\'results\').innerHTML=\'\';document.getElementById(\'username\').value=\'\';submitBtn.disabled=false;submitBtn.textContent=\'\U0001f50d Sniff Around\'" style="width:100%;padding:0.8rem;border:none;border-radius:10px;font-size:0.9rem;font-weight:600;cursor:pointer;background:transparent;color:rgba(255,255,255,0.3);margin-top:12px;">\u2190 Try another search</button>';
      document.getElementById('results').innerHTML = html;
      document.getElementById('submitBtn').disabled = false;
      document.getElementById('submitBtn').textContent = '\U0001f50d Sniff Around';
    }

    window.addEventListener('DOMContentLoaded', async () => {
      const params = new URLSearchParams(window.location.search);
      const username = params.get('username');
      const sessionId = params.get('session_id');
      if (username && sessionId) {
        document.getElementById('username').value = username;
        document.getElementById('submitBtn').disabled = true;
        document.getElementById('submitBtn').textContent = '\U0001f998 Loading results...';
        document.getElementById('results').innerHTML = '<div style="text-align:center;padding:2rem;">Loading your results...</div>';
        try {
          const resp = await fetch('/scan?username=' + encodeURIComponent(username) + '&session_id=' + sessionId);
          if (!resp.ok) throw new Error('Scan failed');
          const data = await resp.json();
          renderResults(data);
        } catch (err) {
          document.getElementById('results').innerHTML =
            '<div style="color:#f87171;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:1rem;margin-top:1rem;">\u274c ' + err.message + '</div>';
        }
        document.getElementById('submitBtn').disabled = false;
        document.getElementById('submitBtn').textContent = '\U0001f50d Sniff Around';
      }
    });

    function renderResults(data) {
      let html = '<h2 style="margin:1.5rem 0 1rem;font-size:24px;">\U0001f4ca Results</h2>';
      let enrichmentItems = [];
      let found = 0, total = 0;
      for (const item of data) {
        if (item.type === 'summary') {
          const s = item.summary;
          found = s.profilesFound; total = s.platformsChecked;
          const pct = s.score;
          const color = pct > 50 ? '#ef4444' : pct > 0 ? '#f59e0b' : '#22c55e';
          html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:1.5rem;margin-bottom:1rem;">';
          html += '<div style="font-size:2rem;font-weight:800;text-align:center;padding:1rem;">' + found + '/' + total + ' profiles found</div>';
          html += '<div style="height:8px;border-radius:4px;background:rgba(255,255,255,0.05);overflow:hidden;margin:0.5rem 0 1rem;"><div style="height:100%;border-radius:4px;width:' + pct + '%;background:' + color + ';transition:width 0.5s;"></div></div>';
          html += '<div style="text-align:center;font-size:0.9rem;color:rgba(255,255,255,0.4);">';
          if (pct > 50) html += '\U0001f6a9 Lookin pretty dodgy, mate.';
          else if (pct > 0) html += '\u26a0\ufe0f Maybe worth a closer look.';
          else html += '\u2705 Clean as a whistle.';
          html += '</div></div>';
        } else if (item.platform) {
          const cls = item.profileFound ? '#22c55e' : item.error ? '#f59e0b' : '#6b7280';
          const icon = item.profileFound ? '\u2705' : item.error ? '\u26a0\ufe0f' : '\u274c';
          // Enrichment items — collect
          if (item.platform === 'sherlock' || item.platform === 'holehe' || item.platform === 'telegram_profile' || item.platform === 'x_profile') {
            enrichmentItems.push(item);
            continue;
          }
          html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:0.8rem 1rem;margin-bottom:0.4rem;display:flex;justify-content:space-between;align-items:center;">';
          html += '<span>' + icon + ' ' + item.platformLabel + '</span>';
          html += '<span style="color:' + cls + '">' + (item.evidence || '') + '</span></div>';
        }
      }

      // Enrichment section
      if (enrichmentItems.length > 0) {
        html += '<div style="margin-top:1rem;padding-top:0.8rem;border-top:1px solid rgba(255,255,255,0.06);">';
        html += '<div style="font-size:0.9rem;font-weight:700;margin-bottom:0.5rem;color:rgba(255,255,255,0.5);">\U0001f50d Enrichment / OSINT</div>';
        for (const item of enrichmentItems) {
          if (item.platform === 'sherlock') {
            const count = (item.sherlock_sites_found || []).length;
            html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;font-size:0.85rem;">';
            html += '<div style="display:flex;justify-content:space-between;"><span>\U0001f50d Sherlock</span><span style="color:' + (count > 0 ? '#22c55e' : '#6b7280') + '">' + (count > 0 ? count + ' found' : 'None') + '</span></div>';
            if (count > 0) {
              html += '<div style="margin-top:0.3rem;max-height:100px;overflow-y:auto;">';
              for (const site of item.sherlock_sites_found.slice(0, 15)) {
                html += '<div>\u2022 <a href="' + site.url + '" target="_blank" style="color:#f97316;text-decoration:none;">' + site.name + '</a></div>';
              }
              if (count > 15) html += '<div style="color:rgba(255,255,255,0.3);">\u2026 and ' + (count - 15) + ' more</div>';
              html += '</div>';
            }
            html += '</div>';
          } else if (item.platform === 'holehe') {
            const count = (item.holehe_sites_found || []).length;
            html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;font-size:0.85rem;">';
            html += '<div style="display:flex;justify-content:space-between;"><span>\U0001f4e7 Holehe</span><span style="color:' + (count > 0 ? '#22c55e' : '#6b7280') + '">' + (count > 0 ? count + ' found' : 'None') + '</span></div>';
            if (count > 0) {
              html += '<div style="margin-top:0.3rem;max-height:100px;overflow-y:auto;">';
              for (const site of item.holehe_sites_found) {
                html += '<div>\u2022 ' + site + '</div>';
              }
              html += '</div>';
            }
            html += '</div>';
          } else if (item.platform === 'telegram_profile') {
            const pd = item.profileData || {};
            html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;font-size:0.85rem;">';
            if (pd.photo_url) html += '<img src="' + pd.photo_url + '" style="width:32px;height:32px;border-radius:50%;object-fit:cover;float:left;margin-right:8px;" />';
            html += '<div style="font-weight:600;">' + (pd.name || 'Telegram') + '</div>';
            if (pd.bio) html += '<div style="color:rgba(255,255,255,0.5);font-size:0.8rem;">' + pd.bio + '</div>';
            html += '<a href="https://t.me/' + item.username + '" target="_blank" style="color:#f97316;text-decoration:none;font-size:0.8rem;">t.me/' + item.username + '</a>';
            html += '</div>';
          } else if (item.platform === 'x_profile') {
            const pd = item.profileData || {};
            html += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;font-size:0.85rem;">';
            if (pd.photo_url) html += '<img src="' + pd.photo_url + '" style="width:32px;height:32px;border-radius:50%;object-fit:cover;float:left;margin-right:8px;" />';
            html += '<div style="font-weight:600;">' + (pd.name || 'X / Twitter') + '</div>';
            if (pd.bio) html += '<div style="color:rgba(255,255,255,0.5);font-size:0.8rem;">' + pd.bio.substring(0, 100) + '</div>';
            html += '<a href="https://x.com/' + item.username + '" target="_blank" style="color:#f97316;text-decoration:none;font-size:0.8rem;">x.com/' + item.username + '</a>';
            html += '</div>';
          }
        }
        html += '</div>';
      }

      html += '<button onclick="window.location.href=\'#scan\'" style="width:100%;padding:1rem;border:none;border-radius:10px;font-size:1rem;font-weight:700;cursor:pointer;background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.5);margin-top:0.5rem;">\U0001f50d Scan someone else</button>';
      document.getElementById('results').innerHTML = html;
    }
  </script>
</body>
</html>"""


@app.on_event("startup")
async def startup():
    """Warn if Stripe isn't configured."""
    if not STRIPE_SECRET_KEY:
        print("⚠️  STRIPE_SECRET_KEY not set — payment will fail")
    if not STRIPE_PRICE_ID:
        print("⚠️  STRIPE_PRICE_ID not set — payment will fail")


@app.get("/", response_class=HTMLResponse)
async def landing():
    return LANDING_HTML.replace("{platforms_json}", json.dumps(PLATFORMS))


@app.get("/health")
async def health():
    return {"status": "ok"}


PRICING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pricing — Aussie Cheaters Exposed</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; background: #0b0b12; color: #e5e5e5; min-height: 100vh; }
    .container { max-width: 800px; margin: 0 auto; padding: 40px 24px; }
    .back { display: inline-block; margin-bottom: 24px; color: #ef4444; text-decoration: none; font-size: 14px; font-weight: 600; }
    .back:hover { text-decoration: underline; }
    h1 { font-size: 36px; font-weight: 900; text-align: center; margin-bottom: 6px; }
    h1 span { color: #ef4444; }
    .subtitle { text-align: center; color: rgba(255,255,255,0.4); font-size: 15px; margin-bottom: 8px; }
    .cancel-anytime { text-align: center; color: rgba(255,255,255,0.2); font-size: 13px; margin-bottom: 40px; }
    .plans { display: flex; flex-direction: column; gap: 16px; max-width: 500px; margin: 0 auto; }
    .plan { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 24px; cursor: pointer; transition: all 0.2s; position: relative; }
    .plan:hover { border-color: rgba(239,68,68,0.3); }
    .plan.selected { border-color: #ef4444; background: rgba(239,68,68,0.05); }
    .plan .badge { position: absolute; top: -1px; right: 16px; background: linear-gradient(135deg,#ef4444,#dc2626); color: #fff; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 0 0 8px 8px; text-transform: uppercase; letter-spacing: 1px; }
    .plan .top { display: flex; align-items: center; gap: 12px; }
    .plan .radio { width: 20px; height: 20px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .plan.selected .radio { border-color: #ef4444; }
    .plan.selected .radio::after { content: ''; width: 10px; height: 10px; border-radius: 50%; background: #ef4444; }
    .plan .price-row { display: flex; align-items: baseline; gap: 8px; }
    .plan .price { font-size: 28px; font-weight: 800; color: #fff; }
    .plan .period { font-size: 14px; color: rgba(255,255,255,0.3); }
    .plan .strike { font-size: 14px; color: rgba(255,255,255,0.15); text-decoration: line-through; }
    .plan .billed { font-size: 13px; color: rgba(255,255,255,0.3); margin-top: 4px; }
    .plan .tagline { font-size: 13px; color: rgba(255,255,255,0.4); margin-top: 2px; }
    .plan .features { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
    .plan .feature { display: flex; align-items: center; gap: 8px; font-size: 14px; color: rgba(255,255,255,0.6); }
    .plan .feature .check { color: #f97316; font-weight: 700; }
    .btn-subscribe { display: block; width: 100%; max-width: 500px; margin: 24px auto 0; padding: 18px; border: none; border-radius: 12px; font-size: 18px; font-weight: 800; cursor: pointer; background: linear-gradient(135deg,#ef4444,#dc2626); color: #fff; box-shadow: 0 8px 32px rgba(239,68,68,0.25); transition: all 0.2s; }
    .btn-subscribe:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(239,68,68,0.4); }
    .btn-subscribe:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .secure-note { text-align: center; font-size: 12px; color: rgba(255,255,255,0.15); margin-top: 12px; }
    .faq-mini { max-width: 500px; margin: 40px auto 0; }
    .faq-mini h3 { font-size: 18px; font-weight: 700; text-align: center; margin-bottom: 16px; }
    .faq-mini .item { border-bottom: 1px solid rgba(255,255,255,0.04); padding: 14px 0; }
    .faq-mini .q { font-size: 14px; font-weight: 600; cursor: pointer; display: flex; justify-content: space-between; }
    .faq-mini .q .tog { color: rgba(255,255,255,0.2); }
    .faq-mini .a { font-size: 13px; color: rgba(255,255,255,0.4); margin-top: 8px; display: none; line-height: 1.5; }
    .faq-mini .a.open { display: block; }
    @media (max-width: 480px) { h1 { font-size: 28px; } .plan { padding: 20px; } }
  </style>
</head>
<body>
  <div class="container">
    <a href="/" class="back">← Back</a>
    <h1>Simple <span>pricing</span></h1>
    <p class="subtitle">Unlimited searches. Full results. No hidden fees.</p>
    <p class="cancel-anytime">Cancel anytime. All plans include full access.</p>

    <div class="plans" id="plans">
      <div class="plan" data-plan="ot" onclick="selectPlan('ot')" style="border-color:rgba(239,68,68,0.2);">
        <div class="top">
          <div class="radio"></div>
          <div>
            <div class="price-row">
              <span class="price">$19.99</span>
              <span class="period">one-time</span>
              <span class="strike">$29.99</span>
            </div>
            <div class="tagline">Single search — no commitment</div>
          </div>
        </div>
        <div class="billed">$19.99 billed once</div>
        <div class="features">
          <div class="feature"><span class="check">✓</span> One full scan across 12 platforms</div>
          <div class="feature"><span class="check">✓</span> 100% private &amp; anonymous</div>
          <div class="feature"><span class="check">✓</span> No subscription required</div>
          <div class="feature"><span class="check">✓</span> Results not stored</div>
        </div>
      </div>

      <div style="text-align:center;color:rgba(255,255,255,0.1);font-size:12px;margin:4px 0;">— or subscribe for unlimited —</div>

      <div class="plan" data-plan="1m" onclick="selectPlan('1m')">
        <div class="top">
          <div class="radio"></div>
          <div>
            <div class="price-row">
              <span class="price">$25</span>
              <span class="period">/month</span>
              <span class="strike">$39.99</span>
            </div>
            <div class="tagline">Flexible month-to-month</div>
          </div>
        </div>
        <div class="billed">$25 billed now</div>
        <div class="features">
          <div class="feature"><span class="check">✓</span> Unlimited searches</div>
          <div class="feature"><span class="check">✓</span> 12 Aussie platforms checked</div>
          <div class="feature"><span class="check">✓</span> 100% private &amp; anonymous</div>
          <div class="feature"><span class="check">✓</span> Cancel anytime</div>
        </div>
      </div>

      <div class="plan" data-plan="3m" onclick="selectPlan('3m')">
        <div class="badge">Most Popular</div>
        <div class="top">
          <div class="radio"></div>
          <div>
            <div class="price-row">
              <span class="price">$12</span>
              <span class="period">/month</span>
              <span class="strike">$29.99</span>
            </div>
            <div class="tagline">Great balance of commitment &amp; savings</div>
          </div>
        </div>
        <div class="billed">$36 billed now</div>
        <div class="features">
          <div class="feature"><span class="check">✓</span> Unlimited searches</div>
          <div class="feature"><span class="check">✓</span> 12 Aussie platforms checked</div>
          <div class="feature"><span class="check">✓</span> 100% private &amp; anonymous</div>
          <div class="feature"><span class="check">✓</span> Cancel anytime</div>
        </div>
      </div>

      <div class="plan selected" data-plan="6m" onclick="selectPlan('6m')">
        <div class="badge" style="background:linear-gradient(135deg,#f97316,#ea580c);">Best Value</div>
        <div class="top">
          <div class="radio"></div>
          <div>
            <div class="price-row">
              <span class="price">$8.99</span>
              <span class="period">/month</span>
              <span class="strike">$19.99</span>
            </div>
            <div class="tagline">Best price per month — longest savings</div>
          </div>
        </div>
        <div class="billed">$53.94 billed now</div>
        <div class="features">
          <div class="feature"><span class="check">✓</span> Unlimited searches</div>
          <div class="feature"><span class="check">✓</span> 12 Aussie platforms checked</div>
          <div class="feature"><span class="check">✓</span> 100% private &amp; anonymous</div>
          <div class="feature"><span class="check">✓</span> Cancel anytime</div>
        </div>
      </div>
    </div>

    <button class="btn-subscribe" id="subBtn" onclick="subscribe()">Continue →</button>
    <p class="secure-note">🔒 Secure payment via Stripe · Cancel anytime</p>

    <div class="faq-mini">
      <h3>FAQs</h3>
      <div class="item">
        <div class="q" onclick="toggleFaq(this)">Can I cancel anytime? <span class="tog">+</span></div>
        <div class="a">Yep. Cancel from your Stripe dashboard and you keep access until the end of your billing period.</div>
      </div>
      <div class="item">
        <div class="q" onclick="toggleFaq(this)">What happens after I subscribe? <span class="tog">+</span></div>
        <div class="a">Enter any email, username, or phone and get full results across all 12 platforms immediately. Unlimited searches.</div>
      </div>
      <div class="item">
        <div class="q" onclick="toggleFaq(this)">Is my search anonymous? <span class="tog">+</span></div>
        <div class="a">100%. Results aren't stored and payment goes through Stripe — we never see your card details.</div>
      </div>
    </div>
  </div>

  <script>
    let selected = '3m';

    function selectPlan(plan) {
      selected = plan;
      document.querySelectorAll('.plan').forEach(p => {
        p.classList.toggle('selected', p.dataset.plan === plan);
      });
    }

    function toggleFaq(el) {
      const a = el.nextElementSibling;
      const t = el.querySelector('.tog');
      a.classList.toggle('open');
      t.textContent = a.classList.contains('open') ? '\u2212' : '+';
    }

    async function subscribe() {
      const btn = document.getElementById('subBtn');
      btn.disabled = true;
      btn.textContent = 'Redirecting to payment...';
      try {
        let resp;
        if (selected === 'ot') {
          // One-time payment — need username
          const username = prompt('Enter the email, username or phone to search:');
          if (!username) { btn.disabled = false; btn.textContent = 'Continue \u2192'; return; }
          resp = await fetch('/create-checkout-onetime', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan: selected, username: username })
          });
        } else {
          resp = await fetch('/create-subscription', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan: selected })
          });
        }
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        window.location.href = data.url;
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Continue \u2192';
        alert('Error: ' + err.message);
      }
    }
  </script>
</body>
</html>"""


@app.get("/pricing", response_class=HTMLResponse)
async def pricing():
    return PRICING_HTML


PRIVACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Privacy Policy — Aussie Cheaters Exposed</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; background: #0b0b12; color: #e5e5e5; min-height: 100vh; }
    .container { max-width: 760px; margin: 0 auto; padding: 60px 24px; }
    h1 { font-size: 36px; font-weight: 800; margin-bottom: 6px; }
    .date { color: rgba(255,255,255,0.3); font-size: 14px; margin-bottom: 40px; }
    h2 { font-size: 20px; font-weight: 700; margin: 32px 0 12px; }
    p { font-size: 15px; line-height: 1.7; color: rgba(255,255,255,0.6); margin-bottom: 12px; }
    ul { margin: 8px 0 16px 20px; }
    ul li { font-size: 15px; line-height: 1.7; color: rgba(255,255,255,0.6); margin-bottom: 6px; }
    .back { display: inline-block; margin-bottom: 32px; color: #ef4444; text-decoration: none; font-size: 14px; font-weight: 600; }
    .back:hover { text-decoration: underline; }
    .highlight { color: rgba(255,255,255,0.8); font-weight: 600; }
    hr { border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 40px 0; }
  </style>
</head>
<body>
  <div class="container">
    <a href="/" class="back">← Back to Scanner</a>
    <h1>Privacy Policy</h1>
    <div class="date">Effective Date: 13/07/2026</div>

    <p>Aussie Cheaters Exposed ("we", "our", or "the Service") respects your privacy and is committed to providing transparency regarding how information is handled.</p>

    <h2>1. Overview of the Service</h2>
    <p>Aussie Cheaters Exposed is a user-initiated search tool that checks whether a given email, username, or phone number has publicly visible profiles across Australian dating and social platforms.</p>
    <p>The Service does <span class="highlight">not</span> create or maintain profiles of individuals. It dynamically checks publicly accessible information based on a user's query and returns results in real-time.</p>

    <h2>2. Information Provided by Users</h2>
    <p>We collect and process information that users voluntarily provide when using the Service, including:</p>
    <ul>
      <li>Search inputs — email, username, or phone number entered by the user</li>
      <li>Payment and transaction information — processed via Stripe (we never see your card details)</li>
    </ul>
    <p>This information is used solely to process the search and return results.</p>

    <h2>3. How the Service Operates</h2>
    <ul>
      <li>Users initiate all searches</li>
      <li>Users provide the search term used to generate results</li>
      <li>The system processes these inputs and checks publicly accessible platforms</li>
      <li>Results are generated dynamically and are not stored as persistent profiles</li>
    </ul>

    <h2>4. Publicly Available Information</h2>
    <p>The Service only checks information that is already publicly accessible on each platform.</p>
    <p>The Service does <span class="highlight">not</span>:</p>
    <ul>
      <li>Access private or restricted accounts</li>
      <li>Bypass platform security measures</li>
      <li>Collect non-public personal data</li>
      <li>Store search results permanently</li>
    </ul>

    <h2>5. What We Do Not Do</h2>
    <ul>
      <li>Create or maintain profiles of individuals</li>
      <li>Provide real-time tracking or monitoring</li>
      <li>Access private communications or accounts</li>
      <li>Sell or share your personal information with third parties</li>
    </ul>

    <h2>6. Use of Information</h2>
    <p>We use information to:</p>
    <ul>
      <li>Provide search results requested by users</li>
      <li>Operate, maintain, and improve the Service</li>
      <li>Process payments via Stripe</li>
      <li>Ensure compliance with applicable laws</li>
    </ul>

    <h2>7. Data Retention</h2>
    <p>Search inputs may be retained temporarily for operational and security purposes. However, the Service does <span class="highlight">not</span> maintain long-term stored profiles or dossiers about individuals.</p>

    <h2>8. Third-Party Services</h2>
    <p>We use the following third-party providers:</p>
    <ul>
      <li><strong>Stripe</strong> — payment processing (see their privacy policy at <a href="https://stripe.com/privacy" style="color:#ef4444;">stripe.com/privacy</a>)</li>
      <li>Cloud infrastructure and hosting providers</li>
    </ul>
    <p>These providers process data in accordance with their own privacy policies.</p>

    <h2>9. User Responsibility</h2>
    <p>The Service is intended for informational purposes only. Users agree to use the Service in compliance with all applicable laws and platform guidelines.</p>

    <h2>10. Security</h2>
    <p>We implement reasonable technical and organisational measures to protect user-provided information. However, no system can guarantee absolute security.</p>

    <h2>11. Children's Privacy</h2>
    <p>The Service is not intended for use by individuals under the age of 18.</p>

    <h2>12. Changes to This Policy</h2>
    <p>We may update this Privacy Policy from time to time. Updates will be posted on this page with a revised effective date.</p>

    <h2>13. Contact</h2>
    <p>If you have questions about this Privacy Policy, contact us at <a href="mailto:info@aussiecheatersexposed.com.au" style="color:#ef4444;">info@aussiecheatersexposed.com.au</a></p>

    <hr />
    <p style="text-align:center;font-size:13px;color:rgba(255,255,255,0.2);">Aussie Cheaters Exposed · Rough Guts Media · ABN pending</p>
  </div>
</body>
</html>"""


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return PRIVACY_HTML


AUTH_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Login — Aussie Cheaters Exposed</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0b0b12;color:#e5e5e5;min-height:100vh;display:flex;align-items:center;justify-content:center}
.box{max-width:400px;width:100%;padding:40px 24px}
h1{font-size:28px;font-weight:800;margin-bottom:4px}
h1 span{color:#ef4444}
p.sub{color:rgba(255,255,255,0.3);font-size:14px;margin-bottom:24px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:#ccc}
.input-wrapper{position:relative;margin-bottom:16px}
.input-wrapper i{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:rgba(255,255,255,0.3);font-size:15px;z-index:1}
.input-wrapper input{width:100%;padding:12px 14px 12px 36px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:#0b0b12;color:#fff;font-size:15px;outline:none;margin-bottom:0}
.input-wrapper input:focus{border-color:#ef4444}
.btn{width:100%;padding:14px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff}
.btn:hover{opacity:.9}
.err{color:#f87171;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:10px;font-size:13px;margin-bottom:12px;display:none}
.foot{text-align:center;margin-top:16px;font-size:13px;color:rgba(255,255,255,0.3)}
.foot a{color:#ef4444;text-decoration:none}
</style>
</head>
<body>
<div class="box">
<h1>Aussie <span>Cheaters</span></h1>
<p class="sub">Sign in to your account</p>
<div class="err" id="err"></div>
<form id="loginForm" onsubmit="return doLogin(event)">
<label>Username</label>
<div class="input-wrapper">
<i class="fas fa-user"></i>
<input type="text" id="username" required />
</div>
<label>Password</label>
<div class="input-wrapper">
<i class="fas fa-lock"></i>
<input type="password" id="password" required />
</div>
<button class="btn" type="submit">Sign In</button>
</form>
<div class="foot">Don't have an account? <a href="/signup">Sign up</a></div>
</div>
<script>
async function doLogin(e){e.preventDefault();const u=document.getElementById('username').value.trim();const p=document.getElementById('password').value;document.querySelector('.btn').textContent='Signing in...';try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});const d=await r.json();if(d.error){document.getElementById('err').style.display='block';document.getElementById('err').textContent=d.error;document.querySelector('.btn').textContent='Sign In';return}localStorage.setItem('token',d.token);window.location.href='/dashboard'}catch(e){document.getElementById('err').style.display='block';document.getElementById('err').textContent='Connection error';document.querySelector('.btn').textContent='Sign In'}}
window.addEventListener('DOMContentLoaded',()=>{const t=localStorage.getItem('token');if(t){fetch('/api/me',{headers:{'Authorization':'Bearer '+t}}).then(r=>r.json()).then(d=>{if(d.username)window.location.href='/dashboard'}).catch(()=>{})}})
</script>
</body>
</html>"""

AUTH_SIGNUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Sign Up — Aussie Cheaters Exposed</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0b0b12;color:#e5e5e5;min-height:100vh;display:flex;align-items:center;justify-content:center}
.box{max-width:400px;width:100%;padding:40px 24px}
h1{font-size:28px;font-weight:800;margin-bottom:4px}
h1 span{color:#ef4444}
p.sub{color:rgba(255,255,255,0.3);font-size:14px;margin-bottom:24px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:#ccc}
.input-wrapper{position:relative;margin-bottom:16px}
.input-wrapper i{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:rgba(255,255,255,0.3);font-size:15px;z-index:1}
.input-wrapper input{width:100%;padding:12px 14px 12px 36px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:#0b0b12;color:#fff;font-size:15px;outline:none;margin-bottom:0}
.input-wrapper input:focus{border-color:#ef4444}
.btn{width:100%;padding:14px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff}
.btn:hover{opacity:.9}
.err{color:#f87171;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:10px;font-size:13px;margin-bottom:12px;display:none}
.foot{text-align:center;margin-top:16px;font-size:13px;color:rgba(255,255,255,0.3)}
.foot a{color:#ef4444;text-decoration:none}
</style>
</head>
<body>
<div class="box">
<h1>Aussie <span>Cheaters</span></h1>
<p class="sub">Create a free account</p>
<div class="err" id="err"></div>
<form id="signupForm" onsubmit="return doSignup(event)">
<label>Username</label>
<div class="input-wrapper">
<i class="fas fa-user"></i>
<input type="text" id="username" required />
</div>
<label>Email</label>
<div class="input-wrapper">
<i class="fas fa-envelope"></i>
<input type="email" id="email" required />
</div>
<label>Password</label>
<div class="input-wrapper">
<i class="fas fa-lock"></i>
<input type="password" id="password" required />
</div>
<button class="btn" type="submit">Create Account</button>
</form>
<div class="foot">Already have an account? <a href="/login">Sign in</a></div>
</div>
<script>
async function doSignup(e){e.preventDefault();const u=document.getElementById('username').value.trim();const em=document.getElementById('email').value.trim();const p=document.getElementById('password').value;document.querySelector('.btn').textContent='Creating...';try{const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,email:em,password:p})});const d=await r.json();if(d.error){document.getElementById('err').style.display='block';document.getElementById('err').textContent=d.error;document.querySelector('.btn').textContent='Create Account';return}localStorage.setItem('token',d.token);window.location.href='/dashboard'}catch(e){document.getElementById('err').style.display='block';document.getElementById('err').textContent='Connection error';document.querySelector('.btn').textContent='Create Account'}}
</script>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Dashboard — Aussie Cheaters Exposed</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0b0b12;color:#e5e5e5;min-height:100vh}
/* ── Nav ── */
nav{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;max-width:1200px;margin:0 auto;border-bottom:1px solid rgba(255,255,255,0.04)}
nav .logo{font-size:18px;font-weight:800}
nav .logo span{color:#ef4444}
nav .nav-right{display:flex;align-items:center;gap:12px}
nav a{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500;transition:color 0.2s;padding:6px 12px;border-radius:6px}
nav a:hover{color:#fff;background:rgba(255,255,255,0.04)}
nav .nav-btn{background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.2);padding:6px 14px}
nav .nav-btn:hover{background:rgba(239,68,68,0.2);color:#fff}
/* ── Container ── */
.container{max-width:900px;margin:0 auto;padding:32px 24px}
/* ── User Info ── */
.user-header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:24px}
.user-header h1{font-size:24px;font-weight:800;letter-spacing:-0.5px}
.user-header .sub{font-size:14px;color:rgba(255,255,255,0.3);margin-top:2px}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}
.admin-badge{background:rgba(239,68,68,0.12);color:#ef4444;border:1px solid rgba(239,68,68,0.2)}
.member-badge{background:rgba(34,197,94,0.12);color:#22c55e;border:1px solid rgba(34,197,94,0.2)}
/* ── Search Card ── */
.search-card{background:linear-gradient(135deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01));border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:24px;margin-bottom:24px}
.search-card h3{font-size:16px;font-weight:700;margin-bottom:4px}
.search-card p{font-size:13px;color:rgba(255,255,255,0.4);margin-bottom:16px}
.search-box{display:flex;gap:8px}
.search-box input{flex:1;padding:14px 16px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:#0b0b12;color:#fff;font-size:15px;outline:none;transition:border-color 0.2s}
.search-box input:focus{border-color:#ef4444}
.search-box button{padding:14px 24px;border:none;border-radius:10px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;font-weight:700;font-size:14px;cursor:pointer;transition:all 0.2s;white-space:nowrap}
.search-box button:hover{opacity:0.9}
.search-box button:disabled{opacity:0.5;cursor:not-allowed}
/* ── Summary Card ── */
.summary-card{background:linear-gradient(135deg,rgba(239,68,68,0.06),rgba(239,68,68,0.02));border:1px solid rgba(239,68,68,0.1);border-radius:16px;padding:28px;margin-bottom:24px;position:relative;overflow:hidden}
.summary-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#ef4444,#f97316,transparent)}
.summary-grid{display:grid;grid-template-columns:auto 1fr;gap:20px 24px;align-items:start}
.summary-score{text-align:center}
.summary-score .big-score{font-size:56px;font-weight:900;line-height:1;letter-spacing:-2px}
.summary-score .score-label{font-size:12px;color:rgba(255,255,255,0.3);margin-top:4px;text-transform:uppercase;letter-spacing:1px}
.summary-details{display:flex;flex-direction:column;gap:12px}
.summary-row{display:flex;justify-content:space-between;align-items:center;font-size:14px}
.summary-row .label{color:rgba(255,255,255,0.4)}
.summary-row .value{font-weight:700}
.summary-row .value.found{color:#22c55e}
.summary-row .value.miss{color:#6b7280}
.summary-row .value.blocked{color:#f59e0b}
.summary-bar{height:6px;border-radius:3px;background:rgba(255,255,255,0.06);overflow:hidden;margin:4px 0}
.summary-bar .bar-fill{height:100%;border-radius:3px;transition:width 0.8s ease}
.summary-verdict{font-size:13px;color:rgba(255,255,255,0.5);margin-top:4px}
/* ── Section Headers ── */
.section-header{display:flex;align-items:center;gap:8px;font-size:18px;font-weight:700;margin-bottom:16px;margin-top:32px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.04)}
.section-header .count{font-size:12px;font-weight:600;background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.4);padding:2px 10px;border-radius:12px;margin-left:4px}
/* ── Platform Cards Grid ── */
.platform-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-bottom:8px}
.platform-card{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:12px;padding:16px;transition:all 0.2s;position:relative;overflow:hidden}
.platform-card:hover{border-color:rgba(255,255,255,0.1);background:rgba(255,255,255,0.03);transform:translateY(-1px)}
.platform-card .card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.platform-card .platform-icon{font-size:18px;margin-right:8px}
.platform-card .platform-name{font-size:14px;font-weight:600;color:#fff}
.platform-card .status-badge{font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;white-space:nowrap}
.platform-card .status-found{background:rgba(34,197,94,0.12);color:#22c55e;border:1px solid rgba(34,197,94,0.2)}
.platform-card .status-notfound{background:rgba(107,114,128,0.12);color:#6b7280;border:1px solid rgba(107,114,128,0.2)}
.platform-card .status-blocked{background:rgba(245,158,11,0.12);color:#f59e0b;border:1px solid rgba(245,158,11,0.2)}
.platform-card .evidence{font-size:12px;color:rgba(255,255,255,0.4);line-height:1.4;margin-bottom:8px}
.platform-card .card-link{display:inline-block;font-size:12px;color:#f97316;text-decoration:none;font-weight:500}
.platform-card .card-link:hover{text-decoration:underline;color:#fb923c}
/* ── Grouped section ── */
.group-section{margin-bottom:24px}
.group-title{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.3);margin-bottom:10px;display:flex;align-items:center;gap:8px}
.group-title .g-count{font-size:11px;background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.3);padding:1px 8px;border-radius:10px}
/* ── Sherlock/Holehe Cards ── */
.osint-card{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:12px;padding:20px;margin-bottom:16px}
.osint-card h4{font-size:14px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.osint-card h4 .hint{font-size:11px;font-weight:400;color:rgba(255,255,255,0.3);margin-left:auto}
.osint-list{display:flex;flex-wrap:wrap;gap:6px}
.osint-tag{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;font-size:12px;transition:all 0.15s}
.osint-tag:hover{background:rgba(249,115,22,0.08);border-color:rgba(249,115,22,0.2)}
.osint-tag a{color:#f97316;text-decoration:none}
.osint-tag a:hover{text-decoration:underline}
.osint-tag .status-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.osint-tag .regd{background:#22c55e}
.osint-tag .noreg{background:#6b7280}
.osint-tag .unknown{background:#f59e0b}
/* ── Activity Timeline ── */
.timeline{position:relative;padding-left:28px;margin-top:8px}
.timeline::before{content:'';position:absolute;left:8px;top:4px;bottom:4px;width:1.5px;background:rgba(239,68,68,0.2)}
.timeline-item{position:relative;padding-bottom:16px}
.timeline-item:last-child{padding-bottom:0}
.timeline-item .dot{position:absolute;left:-24px;top:4px;width:10px;height:10px;border-radius:50%;border:2px solid rgba(239,68,68,0.3);background:#0b0b12}
.timeline-item .dot.active{border-color:#ef4444;background:#ef4444;box-shadow:0 0 8px rgba(239,68,68,0.3)}
.timeline-item .date{font-size:12px;color:rgba(255,255,255,0.3);margin-bottom:2px}
.timeline-item .event{font-size:13px;color:rgba(255,255,255,0.7)}
.timeline-item .platform-tag{font-size:11px;color:#f97316}
/* ── Settings Card ── */
.settings-card{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:24px;max-width:500px;margin:0 auto}
.settings-card h3{font-size:16px;font-weight:700;margin-bottom:16px}
.settings-card label{display:block;font-size:13px;font-weight:600;color:#ccc;margin-top:14px;margin-bottom:6px}
.settings-card input{width:100%;padding:12px 14px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:#0b0b12;color:#fff;font-size:14px;outline:none}
.settings-card input:focus{border-color:#ef4444}
.settings-card .settings-msg{font-size:13px;margin-bottom:8px}
.settings-card button{margin-top:16px;padding:12px 24px;border:none;border-radius:8px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;font-weight:700;cursor:pointer;font-size:14px;transition:opacity 0.2s}
.settings-card button:hover{opacity:0.9}
.settings-card .back-btn{background:transparent;color:rgba(255,255,255,0.4);padding:8px 0;margin-top:8px}
.settings-card .back-btn:hover{color:#fff}
/* ── Error / Loading ── */
.error-box{color:#f87171;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:16px;font-size:14px;margin-bottom:16px}
.loading-box{text-align:center;padding:40px 20px;color:rgba(255,255,255,0.3);font-size:14px}
.loading-spinner{display:inline-block;width:32px;height:32px;border:3px solid rgba(239,68,68,0.1);border-top-color:#ef4444;border-radius:50%;animation:spin 0.8s linear infinite;margin-bottom:12px}
@keyframes spin{to{transform:rotate(360deg)}}
/* ── FAQ Card ── */
.faq-card{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:24px;max-width:700px;margin:0 auto}
.faq-card h3{font-size:16px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.faq-card h3 span{color:#ef4444}
.faq-item{border-bottom:1px solid rgba(255,255,255,0.04);padding:14px 0}
.faq-item:last-child{border-bottom:none}
.faq-q{font-size:14px;font-weight:600;color:#fff;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none}
.faq-q:hover{color:#ef4444}
.faq-q .faq-toggle{font-size:12px;color:rgba(255,255,255,0.3);transition:transform 0.2s}
.faq-q.open .faq-toggle{transform:rotate(180deg)}
.faq-a{font-size:13px;color:rgba(255,255,255,0.5);line-height:1.6;margin-top:10px;display:none;padding-right:20px}
.faq-a.open{display:block}
.faq-back{display:inline-block;margin-top:16px;font-size:13px;color:rgba(255,255,255,0.3);cursor:pointer;text-decoration:none}
.faq-back:hover{color:#ef4444}
/* ── Responsive ── */
@media(max-width:768px){
  .container{padding:20px 16px}
  .summary-grid{grid-template-columns:1fr;gap:16px}
  .summary-score .big-score{font-size:42px}
  .platform-grid{grid-template-columns:1fr}
  .user-header{flex-direction:column;align-items:flex-start}
  .search-box{flex-direction:column}
  .search-box button{width:100%}
  nav .nav-right{gap:6px}
  nav a{font-size:12px;padding:5px 8px}
  .osint-list{flex-direction:column}
}
@media(max-width:480px){
  .summary-score .big-score{font-size:36px}
  .section-header{font-size:16px}
  .platform-card{padding:14px}
  .search-card{padding:18px}
}
</style>
</head>
<body>

<nav>
<div class="logo">\U0001f494 Aussie <span>Cheaters</span></div>
<div class="nav-right">
<a href="#" id="faqBtn" onclick="showFAQ()">❓ FAQ</a>
<a href="#" id="settingsBtn" onclick="showSettings()">⚙️ Settings</a>
<a href="#" id="historyBtn" onclick="showHistory()">📋 History</a>
<a href="#" class="nav-btn" id="logoutBtn" onclick="logout()">🔪 Logout</a>
</div>
</nav>

<div class="container">
<div id="userInfo"></div>
<div id="searchSection"></div>
<div id="results"></div>
</div>

<script>
let currentUser = null;

window.addEventListener('DOMContentLoaded', async () => {
  const token = localStorage.getItem('token');
  if (!token) { window.location.href = '/login'; return; }
  try {
    const r = await fetch('/api/me', { headers: { 'Authorization': 'Bearer ' + token } });
    const d = await r.json();
    if (d.error) { localStorage.removeItem('token'); window.location.href = '/login'; return; }
    currentUser = d;
    renderDashboard(d);
  } catch(e) { localStorage.removeItem('token'); window.location.href = '/login'; }
});

function renderDashboard(u) {
  const isAdmin = u.role === 'admin';
  document.getElementById('userInfo').innerHTML = `
    <div class="user-header">
      <div>
        <h1>G'day, ${u.username}! <span class="badge ${isAdmin ? 'admin-badge' : 'member-badge'}">${isAdmin ? '\U0001f451 Admin' : '\u2705 Subscriber'}</span></h1>
        <div class="sub">OSINT Investigation Dashboard</div>
      </div>
    </div>
  `;
  document.getElementById('searchSection').innerHTML = `
    <div class="search-card">
      <h3>\U0001f50d OSINT Scan</h3>
      <p>Enter email, username, or phone number to scan across ${isAdmin ? 'all' : '12'} platforms.</p>
      <div class="search-box">
        <input type="text" id="searchInput" placeholder="e.g. johnno84 or johnno@bigpond.com" onkeydown="if(event.key==='Enter')doSearch()" />
        <button onclick="doSearch()" id="searchBtn">\U0001f50e Search Targets</button>
      </div>
    </div>
  `;
}

async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const r = document.getElementById('results');
  const btn = document.getElementById('searchBtn');
  btn.disabled = true;
  btn.textContent = '\U0001f998 Scanning...';
  r.innerHTML = '<div class="loading-box"><div class="loading-spinner"></div><div>Running OSINT scan across platforms...</div></div>';
  const token = localStorage.getItem('token');
  try {
    const resp = await fetch('/scan?username=' + encodeURIComponent(q) + '&admin_token=' + encodeURIComponent(token));
    const data = await resp.json();
    if (!resp.ok) { r.innerHTML = '<div class="error-box">\u274c ' + (data.detail || 'Error') + '</div>'; return; }
    renderFullResults(data);
  } catch(e) { r.innerHTML = '<div class="error-box">\u274c ' + e.message + '</div>'; }
  btn.disabled = false;
  btn.textContent = '\U0001f50e Search Targets';
}

function getEmojiForPlatform(platform) {
  const map = {
    'telegram': '\U0001f4ac', 'snapchat': '\U0001f47b', 'instagram': '\U0001f4f8',
    'tiktok': '\U0001f3a7', 'x': '\U0001f426', 'twitter': '\U0001f426',
    'redhotpie': '\u2764\ufe0f', 'adultfriendfinder': '\U0001f525',
    'rsvp': '\U0001f495', 'pof': '\U0001f3a3', 'plentyoffish': '\U0001f3a3',
    'onlyfans': '\U0001f51e', 'fetlife': '\U0001f517',
    'okcupid': '\U0001f498', 'facebook': '\U0001f464'
  };
  return map[platform.toLowerCase()] || '\U0001f310';
}

function renderFullResults(data) {
  let html = '';

  // ── Collect data ──
  let summary = null;
  let platforms = [];
  let enrichmentItems = [];
  let timelineItems = [];

  for (const item of data) {
    if (item.type === 'summary') {
      summary = item.summary;
    } else if (item.platform) {
      if (item.platform === 'sherlock' || item.platform === 'holehe' || item.platform === 'telegram_profile' || item.platform === 'x_profile') {
        enrichmentItems.push(item);
      } else {
        platforms.push(item);
      }
      // Collect dates for timeline
      if (item.lastActive || item.createdDate || item.lastSeen) {
        timelineItems.push({
          platform: item.platformLabel || item.platform,
          date: item.lastActive || item.createdDate || item.lastSeen,
          detail: item.evidence || 'Profile activity detected'
        });
      }
    }
  }

  // ── Summary Card ──
  if (summary) {
    const { profilesFound: found, platformsChecked: total, score: pct } = summary;
    const missing = total - found;
    const color = pct > 50 ? '#ef4444' : pct > 0 ? '#f59e0b' : '#22c55e';
    const verdict = pct > 75 ? '\U0001f6a8 High Risk \u2014 Significant digital footprint detected' :
                    pct > 50 ? '\U0001f6a9 Moderate Risk \u2014 Multiple profiles found' :
                    pct > 0  ? '\u26a0\ufe0f Low Risk \u2014 Some activity detected' :
                               '\u2705 Clean \u2014 No profiles detected across scanned platforms';
    const blocked = platforms.filter(p => p.error).length;

    html += '<div class="summary-card">';
    html += '<div class="summary-grid">';
    html += '<div class="summary-score">';
    html += '<div class="big-score" style="color:' + color + '">' + Math.round(pct) + '<span style="font-size:24px;color:rgba(255,255,255,0.2)">%</span></div>';
    html += '<div class="score-label">OSINT Score</div>';
    html += '</div>';
    html += '<div class="summary-details">';
    html += '<div class="summary-row"><span class="label">Platforms Scanned</span><span class="value" style="color:rgba(255,255,255,0.6)">' + total + '</span></div>';
    html += '<div class="summary-row"><span class="label">\u2705 Profiles Found</span><span class="value found">' + found + '</span></div>';
    html += '<div class="summary-row"><span class="label">\u274c Not Found</span><span class="value miss">' + missing + '</span></div>';
    html += '<div class="summary-row"><span class="label">\u26a0\ufe0f Blocked / Error</span><span class="value blocked">' + blocked + '</span></div>';
    html += '<div class="summary-bar"><div class="bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div>';
    html += '<div class="summary-verdict" style="color:' + color + '">' + verdict + '</div>';
    html += '</div></div></div>';
  }

  // ── Group platform results ──
  const foundPlats = platforms.filter(p => p.profileFound);
  const notFoundPlats = platforms.filter(p => !p.profileFound && !p.error);
  const blockedPlats = platforms.filter(p => p.error);

  // Found section
  if (foundPlats.length > 0) {
    html += '<div class="section-header">\u2705 Profiles Found <span class="count">' + foundPlats.length + '</span></div>';
    html += '<div class="platform-grid">';
    for (const item of foundPlats) {
      const emoji = getEmojiForPlatform(item.platform);
      html += '<div class="platform-card">';
      html += '<div class="card-top">';
      html += '<div><span class="platform-icon">' + emoji + '</span><span class="platform-name">' + item.platformLabel + '</span></div>';
      html += '<span class="status-badge status-found">\u2705 Found</span>';
      html += '</div>';
      if (item.evidence) html += '<div class="evidence">' + item.evidence + '</div>';
      if (item.profileUrl) html += '<a href="' + item.profileUrl + '" target="_blank" class="card-link">\U0001f517 View Profile \u2192</a>';
      html += '</div>';
    }
    html += '</div>';
  }

  // Not Found section
  if (notFoundPlats.length > 0) {
    html += '<div class="section-header" style="margin-top:20px">\u274c Not Found <span class="count">' + notFoundPlats.length + '</span></div>';
    html += '<div class="platform-grid">';
    for (const item of notFoundPlats) {
      const emoji = getEmojiForPlatform(item.platform);
      html += '<div class="platform-card">';
      html += '<div class="card-top">';
      html += '<div><span class="platform-icon">' + emoji + '</span><span class="platform-name">' + item.platformLabel + '</span></div>';
      html += '<span class="status-badge status-notfound">\u274c Not Found</span>';
      html += '</div>';
      if (item.evidence) html += '<div class="evidence">' + item.evidence + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  // Blocked section
  if (blockedPlats.length > 0) {
    html += '<div class="section-header" style="margin-top:20px">\u26a0\ufe0f Blocked / Error <span class="count">' + blockedPlats.length + '</span></div>';
    html += '<div class="platform-grid">';
    for (const item of blockedPlats) {
      const emoji = getEmojiForPlatform(item.platform);
      html += '<div class="platform-card">';
      html += '<div class="card-top">';
      html += '<div><span class="platform-icon">' + emoji + '</span><span class="platform-name">' + item.platformLabel + '</span></div>';
      html += '<span class="status-badge status-blocked">\u26a0\ufe0f Blocked</span>';
      html += '</div>';
      if (item.evidence) html += '<div class="evidence">' + item.evidence + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  // ── Sherlock: Linked Accounts ──
  const sherlock = enrichmentItems.find(i => i.platform === 'sherlock');
  if (sherlock && sherlock.sherlock_sites_found && sherlock.sherlock_sites_found.length > 0) {
    html += '<div class="section-header">\U0001f517 Linked Accounts (Sherlock) <span class="count">' + sherlock.sherlock_sites_found.length + '</span></div>';
    html += '<div class="osint-card">';
    html += '<h4>\U0001f50d Discovered Accounts <span class="hint">Click to open profile</span></h4>';
    html += '<div class="osint-list">';
    for (const site of sherlock.sherlock_sites_found.slice(0, 30)) {
      html += '<span class="osint-tag"><span class="status-dot regd"></span><a href="' + site.url + '" target="_blank">' + site.name + '</a></span>';
    }
    if (sherlock.sherlock_sites_found.length > 30) {
      html += '<span class="osint-tag" style="color:rgba(255,255,255,0.3);border-style:dashed">+' + (sherlock.sherlock_sites_found.length - 30) + ' more</span>';
    }
    html += '</div></div>';
  }

  // ── Holehe: Email Registrations ──
  const holehe = enrichmentItems.find(i => i.platform === 'holehe');
  if (holehe && holehe.holehe_sites_found && holehe.holehe_sites_found.length > 0) {
    html += '<div class="section-header">\U0001f4e7 Email Registrations (Holehe) <span class="count">' + holehe.holehe_sites_found.length + '</span></div>';
    html += '<div class="osint-card">';
    html += '<h4>\U0001f4cb Email-to-Account Mappings <span class="hint">Registered accounts</span></h4>';
    html += '<div class="osint-list">';
    for (const site of holehe.holehe_sites_found) {
      html += '<span class="osint-tag"><span class="status-dot regd"></span>' + site + '</span>';
    }
    html += '</div></div>';
  }

  // ── EmailRep.io: Reputation & Breaches ──
  const emailrep = enrichmentItems.find(i => i.platform === 'emailrep');
  if (emailrep && emailrep.emailrep_reputation) {
    const repColor = emailrep.emailrep_reputation === 'high' ? '#ef4444' : emailrep.emailrep_reputation === 'medium' ? '#f59e0b' : '#22c55e';
    html += '<div class="section-header">📧 Email Reputation (EmailRep.io)</div>';
    html += '<div class="osint-card">';
    html += '<h4>🔍 Reputation: <span style="color:' + repColor + ';font-weight:800;text-transform:uppercase">' + emailrep.emailrep_reputation + '</span> <span class="hint">emailrep.io</span></h4>';
    if (emailrep.emailrep_breaches && emailrep.emailrep_breaches.length > 0) {
      html += '<div style="font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:8px">⚠️ Known breaches:</div>';
      html += '<div class="osint-list">';
      for (const breach of emailrep.emailrep_breaches.slice(0, 15)) {
        html += '<span class="osint-tag"><span class="status-dot regd"></span>' + breach + '</span>';
      }
      if (emailrep.emailrep_breaches.length > 15) {
        html += '<span class="osint-tag" style="color:rgba(255,255,255,0.3);border-style:dashed">+' + (emailrep.emailrep_breaches.length - 15) + ' more</span>';
      }
      html += '</div>';
    }
    if (emailrep.emailrep_socials && emailrep.emailrep_socials.length > 0) {
      html += '<div style="font-size:13px;color:rgba(255,255,255,0.5);margin-top:10px;margin-bottom:8px">🌐 Social media profiles:</div>';
      html += '<div class="osint-list">';
      for (const social of emailrep.emailrep_socials.slice(0, 10)) {
        html += '<span class="osint-tag"><span class="status-dot regd"></span>' + social + '</span>';
      }
      if (emailrep.emailrep_socials.length > 10) {
        html += '<span class="osint-tag" style="color:rgba(255,255,255,0.3);border-style:dashed">+' + (emailrep.emailrep_socials.length - 10) + ' more</span>';
      }
      html += '</div>';
    }
    if ((!emailrep.emailrep_breaches || emailrep.emailrep_breaches.length === 0) && (!emailrep.emailrep_socials || emailrep.emailrep_socials.length === 0)) {
      html += '<div style="font-size:13px;color:rgba(255,255,255,0.4)">No breaches or social media profiles found for this email.</div>';
    }
    html += '</div>';
  }

  // ── Enriched Profiles (Telegram, X) ──
  const enrichedProfiles = enrichmentItems.filter(i => i.platform === 'telegram_profile' || i.platform === 'x_profile');
  if (enrichedProfiles.length > 0) {
    html += '<div class="section-header">\U0001f464 Enriched Profile Data <span class="count">' + enrichedProfiles.length + '</span></div>';
    for (const item of enrichedProfiles) {
      const pd = item.profileData || {};
      const isTelegram = item.platform === 'telegram_profile';
      const profileUrl = isTelegram ? 'https://t.me/' + item.username : 'https://x.com/' + item.username;
      html += '<div class="osint-card" style="display:flex;align-items:center;gap:14px;padding:16px 20px">';
      if (pd.photo_url) {
        html += '<img src="' + pd.photo_url + '" style="width:48px;height:48px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid rgba(239,68,68,0.15)" alt="photo" />';
      } else {
        html += '<div style="width:48px;height:48px;border-radius:50%;background:rgba(239,68,68,0.1);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0">' + (isTelegram ? '\U0001f4ac' : '\U0001f426') + '</div>';
      }
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-weight:600;font-size:15px;color:#fff">' + (pd.name || (isTelegram ? 'Telegram' : 'X / Twitter')) + '</div>';
      if (pd.bio) html += '<div style="font-size:12px;color:rgba(255,255,255,0.4);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + pd.bio.substring(0, 120) + '</div>';
      html += '<a href="' + profileUrl + '" target="_blank" style="font-size:12px;color:#f97316;text-decoration:none;margin-top:4px;display:inline-block">' + profileUrl + ' \u2197</a>';
      html += '</div></div>';
    }
  }

  // ── Activity Timeline ──
  if (timelineItems.length > 0) {
    html += '<div class="section-header">\U0001f4c5 Activity Timeline <span class="count">' + timelineItems.length + '</span></div>';
    html += '<div class="osint-card">';
    html += '<div class="timeline">';
    // Sort by date descending
    timelineItems.sort((a, b) => new Date(b.date) - new Date(a.date));
    for (const t of timelineItems) {
      html += '<div class="timeline-item">';
      html += '<div class="dot active"></div>';
      html += '<div class="date">' + t.date + '</div>';
      html += '<div class="event">' + t.detail + ' <span class="platform-tag">\u2014 ' + t.platform + '</span></div>';
      html += '</div>';
    }
    html += '</div></div>';
  }

  // ── No results fallback ──
  if (!summary && platforms.length === 0 && enrichmentItems.length === 0) {
    html += '<div class="error-box">\u26a0\ufe0f No results returned. The scan may have encountered an issue.</div>';
  }

  document.getElementById('results').innerHTML = html;
}

function showSettings() {
  const r = document.getElementById('results');
  r.innerHTML = `
    <div class="settings-card">
      <h3>\u2699\ufe0f Account Settings</h3>
      <div id="settingsMsg"></div>
      <label>Current Password</label>
      <input type="password" id="curPw" />
      <label>New Password</label>
      <input type="password" id="newPw" />
      <button onclick="changePw()">Change Password</button>
      <button onclick="document.getElementById('results').innerHTML=''" class="back-btn">\u2190 Back to Dashboard</button>
    </div>
  `;
}

async function changePw() {
  const cur = document.getElementById('curPw').value;
  const newPw = document.getElementById('newPw').value;
  if (!cur || !newPw) { document.getElementById('settingsMsg').innerHTML = '<div class="settings-msg" style="color:#f87171;">Both fields required</div>'; return; }
  if (newPw.length < 4) { document.getElementById('settingsMsg').innerHTML = '<div class="settings-msg" style="color:#f87171;">New password must be 4+</div>'; return; }
  const token = localStorage.getItem('token');
  try {
    const r = await fetch('/api/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }, body: JSON.stringify({ current_password: cur, new_password: newPw }) });
    const d = await r.json();
    if (d.error) { document.getElementById('settingsMsg').innerHTML = '<div class="settings-msg" style="color:#f87171;">' + d.error + '</div>'; return; }
    document.getElementById('settingsMsg').innerHTML = '<div class="settings-msg" style="color:#22c55e;">\u2705 Password changed successfully</div>';
    document.getElementById('curPw').value = ''; document.getElementById('newPw').value = '';
  } catch(e) { document.getElementById('settingsMsg').innerHTML = '<div class="settings-msg" style="color:#f87171;">Connection error</div>'; }
}

function showFAQ() {
  const r = document.getElementById('results');
  r.innerHTML = `
    <div class="faq-card">
      <h3>❓ Frequently Asked <span>Questions</span></h3>
      <div class="faq-item">
        <div class="faq-q" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
          What does the OSINT score mean?
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">The OSINT score (0–100%) reflects how many platforms returned a profile match for the searched username or email. A higher score means a larger digital footprint — more accounts found across dating sites, social media, and messaging apps.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
          Which platforms are scanned?
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">We scan 12+ Australian and international platforms including Snapchat, Instagram, Telegram, TikTok, X/Twitter, RedHotPie, AdultFriendFinder, RSVP, OKCupid, Plenty of Fish, OnlyFans, and FetLife. Username searches also run through Sherlock (400+ sites) and Maigret (3000+ sites). Email searches use Holehe and EmailRep.io for breach and registration data.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
          How accurate are the results?
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">Results are based on real-time HTTP status checks and content analysis of each platform's profile page. Some sites block automated requests (shown as "Blocked"), which reduces coverage. A "Not Found" result means no profile was detected, but it's possible a user exists under a different username or has privacy settings that hide their profile.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
          Is my search private?
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">Yes. Searches are authenticated per-user and results are only visible to you while logged in. We do not share, log, or store search queries beyond what's needed to deliver results. Your account password is hashed and we use JWT tokens for session management.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
          What's the difference between a free preview and a full scan?
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">A free preview checks Snapchat and Instagram only. A full scan checks all 12+ platforms, runs Sherlock/Maigret for username OSINT, checks email registrations via Holehe and EmailRep.io, and scrapes enriched profile data from Telegram and X/Twitter. Full scans are available to subscribers.</div>
      </div>
      <a href="#" onclick="document.getElementById('results').innerHTML=''" class="faq-back">← Back to Dashboard</a>
    </div>
  `;
}

function logout() { localStorage.removeItem('token'); window.location.href = '/login'; }

function showHistory() {
  const tk = localStorage.getItem('token');
  if (!tk) return;
  // Get username from the greeting element
  const greeting = document.querySelector('h1');
  const uname = greeting ? greeting.textContent.replace(/[^a-zA-Z0-9_-]/g, '') : '';
  const r = document.getElementById('results');
  r.innerHTML = '<div class="card" style="padding:2rem"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem"><h3 style="margin:0">📋 Scan History</h3><a href="/api/history/download" style="background:#ef4444;color:#fff;padding:0.5rem 1rem;border-radius:6px;text-decoration:none;font-size:0.85rem" onclick="event.preventDefault();fetch(\'/api/history/download\',{headers:{\'Authorization\':\'Bearer \'+localStorage.getItem(\'token\')}}).then(r=>r.blob()).then(b=>{const a=document.createElement(\'a\');a.href=URL.createObjectURL(b);a.download=\'scan_history.json\';a.click()})">⬇️ Download</a></div><div id="historyList"><p style="text-align:center;padding:2rem;color:#888">Loading...</p></div></div>';
  fetch('/api/history', { headers: { 'Authorization': 'Bearer ' + tk } })
    .then(res => res.json())
    .then(data => {
      let html = '';
      const entries = data[uname] || [];
      if (entries.length === 0) {
        html = '<p style="text-align:center;padding:2rem;color:#888">No scans yet</p>';
      } else {
        html = '<table style="width:100%;border-collapse:collapse"><tr style="border-bottom:1px solid #333;color:#888;font-size:0.85rem"><th style="padding:0.75rem 0.5rem;text-align:left">Date</th><th style="padding:0.75rem 0.5rem;text-align:left">Query</th><th style="padding:0.75rem 0.5rem;text-align:center">Score</th><th style="padding:0.75rem 0.5rem;text-align:center">Found</th></tr>';
        entries.forEach(e => {
          const d = new Date(e.timestamp);
          const ds = d.toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'2-digit'})+' '+d.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'});
          const sc = e.osint_score !== null ? e.osint_score+'%' : '—';
          const fd = e.total_found+'/'+e.total_platforms;
          html += '<tr style="border-bottom:1px solid #222"><td style="padding:0.75rem 0.5rem;color:#aaa;font-size:0.85rem">'+ds+'</td><td style="padding:0.75rem 0.5rem;font-weight:600">'+e.query+'</td><td style="padding:0.75rem 0.5rem;text-align:center;color:'+(e.osint_score>=50?'#ef4444':'#eab308')+';font-weight:700">'+sc+'</td><td style="padding:0.75rem 0.5rem;text-align:center;color:#22c55e">'+fd+'</td></tr>';
        });
        html += '</table>';
      }
      document.getElementById('historyList').innerHTML = html;
    })
    .catch(() => {
      document.getElementById('historyList').innerHTML = '<p style="text-align:center;padding:2rem;color:#ef4444">Failed to load history</p>';
    });
}
</script>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return AUTH_LOGIN_HTML


@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    return AUTH_SIGNUP_HTML


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return DASHBOARD_HTML


@app.post("/api/signup")
async def api_signup(body: dict = None):
    body = body or {}
    username = (body.get("username") or "").strip().lower()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")
    if not username or not password or not email:
        return JSONResponse({"error": "All fields required"}, 400)
    if len(username) < 3 or len(password) < 4:
        return JSONResponse({"error": "Username (3+) and password (4+)"}, 400)
    users = _load_users()
    if username in users:
        return JSONResponse({"error": "Username taken"}, 409)
    users[username] = {
        "password": _hash_password(password),
        "email": email,
        "role": "user",
        "created": time.time(),
    }
    _save_users(users)
    token = _make_token(username)
    return {"token": token, "username": username, "role": "user"}


@app.post("/api/login")
async def api_login(body: dict = None):
    body = body or {}
    username = (body.get("username") or "").strip().lower()
    password = body.get("password", "")
    users = _load_users()
    user = users.get(username)
    if not user or user["password"] != _hash_password(password):
        return JSONResponse({"error": "Invalid username or password"}, 401)
    token = _make_token(username)
    return {"token": token, "username": username, "role": user.get("role", "user")}


@app.post("/api/change-password")
async def api_change_password(request: Request, body: dict = None):
    body = body or {}
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"error": "Not authenticated"}, 401)
    username = _verify_token(auth[7:])
    if not username:
        return JSONResponse({"error": "Invalid token"}, 401)
    users = _load_users()
    user = users.get(username)
    if not user:
        return JSONResponse({"error": "User not found"}, 404)
    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")
    if user["password"] != _hash_password(current_password):
        return JSONResponse({"error": "Current password is wrong"}, 403)
    if len(new_password) < 4:
        return JSONResponse({"error": "New password must be 4+ characters"}, 400)
    user["password"] = _hash_password(new_password)
    _save_users(users)
    return {"status": "ok"}


@app.get("/api/me")
async def api_me(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"error": "Not authenticated"}, 401)
    username = _verify_token(auth[7:])
    if not username:
        return JSONResponse({"error": "Invalid token"}, 401)
    users = _load_users()
    user = users.get(username)
    if not user:
        return JSONResponse({"error": "User not found"}, 404)
    return {"username": username, "role": user.get("role", "user"), "email": user.get("email", "")}


@app.post("/create-checkout-session")
@limiter.limit("10/hour")
async def create_checkout(request: Request, body: dict = None):
    """Create a Stripe Checkout session for $13 full scan."""
    body = body or {}
    username = (body.get("username") or "").strip()
    if not username:
        raise HTTPException(422, "username is required")

    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        # Demo mode — skip payment, return a mock session
        return {"url": f"{BASE_URL}/scan?username={username}&demo=1"}

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{BASE_URL}/?username={username}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")


@app.post("/create-subscription")
@limiter.limit("10/hour")
async def create_subscription(request: Request, body: dict = None):
    body = body or {}
    plan = body.get("plan", "3m")

    price_id = ""
    if plan == "1m":
        price_id = STRIPE_PRICE_1M
    elif plan == "3m":
        price_id = STRIPE_PRICE_3M
    elif plan == "6m":
        price_id = STRIPE_PRICE_6M

    if not STRIPE_SECRET_KEY or not price_id:
        return {"url": f"{BASE_URL}/?subscribed=demo"}

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{BASE_URL}/?subscribed=true&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/pricing",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")


@app.post("/create-checkout-onetime")
@limiter.limit("10/hour")
async def create_checkout_onetime(request: Request, body: dict = None):
    """Create a Stripe Checkout session for one-time $19.99 search."""
    body = body or {}
    username = (body.get("username") or "").strip()
    test = body.get("test", False)
    if not username:
        raise HTTPException(422, "username is required")

    if test or not STRIPE_SECRET_KEY or not STRIPE_PRICE_OT:
        return {"url": f"{BASE_URL}/?username={username}&demo=1"}

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_OT, "quantity": 1}],
            success_url=f"{BASE_URL}/?username={username}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/pricing",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    whsec = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if whsec:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, whsec)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid signature")
    else:
        event = json.loads(payload)

    event_type = event.get("type", "")

    if event_type in ("checkout.session.completed", "invoice.paid"):
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email") or session.get("customer_email", "")
        subscription_id = session.get("subscription")
        if customer_email and subscription_id:
            subs = _load_subs()
            subs[customer_email] = subscription_id
            _save_subs(subs)

    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub = event["data"]["object"]
        sub_id = sub.get("id", "")
        status = sub.get("status", "")
        subs = _load_subs()
        for email, sid in list(subs.items()):
            if sid == sub_id and status in ("canceled", "incomplete_expired", "unpaid"):
                del subs[email]
                _save_subs(subs)
                break

    return {"status": "ok"}


@app.get("/scan")
@limiter.limit("10/hour")
async def do_scan(
    request: Request,
    username: str = Query(None),
    session_id: str = Query(None),
    demo: str = Query(None),
    preview: str = Query(None),
    admin_token: str = Query(None),
    platforms: str = Query(None),
):
    """Run the scan.

    preview=true: returns 2 free results
    admin_token: bypasses payment for admin users
    paid: returns all results
    """
    if not username:
        raise HTTPException(422, "username is required")

    # Admin bypass
    is_admin = False
    if admin_token:
        admin_user = _verify_token(admin_token)
        if admin_user:
            users = _load_users()
            if users.get(admin_user, {}).get("role") == "admin":
                is_admin = True

    # Verify payment (skip for demo, preview, or admin)
    if not demo and not preview and not is_admin:
        if session_id and STRIPE_SECRET_KEY:
            try:
                sess = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
                # Check if it's a one-time payment OR an active subscription
                if sess.mode == "payment" and sess.payment_status == "paid":
                    pass  # OK
                elif sess.mode == "subscription" and sess.subscription:
                    sub_id = sess.subscription if isinstance(sess.subscription, str) else sess.subscription.get("id", "")
                    if sub_id:
                        sub = stripe.Subscription.retrieve(sub_id)
                        if sub.status in ("active", "trialing", "past_due"):
                            pass  # OK
                        else:
                            raise HTTPException(402, "subscription not active")
                    else:
                        raise HTTPException(402, "no subscription id")
                else:
                    raise HTTPException(402, "payment required")
            except stripe.error.StripeError as e:
                raise HTTPException(402, f"payment verification failed: {e}")
        else:
            if not STRIPE_PRICE_ID and not STRIPE_PRICE_1M:
                raise HTTPException(402, "payment required")

    platform_list = platforms.split(",") if platforms else None

    results = await scan_all(
        username,
        platforms=platform_list,
        proxy_url=None,  # No proxy for self-hosted
        limit_per_host=1,
        timeout=150,
        skip_enrichment=bool(preview),
    )

    # Preview mode: return 2 specific free results
    if preview:
        snapchat_result = None
        instagram_result = None
        for r in results:
            if isinstance(r, dict):
                if r.get("platform") == "snapchat":
                    snapchat_result = r
                elif r.get("platform") == "instagram":
                    instagram_result = r
        preview_results = []
        for pr in [snapchat_result, instagram_result]:
            if pr:
                pr["locked"] = False
                preview_results.append(pr)
        return {
            "preview": True,
            "total_platforms": len([r for r in results if isinstance(r, dict) and r.get("platform")]),
            "results": preview_results,
        }

    # Auto-save to history
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and not preview:
        user = _verify_token(auth[7:])
        if user:
            _add_to_history(user, username, results, preview=False)

    return results


# ── History System ─────────────────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.json")


def _load_history() -> dict:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_history(data: dict):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _add_to_history(username: str, query: str, results: list, preview: bool = False):
    """Store a scan in the history."""
    history = _load_history()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "is_preview": preview,
        "total_found": len([r for r in results if isinstance(r, dict) and r.get("profileFound")]),
        "total_platforms": len([r for r in results if isinstance(r, dict) and r.get("platform")]),
        "osint_score": next((r.get("summary", {}).get("score") for r in results if isinstance(r, dict) and r.get("type") == "summary"), None),
    }
    if username not in history:
        history[username] = []
    history[username].insert(0, entry)
    # Keep last 50 per user
    history[username] = history[username][:50]
    _save_history(history)


@app.post("/api/history/save")
async def api_history_save(request: Request, body: dict = None):
    body = body or {}
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"error": "Not authenticated"}, 401)
    username = _verify_token(auth[7:])
    if not username:
        return JSONResponse({"error": "Invalid token"}, 401)

    query = body.get("query", "")
    results = body.get("results", [])
    preview = body.get("preview", False)
    _add_to_history(username, query, results, preview)
    return {"ok": True}


@app.get("/api/history")
async def api_history(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("auth_token")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, 401)
    username = _verify_token(token)
    if not username:
        return JSONResponse({"error": "Invalid token"}, 401)

    history = _load_history()
    users = _load_users()
    user = users.get(username, {})
    is_admin = user.get("role") == "admin"

    if is_admin:
        return history  # admin sees all
    return {username: history.get(username, [])}


REPORTS_DIR = "/root/reports"


@app.get("/api/history/download")
async def api_history_download(request: Request):
    """Download scan history as a JSON file."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("auth_token")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, 401)
    username = _verify_token(token)
    if not username:
        return JSONResponse({"error": "Invalid token"}, 401)

    history = _load_history()
    users = _load_users()
    user = users.get(username, {})
    is_admin = user.get("role") == "admin"

    if is_admin:
        data = history
    else:
        data = {username: history.get(username, [])}

    # Save to reports dir and return as download
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", username)
    filepath = os.path.join(REPORTS_DIR, f"{safe}_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return FileResponse(filepath, media_type="application/json", filename=f"scan_history_{safe}.json")


# ── Run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)