"""
Cheatin' Heart Scanner — Core Probe Engine
============================================
Stone the flamin' crows! Shared logic for sniffin' 12 Aussie adult/social
sites. Used by the Apify actor, standalone CLI, and FastAPI server.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Bright Data Web Unlocker ───────────────────────────────────────────
BRIGHTDATA_API_KEY = os.environ.get("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_ZONE = os.environ.get("BRIGHTDATA_ZONE", "cheatin_zone")
BRIGHTDATA_API = "https://api.brightdata.com/request"


async def probe_via_brightdata(url: str) -> dict:
    """Probe a URL through Bright Data Web Unlocker instead of direct HTTP."""
    if not BRIGHTDATA_API_KEY:
        return {"error": "BrightData API key not configured", "statusCode": 0}

    try:
        payload = {"zone": BRIGHTDATA_ZONE, "url": url, "format": "raw"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BRIGHTDATA_API, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=25)
            ) as resp:
                if resp.status != 200:
                    return {"error": f"BrightData returned HTTP {resp.status}", "statusCode": resp.status}

                body = await resp.text()
                result = {"profileFound": False, "statusCode": 200, "evidence": "Proxied via BrightData"}

                # Check for not-found patterns
                notfound_patterns = [
                    "not found", "doesn't exist", "no account",
                    "page not found", "user not found", "sorry",
                    "this page doesn't exist", "couldn't find",
                    "the page you were looking for doesn't exist",
                    "page doesn't exist",
                ]
                has_content = any(p in body.lower() for p in notfound_patterns)
                result["profileFound"] = not has_content
                result["evidence"] = "Proxied via BrightData — " + (
                    f"Got HTTP {resp.status} but body says 'not found'" if has_content
                    else f"Profile exists — HTTP {resp.status}"
                )

                # Try to scrape profile name
                try:
                    soup = BeautifulSoup(body, "html.parser")
                    title = soup.title.string if soup.title else ""
                    result["profile_name"] = title[:120] if title else ""
                except Exception:
                    pass

                return result
    except asyncio.TimeoutError:
        return {"error": "BrightData request timed out", "statusCode": 0}
    except Exception as exc:
        return {"error": f"BrightData error: {type(exc).__name__}", "statusCode": 0}


# ── Sherlock & Holehe paths ────────────────────────────────────────────
HERMES_VENV = "/usr/local/lib/hermes-agent/venv/bin"
SHERLOCK_BIN = os.path.join(HERMES_VENV, "sherlock")
HOLEHE_BIN = os.path.join(HERMES_VENV, "holehe")

# ── HTTP scrape headers (real-browser-ish) ─────────────────────────────
SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

# ── Which sites we're sniffin' ──────────────────────────────────────────────
PLATFORMS = [
    {"key": "snapchat", "label": "Snapchat", "url_template": "https://www.snapchat.com/add/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "instagram", "label": "Instagram", "url_template": "https://www.instagram.com/{u}/", "found_codes": [200], "notfound_codes": [404]},
    {"key": "telegram", "label": "Telegram", "url_template": "https://t.me/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "redhotpie", "label": "RedHotPie", "url_template": "https://www.redhotpie.com.au/members/{u}", "found_codes": [200], "notfound_codes": [404], "needs_proxy": True},
    {"key": "adultfriendfinder", "label": "AdultFriendFinder", "url_template": "https://www.adultfriendfinder.com/go/page/member.html?id={u}", "found_codes": [200], "notfound_codes": [404, 403], "needs_proxy": True},
    {"key": "rsvp", "label": "RSVP", "url_template": "https://www.rsvp.com.au/member/{u}", "found_codes": [200], "notfound_codes": [404]},
    {"key": "tiktok", "label": "TikTok", "url_template": "https://www.tiktok.com/@{u}", "found_codes": [200], "notfound_codes": [404]},
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

    if platform_def.get("needs_proxy"):
        if not proxy_url and BRIGHTDATA_API_KEY:
            # Use Bright Data Web Unlocker instead of direct HTTP
            bd_result = await probe_via_brightdata(url)
            result.update(bd_result)
            return result
        elif not proxy_url:
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


# ── Sherlock (username OSINT) ──────────────────────────────────────────


def _looks_like_email(value: str) -> bool:
    """Rough check — has an @ with something before and a dot after."""
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def sherlock_check(username: str, timeout: int = 45) -> dict:
    """
    Run Sherlock CLI to find social-network accounts by username.
    Returns a result dict with platform key 'sherlock'.
    """
    result = {
        "platform": "sherlock",
        "platformLabel": "Sherlock (400+ Sites)",
        "profileFound": False,
        "profileUrl": None,
        "username": username,
        "error": None,
        "evidence": None,
        "profileData": None,
        "sherlock_sites_found": [],
    }
    try:
        out = subprocess.run(
            [SHERLOCK_BIN, "--output", "/dev/stdout", "--print-found", "--no-color", "--timeout", "15", username],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        stdout = out.stdout or ""
        stderr = out.stderr or ""
        sites = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[+]") or line.startswith("[ + ]"):
                # Parse: "[+] SiteName: https://..."
                parts = line.split(": ", 1)
                if len(parts) == 2:
                    site_name = parts[0].lstrip("[+] ").strip()
                    site_url = parts[1].strip()
                    sites.append({"name": site_name, "url": site_url})
        result["sherlock_sites_found"] = sites
        if sites:
            result["profileFound"] = True
            result["profileUrl"] = sites[0]["url"]
            result["evidence"] = f"Sherlock found {len(sites)} profile(s)"
            result["profileData"] = {"sites": sites}
        else:
            result["evidence"] = "No Sherlock results found"
    except subprocess.TimeoutExpired:
        result["error"] = "Sherlock timed out"
        result["evidence"] = "⏰ Sherlock took too long"
    except FileNotFoundError:
        result["error"] = "Sherlock CLI not found"
        result["evidence"] = "⚠️ Sherlock not installed"
    except Exception as exc:
        result["error"] = f"Sherlock error: {type(exc).__name__}"
        result["evidence"] = f"🔌 Sherlock failed — {exc}"
    return result


# ── Holehe (email OSINT) ────────────────────────────────────────────────


def holehe_check(email: str, timeout: int = 60) -> dict:
    """
    Run Holehe CLI to check which sites an email is registered on.
    Returns a result dict with platform key 'holehe'.
    """
    result = {
        "platform": "holehe",
        "platformLabel": "Holehe (Email Check)",
        "profileFound": False,
        "profileUrl": None,
        "username": email,
        "error": None,
        "evidence": None,
        "profileData": None,
        "holehe_sites_found": [],
    }
    try:
        out = subprocess.run(
            [HOLEHE_BIN, "--no-color", "--no-clear", "--only-used", "--timeout", "10", email],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        stdout = out.stdout or ""
        sites = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[+]"):
                site_name = line.lstrip("[+] ").strip()
                # Skip summary/status lines
                if site_name and not any(kw in site_name.lower() for kw in ["email used", "not used", "rate limit", "---"]):
                    sites.append(site_name)
        result["holehe_sites_found"] = sites
        if sites:
            result["profileFound"] = True
            result["evidence"] = f"Holehe found {len(sites)} registration(s)"
            result["profileData"] = {"sites": sites}
        else:
            result["evidence"] = "No Holehe results found"
    except subprocess.TimeoutExpired:
        result["error"] = "Holehe timed out"
        result["evidence"] = "⏰ Holehe took too long"
    except FileNotFoundError:
        result["error"] = "Holehe CLI not found"
        result["evidence"] = "⚠️ Holehe not installed"
    except Exception as exc:
        result["error"] = f"Holehe error: {type(exc).__name__}"
        result["evidence"] = f"🔌 Holehe failed — {exc}"
    return result


# ── EmailRep.io (email OSINT) ────────────────────────────────────────────


async def emailrep_check(email: str, timeout: int = 15) -> dict:
    """
    Query the free emailrep.io API for reputation data, social media links,
    and breach information about an email address.
    Returns a dict with platform key 'emailrep'.
    """
    import aiohttp

    result = {
        "platform": "emailrep",
        "platformLabel": "EmailRep.io",
        "profileFound": False,
        "profileUrl": None,
        "username": email,
        "error": None,
        "evidence": None,
        "profileData": None,
        "emailrep_reputation": None,
        "emailrep_breaches": [],
        "emailrep_socials": [],
    }
    try:
        url = f"https://emailrep.io/{email}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["profileData"] = data
                    result["emailrep_reputation"] = data.get("reputation", "unknown")
                    result["emailrep_breaches"] = data.get("details", {}).get("breaches", []) or []
                    result["emailrep_socials"] = data.get("details", {}).get("social_media", {}).get("profiles", []) or []

                    if result["emailrep_reputation"] == "high":
                        result["profileFound"] = True
                        result["evidence"] = f"High risk — {len(result['emailrep_breaches'])} breach(es), {len(result['emailrep_socials'])} social profile(s)"
                    elif result["emailrep_reputation"] == "medium":
                        result["profileFound"] = True
                        result["evidence"] = f"Medium risk — {len(result['emailrep_breaches'])} breach(es), {len(result['emailrep_socials'])} social profile(s)"
                    elif result["emailrep_reputation"] == "low":
                        result["evidence"] = f"Low risk — {len(result['emailrep_breaches'])} breach(es), {len(result['emailrep_socials'])} social profile(s)"
                    else:
                        result["evidence"] = f"Reputation: {result['emailrep_reputation']}"
                elif resp.status == 429:
                    result["error"] = "Rate limited by emailrep.io"
                    result["evidence"] = "⏳ EmailRep.io rate limit hit"
                elif resp.status == 404:
                    result["evidence"] = "Email not found in EmailRep.io database"
                else:
                    result["error"] = f"EmailRep.io returned HTTP {resp.status}"
                    result["evidence"] = f"⚠️ HTTP {resp.status}"
    except asyncio.TimeoutError:
        result["error"] = "EmailRep.io timed out"
        result["evidence"] = "⏰ EmailRep.io took too long"
    except aiohttp.ClientError as exc:
        result["error"] = f"EmailRep.io connection error: {type(exc).__name__}"
        result["evidence"] = f"🔌 EmailRep.io — {type(exc).__name__}"
    except Exception as exc:
        result["error"] = f"EmailRep.io error: {type(exc).__name__}"
        result["evidence"] = f"⚠️ EmailRep.io — {exc}"

    return result


# ── Maigret check (3000+ sites) ────────────────────────────────────────


def maigret_check(username: str, timeout: int = 60) -> dict:
    """Run maigret CLI to check username across 3000+ sites."""
    result = {
        "source": "maigret",
        "username": username,
        "sites_found": [],
        "total_found": 0,
        "error": None,
    }
    try:
        import subprocess, tempfile, os, json
        output_file = f"/tmp/maigret_{username}.json"
        cmd = [
            "/usr/local/lib/hermes-agent/venv/bin/maigret", username,
            "-J", "simple",
            "--folderoutput", "/tmp",
            "--timeout", str(timeout),
            "--no-progressbar",
            "--no-color",
            "--top-sites", "50",
        ]
        subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
        output_file = f"/tmp/report_{username}_simple.json"
        if os.path.exists(output_file):
            with open(output_file) as f:
                data = json.load(f)
            # Top-level keys are the site names
            found = []
            for site_name, site_data in data.items():
                if isinstance(site_data, dict):
                    status_obj = site_data.get("status")
                    if isinstance(status_obj, dict):
                        status_str = str(status_obj.get("status", "")).lower()
                    else:
                        status_str = str(status_obj).lower()
                    if status_str in ("found", "claimed", "yes", "claim"):
                        found.append({
                            "site_name": site_name,
                            "url": site_data.get("url", ""),
                            "username": site_data.get("username", username),
                        })
            result["sites_found"] = found
            result["total_found"] = len(found)
            os.remove(output_file)
    except subprocess.TimeoutExpired:
        result["error"] = "Maigret timed out"
    except FileNotFoundError:
        result["error"] = "Maigret CLI not found"
    except Exception as exc:
        result["error"] = f"Maigret error: {type(exc).__name__}"
    return result


# ── Telegram Profile Scraper ────────────────────────────────────────────


async def _fetch_html(url: str, session: aiohttp.ClientSession | None = None) -> str | None:
    """Fetch a URL and return the response body as text, or None on failure."""
    try:
        if session:
            async with session.get(url, headers=SCRAPE_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.text()
        else:
            async with aiohttp.ClientSession(headers=SCRAPE_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(url) as resp:
                    if resp.status == 200:
                        return await resp.text()
    except Exception:
        pass
    return None


def scrape_telegram(username: str, session: aiohttp.ClientSession | None = None) -> dict:
    """
    Scrape t.me/{username} for profile info — name, bio, photo.
    Returns a dict with enriched profile data.
    """
    result = {
        "platform": "telegram_profile",
        "platformLabel": "Telegram Profile",
        "profileFound": False,
        "profileUrl": f"https://t.me/{username}",
        "username": username,
        "error": None,
        "evidence": None,
        "profileData": None,
    }

    async def _scrape():
        html = await _fetch_html(f"https://t.me/{username}")
        if not html:
            result["error"] = "Could not fetch Telegram page"
            result["evidence"] = "🔌 Failed to load t.me page"
            return result

        soup = BeautifulSoup(html, "lxml")

        # Check if page exists (t.me returns 200 but shows error text)
        error_div = soup.find("div", class_="tgme_page_extra")
        if error_div and "if you have" in error_div.get_text(strip=True).lower():
            result["evidence"] = "Telegram profile not found"
            return result

        profile_data = {}

        # Name
        name_el = soup.find("div", class_="tgme_page_title")
        if name_el:
            profile_data["name"] = name_el.get_text(strip=True)

        # Bio / extra text
        extra_el = soup.find("div", class_="tgme_page_description")
        if extra_el:
            bio_text = extra_el.get_text(" ", strip=True)
            # Non-existent profiles show "If you have Telegram, you can contact @username right away."
            if "you can contact" in bio_text.lower():
                result["evidence"] = "Telegram profile not found"
                return result
            profile_data["bio"] = bio_text

        # Photo URL
        photo_el = soup.find("img", class_="tgme_page_photo_image")
        if photo_el and photo_el.get("src"):
            profile_data["photo_url"] = photo_el["src"]

        if profile_data:
            result["profileFound"] = True
            result["profileData"] = profile_data
            result["evidence"] = f"Telegram profile: {profile_data.get('name', 'unknown')}"
        else:
            result["evidence"] = "Telegram profile page exists but no data extracted"

        return result

    # Run the async scrape synchronously (or as a task in scan_all)
    try:
        loop = asyncio.get_running_loop()
        # Already in an event loop — return the coroutine for the caller to await
        return _scrape()
    except RuntimeError:
        # No running loop — run it
        return asyncio.run(_scrape())


# ── X / Twitter Profile Scraper ────────────────────────────────────────


def scrape_twitter(username: str, session: aiohttp.ClientSession | None = None) -> dict:
    """
    Scrape x.com/{username} for profile info — name, bio, follower count, photo.
    Returns a dict with enriched profile data.
    """
    result = {
        "platform": "x_profile",
        "platformLabel": "X / Twitter Profile",
        "profileFound": False,
        "profileUrl": f"https://x.com/{username}",
        "username": username,
        "error": None,
        "evidence": None,
        "profileData": None,
    }

    async def _scrape():
        html = await _fetch_html(f"https://x.com/{username}", session)
        if not html:
            result["error"] = "Could not fetch X profile page"
            result["evidence"] = "🔌 Failed to load x.com page"
            return result

        soup = BeautifulSoup(html, "lxml")
        profile_data = {}

        # X serves a static HTML shell — look for meta tags and JSON data
        # Try meta description for bio
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            prop = (meta.get("property") or "").lower()
            content = meta.get("content", "")
            if name == "description" or prop == "og:description":
                if content:
                    profile_data["bio"] = content
            if prop == "og:title":
                if content:
                    profile_data["name"] = content
            if prop == "og:image":
                if content:
                    profile_data["photo_url"] = content
            if prop == "og:url":
                if content:
                    profile_data["profile_url"] = content

        # Also look for the profile JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Person":
                        if "name" in data and "name" not in profile_data:
                            profile_data["name"] = data["name"]
                        if "description" in data and "bio" not in profile_data:
                            profile_data["bio"] = data["description"]
                        if "image" in data and "photo_url" not in profile_data:
                            if isinstance(data["image"], dict):
                                profile_data["photo_url"] = data["image"].get("url", "")
                            else:
                                profile_data["photo_url"] = data["image"]
            except (json.JSONDecodeError, TypeError):
                continue

        if profile_data:
            result["profileFound"] = True
            result["profileData"] = profile_data
            result["evidence"] = f"X profile: {profile_data.get('name', 'unknown')}"
        else:
            result["evidence"] = "X profile page exists but no data extracted"

        return result

    try:
        loop = asyncio.get_running_loop()
        return _scrape()
    except RuntimeError:
        return asyncio.run(_scrape())


# ── Main scan ──────────────────────────────────────────────────────────


async def scan_all(
    username: str,
    platforms: list[str] | None = None,
    proxy_url: str | None = None,
    limit_per_host: int = 2,
    timeout: int = 30,
    skip_enrichment: bool = False,
) -> list[dict]:
    """
    Scan a username across all (or selected) platforms.
    Also runs Sherlock, Holehe, Telegram profile scrape, and X profile scrape as enrichment.
    Returns a list of result dicts, ending with a summary item.
    """
    is_email = _looks_like_email(username)
    active = [p for p in PLATFORMS if not platforms or p["key"] in platforms]
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=limit_per_host)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as session:
        tasks = [asyncio.create_task(probe_platform(session, p, username, proxy_url)) for p in active]

        # Enrichment tasks — run concurrently alongside platform probes
        if not skip_enrichment and not platforms:
            # Sherlock: only for non-email usernames
            if not is_email:
                tasks.append(asyncio.create_task(
                    _run_in_executor(sherlock_check, username)
                ))
                # Maigret: 3000+ site check for non-email usernames
                tasks.append(asyncio.create_task(
                    _run_in_executor(maigret_check, username)
                ))

            # Holehe: only for email inputs
            if is_email:
                tasks.append(asyncio.create_task(
                    _run_in_executor(holehe_check, username)
                ))
                # EmailRep.io: email reputation, breaches, social media
                tasks.append(asyncio.create_task(
                    emailrep_check(username)
                ))

            # Telegram profile scrape
            tasks.append(asyncio.create_task(scrape_telegram(username, session)))

            # X / Twitter profile scrape
            tasks.append(asyncio.create_task(scrape_twitter(username, session)))

        results = []
        found = 0
        for coro in asyncio.as_completed(tasks):
            r = await coro
            if isinstance(r, dict) and r.get("profileFound"):
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


async def _run_in_executor(fn, arg):
    """Run a blocking function in the default executor so it doesn't block the event loop."""
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, arg)