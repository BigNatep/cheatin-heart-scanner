#!/usr/bin/env python3
"""Cheatin' Heart Scanner — Who's the Dirty Mongrel? Test Harness.
Strike me roan, don't run this without settin' up the env first.

Usage:
    # Quick test with a username
    python test_local.py --username johnno84

    # Test with email
    python test_local.py --email johnno@bigpond.com

    # Test specific platforms
    python test_local.py --username testuser --platforms snapchat telegram

    # Full test
    python test_local.py --username testuser --full-name "John Smith" --state NSW
"""

import argparse
import os
import sys
import tempfile
import json

# ── Set up local storage dir so Apify SDK doesn't scream ─────────────
LOCAL_DIR = os.path.join(tempfile.gettempdir(), "cheatin-heart-test")
os.environ["APIFY_LOCAL_STORAGE_DIR"] = LOCAL_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Stone the flamin' crows, test the Cheatin' Heart Scanner locally!"
    )
    parser.add_argument("--username", help="Username to look up")
    parser.add_argument("--email", help="Email address")
    parser.add_argument("--phone", help="Phone number (E.164)")
    parser.add_argument("--full-name", help="Full name (optional)")
    parser.add_argument("--platforms", nargs="+", default=[],
                        help="Platforms to check (default: all)")
    parser.add_argument("--state", default="", choices=["", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"],
                        help="Aussie state filter")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just print what would happen without hitting real sites")

    args = parser.parse_args()

    if not args.username and not args.email and not args.phone:
        print("❌ Yeah nah mate, ya gotta give us a username, email, or phone!")
        parser.print_help()
        sys.exit(1)

    # Build input like Apify would
    run_input = {
        "username": args.username or "",
        "email": args.email or "",
        "phone": args.phone or "",
        "fullName": args.full_name or "",
        "platforms": args.platforms,
        "state": args.state,
    }

    print(f"🦘 Cheatin' Heart Scanner — Local Test")
    print(f"{'='*50}")
    print(f"  Looking up: {args.username or args.email or args.phone}")
    print(f"  Platforms:  {', '.join(args.platforms) if args.platforms else 'ALL'}")
    print(f"{'='*50}")
    print()

    if args.dry_run:
        print("📋 DRY RUN — no sites will be hit")
        print(f"  Would send input: {json.dumps(run_input, indent=2)}")
        print()
        platforms = args.platforms or [
            "redhotpie", "adultfriendfinder", "snapchat", "telegram", "rsvp"
        ]
        for p in platforms:
            print(f"  🔍 Would check '{p}'...")
        print()
        print("✅ Dry run complete. Remove --dry-run to actually test.")
        return

    # Write input to the local storage directory (Apify SDK 3.x uses key_value_stores)
    input_dir = os.path.join(LOCAL_DIR, "key_value_stores", "default")
    os.makedirs(input_dir, exist_ok=True)
    with open(os.path.join(input_dir, "INPUT"), "w") as f:
        json.dump(run_input, f)

    # Run the actor
    print("🔍 Firin' off the probes...")
    print()
    sys.path.insert(0, os.path.dirname(__file__))

    from src.main import main as actor_main
    import asyncio
    asyncio.run(actor_main())

    # Read back all dataset entries (Apify SDK 3.x stores one file per item)
    dataset_dir = os.path.join(LOCAL_DIR, "datasets", "default")
    dataset_files = sorted(
        f for f in os.listdir(dataset_dir)
        if f.startswith("00000") and f.endswith(".json") and f != "__metadata__.json"
    )
    if dataset_files:
        print()
        print("📊 Results:")
        print(f"{'='*50}")
        for df in dataset_files:
            with open(os.path.join(dataset_dir, df)) as f:
                item = json.load(f)
            if item.get("type") == "summary":
                s = item.get("summary", {})
                print(f"\n📈 Score: {s.get('score', 0)}% — {s.get('profilesFound', 0)}/{s.get('platformsChecked', 0)} found")
            elif "platform" in item:
                emoji = "✅" if item.get("profileFound") else "❌"
                err = f" — {item.get('error', '')}" if item.get("error") else ""
                code = f" (HTTP {item.get('statusCode', '?')})" if item.get("statusCode") else ""
                print(f"  {emoji}  {item.get('platformLabel', item['platform']):>18}: {item.get('evidence', '')}{code}{err}")
    else:
        print("⚠️ No dataset output found — check logs for errors.")


if __name__ == "__main__":
    main()