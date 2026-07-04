#!/usr/bin/env python3
"""
Cheatin' Heart Scanner — Standalone CLI
=========================================
Stone the flamin' crows! No Apify needed. Just Python + aiohttp.

Usage:
    python scan.py --username johnno84
    python scan.py --email johnno@bigpond.com --platforms snapchat,telegram,pof
    python scan.py --phone "+614****5678" --json
    python scan.py --help
"""

import argparse
import asyncio
import json
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cheatin_scanner.core import scan_all, PLATFORMS


def format_results(results: list[dict], as_json: bool) -> str:
    """Pretty-print or JSON-dump the results."""
    if as_json:
        return json.dumps(results, indent=2, default=str)

    lines = []
    for r in results:
        if r.get("type") == "summary":
            s = r["summary"]
            lines.append(f"\n{'='*50}")
            lines.append(f"📈 Score: {s['score']}% — {s['profilesFound']}/{s['platformsChecked']} found")
            lines.append(f"{'='*50}")
        elif "platform" in r:
            emoji = "✅" if r.get("profileFound") else "❌"
            code = f" (HTTP {r['statusCode']})" if r.get("statusCode") else ""
            err = f" — {r['error']}" if r.get("error") else ""
            lines.append(f"  {emoji}  {r['platformLabel']:>18}: {r.get('evidence', '')}{code}{err}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Cheatin' Heart Scanner — Who's the Dirty Mongrel? (Standalone CLI)",
        epilog="Examples:\n  python scan.py --username johnno84\n  python scan.py --email j@b.com --platforms snapchat,telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    input_group = parser.add_argument_group("Input (at least one required)")
    input_group.add_argument("--username", help="Username to search")
    input_group.add_argument("--email", help="Email address (uses prefix as username)")
    input_group.add_argument("--phone", help="Phone number (E.164 format)")

    parser.add_argument("--platforms", help="Comma-separated platforms (default: all 12)")
    parser.add_argument("--proxy", help="HTTP proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--list-platforms", action="store_true", help="List available platforms and exit")

    args = parser.parse_args()

    if args.list_platforms:
        print(f"{'Platform':>20}  {'Key':<20}  {'Needs Proxy?'}")
        print("-" * 65)
        for p in PLATFORMS:
            proxy = "⚠️" if p.get("needs_proxy") else "✅"
            print(f"{p['label']:>20}  {p['key']:<20}  {proxy}")
        return

    username = args.username or (args.email.split("@")[0] if args.email else args.phone)
    if not username:
        print("❌ Yeah nah, ya gotta give us somethin' — --username, --email, or --phone.")
        parser.print_help()
        sys.exit(1)

    platform_list = args.platforms.split(",") if args.platforms else None

    print(f"🦘 Sniffin' around for '{username}'...")
    if platform_list:
        print(f"🔍 Platforms: {', '.join(platform_list)}")
    else:
        print(f"🔍 Platforms: All {len(PLATFORMS)}")

    results = asyncio.run(scan_all(username, platforms=platform_list, proxy_url=args.proxy))
    print(format_results(results, as_json=args.json))

    # Exit with error if nothing found
    summary = next((r for r in results if r.get("type") == "summary"), None)
    if summary and summary.get("summary", {}).get("profilesFound", 0) == 0:
        sys.exit(0)  # No profiles found but not an error


if __name__ == "__main__":
    main()