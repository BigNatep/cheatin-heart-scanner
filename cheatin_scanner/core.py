"""
Cheatin' Heart Scanner — Core Probe Engine
============================================
Stone the flamin' crows! Shared logic for sniffin' 12 Aussie adult/social
sites. Used by the Apify actor, standalone CLI, and FastAPI server.
"""

import asyncio
import json
import logging
from urllib.parse import quote_plus

import aiohttp

logger = logging.getLogger(__name__)

# ── Which sites we're sniffin' ──────────────────────────────────────────────
PLATFORMS = [
    {"key": "snapchat", "label": "Snapchat", "url_template": "https://www.snapchat.com/add/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "telegram", "label": "Telegram", "url_template": "https://t.me/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "redhotpie", "label": "RedHotPie", "url_template": "https://www.redhotpie.com.au/members/{u}", "found_codes": [200], "notfound_codes": [404], "needs_proxy": True},
    {"key": "adultfriendfinder", "label": "AdultFriendFinder", "url_template": "https://www.adultfriendfinder.com/go/page/member.html?id={u}", "found_codes": [200], "notfound_codes": [404, 403], "needs_proxy": True},
    {"key": "rsvp", "label": "RSVP", "url_template": "https://www.rsvp.com.au/member/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "tiktok", "label": "TikTok", "url_template": "https://www.tiktok.com/@{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "instagram", "label": "Instagram", "url_template": "https://www.instagram.com/{u}/", "found_codes": [200], "notfound_codes": [404]},
    {"key": "x", "label": "X / Twitter", "url_template": "https://x.com/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "okcupid", "label": "OKCupid", "url_template": "https://www.okcupid.com/profile/{u}", "found_codes": [200], "notfound_codes": [404], "needs_proxy": True},
    {"key": "pof", "label": "Plenty of Fish", "url_template": "https://www.pof.com/viewprofile.aspx?username={u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "onlyfans", "label": "OnlyFans", "url_template": "https://onlyfans.com/{u}", "found_codes": [200], "notfound_codes": [404], "needs_proxy": True},
    {"key": "fetlife", "label": "FetLife", "url_template": "https://fetlife.com/users/{u}", "found_codes": [200], "notfound_codes": [404], "needs_proxy": True},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
}

NOTFOUND_PHRASES = [
    "not found", "doesn't exist", "no account",
    "page not found", "user not found", "sorry",
    "this page doesn't exist", "couldn't find",
]


def _build_headers(accept_json: bool = False) -> dict:
    h = HEADERS.copy()
    if accept_json:
        h["Accept"] = "application/json, text/plain, */*"
    return h


async def _safe_text(resp: aiohttp.ClientResponse) -> str:
    try:
        return await resp.text()
    except Exception:
        return ""


async def probe_platform(
    session: aiohttp.ClientSession,
    platform_def: dict,
    username: str,
    proxy_url: str | None = None,
) -> dict:
    """
    Check if a username exists on a given platform.
    Returns dict with: platform, profileFound, profileUrl, evidence, statusCode.
    """
    url = platform_def["url_template"].format(u=quote_plus(username))
    result = {
        "platform": platform_def["key"],
        "platformLabel": platform_def["label"],
        "profileFound": False,
        "profileUrl": url,
        "username": username,
        "error": None,
        "statusCode": None,
    }

    if platform_def.get("needs_proxy") and not proxy_url:
        result["error"] = "Blocked — needs residential proxy"
        result["evidence"] = "⚠️ Requires residential proxy (not configured)"
        result["statusCode"] = 0
        return result

    try:
        kwargs = {
            "headers": _build_headers(platform_def.get("check_json", False)),
            "timeout": aiohttp.ClientTimeout(total=15),
            "allow_redirects": True,
        }
        if proxy_url:
            kwargs["proxy"] = proxy_url

        async with session.get(url, **kwargs) as resp:
            result["statusCode"] = resp.status
            body = await _safe_text(resp)

            if resp.status in platform_def.get("found_codes", [200]):
                has_content = any(p in body.lower() for p in NOTFOUND_PHRASES)
                if has_content:
                    result["profileFound"] = False
                    result["evidence"] = f"Got HTTP {resp.status} but body says 'not found'"
                else:
                    result["profileFound"] = True
                    result["evidence"] = f"Profile exists — HTTP {resp.status}"
                    result["profileUrl"] = str(resp.url)

            elif resp.status in platform_def.get("notfound_codes", [404]):
                result["profileFound"] = False
                result["evidence"] = f"Confirmed not found — HTTP {resp.status}"
            elif resp.status == 403:
                result["error"] = "Blocked (403) — site might need login"
                result["evidence"] = "❌ Blocked by site security"
            elif resp.status == 429:
                result["error"] = "Rate limited (429)"
                result["evidence"] = "⏳ Got rate-limited, try again later"
            else:
                result["error"] = f"Unexpected HTTP {resp.status}"
                result["evidence"] = f"⚠️ HTTP {resp.status} — couldn't determine"

    except asyncio.TimeoutError:
        result["error"] = "Timed out"
        result["evidence"] = "⏰ Site took too long to respond"
    except aiohttp.ClientError as exc:
        result["error"] = f"Connection error: {type(exc).__name__}"
        result["evidence"] = f"🔌 Couldn't connect — {type(exc).__name__}"

    return result


async def scan_all(
    username: str,
    platforms: list[str] | None = None,
    proxy_url: str | None = None,
    limit_per_host: int = 2,
    timeout: int = 30,
) -> list[dict]:
    """
    Scan a username across all (or selected) platforms.
    Returns a list of result dicts, ending with a summary item.
    """
    active = [p for p in PLATFORMS if not platforms or p["key"] in platforms]
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=limit_per_host)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as session:
        tasks = [asyncio.create_task(probe_platform(session, p, username, proxy_url)) for p in active]
        results = []
        found = 0
        for coro in asyncio.as_completed(tasks):
            r = await coro
            if r.get("profileFound"):
                found += 1
            results.append(r)

    results.append({
        "type": "summary",
        "query": {"username": username},
        "summary": {
            "platformsChecked": len(active),
            "profilesFound": found,
            "score": round((found / max(len(active), 1)) * 100, 1),
        },
    })
    return results