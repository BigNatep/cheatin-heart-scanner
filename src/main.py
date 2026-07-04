"""
Cheatin' Heart Scanner — Apify Actor
======================================
Stone the flamin' crows! Wraps the shared probe engine for the Apify Store.
"""

import asyncio
import logging

from apify import Actor

# Shared probe engine — same code used by CLI & API server
from cheatin_scanner.core import scan_all, PLATFORMS

logger = logging.getLogger(__name__)


async def main() -> None:
    """Entry point — strike me roan, let's find some answers."""
    async with Actor:
        actor_input = await Actor.get_input() or {}

        # ── Grab the search params ─────────────────────────────────
        email = (actor_input.get("email") or "").strip()
        username = (actor_input.get("username") or "").strip()
        phone = (actor_input.get("phone") or "").strip()
        full_name = (actor_input.get("fullName") or "").strip()
        requested_platforms = actor_input.get("platforms", []) or []

        query = {
            "email": email,
            "username": username,
            "phone": phone,
            "fullName": full_name,
        }

        await Actor.set_status_message(
            f"🦘 Sniffin' around for {username or email or phone}..."
        )

        if not username and not email and not phone:
            await Actor.push_data({
                "error": "Yeah nah, ya gotta give us somethin' — email, username, or phone.",
                "query": query,
            })
            await Actor.set_status_message("Stuffed — no input provided")
            return

        # ── Pick platforms ─────────────────────────────────────────
        if requested_platforms:
            active_platforms = [p for p in PLATFORMS if p["key"] in requested_platforms]
        else:
            active_platforms = PLATFORMS

        # Use username for URL probes, fall back to email prefix
        probe_username = username or (email.split("@")[0] if email else phone)

        await Actor.set_status_message(
            f"🔍 Checkin' {len(active_platforms)} site(s) for '{probe_username}'..."
        )

        # ── Get Apify proxy (residential for blocked sites) ─────────
        proxy_configuration = await Actor.create_proxy_configuration(
            use_residential_proxies=True
        )
        proxy_url = await proxy_configuration.new_url() if proxy_configuration else None
        if proxy_url:
            logger.info("Using Apify proxy for residential-only sites")

        # ── Fire all probes concurrently ───────────────────────────
        results = await scan_all(
            probe_username,
            platforms=requested_platforms or None,
            proxy_url=proxy_url,
        )

        # ── Push results to Apify dataset ──────────────────────────
        found_count = 0
        for r in results:
            r["query"] = query
            if r.get("profileFound"):
                found_count += 1
            await Actor.push_data(r)

        # ── Done ───────────────────────────────────────────────────
        total = len(active_platforms)
        msg = f"✅ Done! Found {found_count}/{total} profile(s) for '{probe_username}'"
        await Actor.set_status_message(msg)
        logger.info(msg)


if __name__ == "__main__":
    asyncio.run(main())