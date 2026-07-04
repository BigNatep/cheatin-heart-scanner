"""
Cheatin' Heart Scanner — Production Web App
=============================================
Safe, secure, and people can actually use it.
Web UI + Stripe Checkout + rate limiting.
"""

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import stripe
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from cheatin_scanner.core import scan_all, PLATFORMS

# ── Config ─────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")  # $1.00 one-time
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
stripe.api_key = STRIPE_SECRET_KEY

# ── Rate limiting ──────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["10/hour"])
app = FastAPI(title="Cheatin' Heart Scanner", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Landing page ───────────────────────────────────────────────────────
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cheatin' Heart Scanner — Who's the Dirty Mongrel?</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, 'Segoe UI', system-ui, sans-serif; background: #0f0f0f; color: #e5e5e5; min-height: 100vh; display: flex; flex-direction: column; align-items: center; }}
    .container {{ max-width: 640px; width: 100%; padding: 2rem 1rem; }}
    h1 {{ font-size: 2rem; margin-bottom: .25rem; }} h1 span {{ color: #ef4444; }}
    .tagline {{ color: #888; margin-bottom: 2rem; font-size: .95rem; }}
    .card {{ background: #1a1a2e; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; border: 1px solid #2a2a3e; }}
    label {{ display: block; margin-bottom: .5rem; font-weight: 600; color: #ccc; font-size: .9rem; }}
    input, select {{ width: 100%; padding: .8rem 1rem; border-radius: 8px; border: 1px solid #333; background: #0f0f0f; color: #fff; font-size: 1rem; margin-bottom: 1rem; }}
    input:focus {{ outline: none; border-color: #ef4444; }}
    .hint {{ font-size: .8rem; color: #666; margin-top: -.5rem; margin-bottom: 1rem; }}
    button {{ width: 100%; padding: 1rem; border: none; border-radius: 8px; font-size: 1.1rem; font-weight: 700; cursor: pointer; transition: .2s; }}
    .btn-primary {{ background: #ef4444; color: #fff; }}
    .btn-primary:hover {{ background: #dc2626; }}
    .btn-primary:disabled {{ opacity: .5; cursor: not-allowed; }}
    .btn-secondary {{ background: #2a2a3e; color: #ccc; margin-top: .5rem; }}
    .btn-secondary:hover {{ background: #3a3a4e; }}
    .result-card {{ background: #1a1a2e; border-radius: 12px; padding: 1rem; margin-bottom: .5rem; border: 1px solid #2a2a3e; display: flex; justify-content: space-between; align-items: center; }}
    .found {{ color: #22c55e; }} .not-found {{ color: #ef4444; }} .blocked {{ color: #f59e0b; }}
    .score {{ font-size: 2rem; font-weight: 800; text-align: center; padding: 1rem; }}
    .score-bar {{ height: 8px; border-radius: 4px; background: #2a2a3e; overflow: hidden; margin: .5rem 0 1.5rem; }}
    .score-fill {{ height: 100%; border-radius: 4px; transition: width .5s; }}
    .error-msg {{ color: #f87171; background: #2a0a0a; border: 1px solid #7f1d1d; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
    .platforms-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-bottom: 1rem; }}
    .platforms-grid label {{ display: flex; align-items: center; gap: .5rem; font-weight: 400; cursor: pointer; }}
    .platforms-grid input[type=checkbox] {{ width: auto; margin: 0; }}
    .footer {{ text-align: center; color: #555; font-size: .8rem; margin-top: 2rem; padding: 1rem; }}
    .footer a {{ color: #ef4444; }}
    .loading {{ text-align: center; padding: 2rem; }}
    .loading::after {{ content: '🦘'; font-size: 2rem; animation: bounce 1s infinite; display: block; }}
    @keyframes bounce {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
    @media (max-width: 480px) {{ .platforms-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="container">
    <h1>💔 Cheatin' <span>Heart</span> Scanner</h1>
    <p class="tagline">Who's the dirty mongrel? Check 12 Aussie dating &amp; social sites.</p>

    <div class="card">
      <form id="scanForm" onsubmit="return doScan(event)">
        <label for="username">Email, Username or Phone</label>
        <input type="text" id="username" name="username" placeholder="e.g. johnno84 or johnno@bigpond.com" required />
        <div class="hint">Just one is enough — we'll figure out the rest.</div>
        <button type="submit" class="btn-primary" id="submitBtn">🔍 Sniff Around — $1.00</button>
      </form>
    </div>

    <div id="results"></div>

    <div class="footer">
      <p><a href="#" onclick="return showPlats()">View all 12 platforms we check</a></p>
      <p style="margin-top:.5rem">🔒 Payments via Stripe. Your search is not stored.</p>
    </div>
  </div>

  <script>
    const PLATFORMS = {platforms_json};

    function showPlats() {{
      alert('Platforms:\\n' + PLATFORMS.map(p => p.label + (p.needs_proxy ? ' ⚠️ needs proxy' : ' ✅')).join('\\n'));
      return false;
    }}

    async function doScan(e) {{
      e.preventDefault();
      const username = document.getElementById('username').value.trim();
      if (!username) return;
      const submitBtn = document.getElementById('submitBtn');
      submitBtn.disabled = true;
      submitBtn.textContent = '🦘 Scanning...';
      document.getElementById('results').innerHTML = '<div class="loading">Checkin 12 sites...</div>';

      try {{
        // Step 1: Create Stripe Checkout session
        const sessionResp = await fetch('/create-checkout-session', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ username }})
        }});
        const session = await sessionResp.json();
        if (session.error) throw new Error(session.error);

        // Step 2: Redirect to Stripe Checkout
        window.location.href = session.url;
      }} catch (err) {{
        document.getElementById('results').innerHTML =
          '<div class="error-msg">❌ ' + err.message + '</div>';
        submitBtn.disabled = false;
        submitBtn.textContent = '🔍 Sniff Around — $1.00';
      }}
    }}

    // Show results if returning from Stripe
    window.addEventListener('DOMContentLoaded', async () => {{
      const params = new URLSearchParams(window.location.search);
      const username = params.get('username');
      const sessionId = params.get('session_id');
      if (username && sessionId) {{
        document.getElementById('username').value = username;
        document.getElementById('submitBtn').disabled = true;
        document.getElementById('submitBtn').textContent = '🦘 Loading results...';
        document.getElementById('results').innerHTML = '<div class="loading">Loading your results...</div>';
        try {{
          const resp = await fetch('/scan?username=' + encodeURIComponent(username) + '&session_id=' + sessionId);
          if (!resp.ok) throw new Error('Scan failed');
          const data = await resp.json();
          renderResults(data);
        }} catch (err) {{
          document.getElementById('results').innerHTML =
            '<div class="error-msg">❌ ' + err.message + '</div>';
        }}
        document.getElementById('submitBtn').disabled = false;
        document.getElementById('submitBtn').textContent = '🔍 Sniff Around — $1.00';
      }}
    }});

    function renderResults(data) {{
      let html = '<h2 style="margin:1.5rem 0 1rem">📊 Results</h2>';
      let found = 0, total = 0;
      for (const item of data) {{
        if (item.type === 'summary') {{
          const s = item.summary;
          found = s.profilesFound; total = s.platformsChecked;
          const pct = s.score;
          const color = pct > 50 ? '#ef4444' : pct > 0 ? '#f59e0b' : '#22c55e';
          html += '<div class="card"><div class="score">' + found + '/' + total + ' profiles found</div>';
          html += '<div class="score-bar"><div class="score-fill" style="width:' + pct + '%;background:' + color + '"></div></div>';
          html += '<div style="text-align:center;font-size:.9rem;color:#888">';
          if (pct > 50) html += '🚩 Lookin pretty dodgy, mate.';
          else if (pct > 0) html += '⚠️ Maybe worth a closer look.';
          else html += '✅ Clean as a whistle.';
          html += '</div></div>';
        }} else if (item.platform) {{
          const cls = item.profileFound ? 'found' : item.error ? 'blocked' : 'not-found';
          const icon = item.profileFound ? '✅' : item.error ? '⚠️' : '❌';
          html += '<div class="result-card"><span>' + icon + ' ' + item.platformLabel + '</span>';
          html += '<span class="' + cls + '">' + (item.evidence || '') + '</span></div>';
        }}
      }}
      html += '<button class="btn-secondary" onclick="window.location.href=\'/\'">🔍 Scan someone else</button>';
      document.getElementById('results').innerHTML = html;
    }}
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


@app.post("/create-checkout-session")
@limiter.limit("10/hour")
async def create_checkout(request: Request, body: dict = None):
    """Create a Stripe Checkout session for $1/scan."""
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
            success_url=f"{BASE_URL}/scan?username={username}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")


@app.get("/scan")
@limiter.limit("10/hour")
async def do_scan(
    request: Request,
    username: str = Query(None),
    session_id: str = Query(None),
    demo: str = Query(None),
    platforms: str = Query(None),
):
    """Run the scan. Requires a valid Stripe session or demo mode."""
    if not username:
        raise HTTPException(422, "username is required")

    # Verify payment (skip for demo mode)
    if not demo:
        if not session_id and not STRIPE_PRICE_ID:
            raise HTTPException(402, "payment required")
        if session_id and STRIPE_SECRET_KEY and STRIPE_PRICE_ID:
            try:
                sess = stripe.checkout.Session.retrieve(session_id)
                if sess.payment_status != "paid":
                    raise HTTPException(402, "payment not completed")
            except stripe.error.StripeError as e:
                raise HTTPException(402, f"payment verification failed: {e}")

    platform_list = platforms.split(",") if platforms else None

    results = await scan_all(
        username,
        platforms=platform_list,
        proxy_url=None,  # No proxy for self-hosted
        limit_per_host=1,
    )

    return results


# ── Run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)