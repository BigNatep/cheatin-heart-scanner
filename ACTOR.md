# Cheatin' Heart Scanner — Who's the Dirty Mongrel? 🇦🇺🔍

[![Apify](https://img.shields.io/badge/Apify-Actor-blue)](https://apify.com)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)

> **Got a sneaky suspicion? For the price of a coffee, catch 'em red-handed.**
> Scans 12 Aussie dating & social sites in 30 seconds. Email. Username. Phone. Pick one.

**Strike me roan!** Suspicious your partner's been a bit too friendly with the Uber Eats driver? Found a strange number in their phone? **Cheatin' Heart Scanner** checks 12 Australian adult social and dating sites to see if someone's profiles are kickin' around where they shouldn't be.

Chuck in an **email, username, or phone number** and this lil' beauty sniffs around **Snapchat, Telegram, Instagram, X/Twitter, AdultFriendFinder, Plenty of Fish, RedHotPie, OKCupid, OnlyFans, FetLife, RSVP, and more** — faster than a gossiping tradie at smoko. You'll know if they're fair dinkum or a dodgy mongrel.

**Don't trust your gut. Trust the receipts.**

---

## 🔧 What This Beauty Does

### The Sites We Check (v1 — Live)

| Site | How We Check | Verdict |
|---|---|---|
| **Telegram** ✈️ | `t.me/{username}` | ✅ Live |
| **Snapchat** 👻 | `snapchat.com/add/{username}` | ✅ Live |
| **Instagram** 📸 | `instagram.com/{username}/` | ✅ Live |
| **X / Twitter** 🐦 | `x.com/{username}` | ✅ Live |
| **AdultFriendFinder** 🔥 | Profile check | ✅ Live |
| **Plenty of Fish** 🐟 | `pof.com` username check | ✅ Live |
| **RedHotPie** 🥧 | AU's biggest adult dating site | ✅ With residential proxy |
| **OKCupid** 💞 | Dating profile check | ✅ With residential proxy |
| **OnlyFans** 🔞 | Creator profile check | ✅ With residential proxy |
| **FetLife** ⛓️ | Kink/fetish social network | ✅ With residential proxy |
| **RSVP** 💔 | AU dating site | ❌ 404 |

> **Disclaimer:** This is an OSINT tool for investigative purposes. Don't be a creep. If you're usin' it, you've got your reasons — I'm not your priest.

### What You Need (Input)

| Field | Required? | What It Is |
|---|---|---|
| `email` | One of these | Their email address (e.g. `johnno@bigpond.com`) |
| `username` | One of these | Their handle/nickname on these sites |
| `phone` | One of these | Aussie mobile number (e.g. `+614****5678`) |
| `fullName` | Nah | Their full name — helps narrow results |
| `platforms` | Nah | Which sites to check (default: all 12) |
| `state` | Nah | Which AU state — filters local sites (NSW, VIC, QLD, etc.) |

### What You Get Back (The Receipts)

```json
{
  "platform": "snapchat",
  "profileFound": true,
  "profileUrl": "https://www.snapchat.com/add/johnno84",
  "username": "johnno84",
  "evidence": "✅ Profile exists — HTTP 200",
  "statusCode": 200
}
```

Plus a summary with your **Dodgy Meter score** (0–100).

---

## 🧪 Test Locally

```bash
cd /root/cheatin-heart-scanner
source /tmp/cheatin-venv/bin/activate

# Dry run — no real sites hit
python test_local.py --username johnno84 --dry-run

# Real test
python test_local.py --username johnno84

# Specific platforms
python test_local.py --email johnno@bigpond.com --platforms snapchat telegram pof
```

---

## 🐍 Call From Code

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_API_TOKEN")

result = client.actor("YOUR_USERNAME/cheatin-heart-scanner").call(
    run_input={
        "email": "johnno@bigpond.com",
        "username": "johnno84",
        "phone": "+614****5678",
        "platforms": ["snapchat", "adultfriendfinder", "pof", "redhotpie"]
    }
)

dataset = client.dataset(result["defaultDatasetId"]).list_items()
print(dataset.items)
```

### cURL

```bash
curl -X POST "https://api.apify.com/v2/acts/YOUR_USERNAME~cheatin-heart-scanner/runs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ***" \
  -d '{
    "username": "johnno84",
    "platforms": ["snapchat", "telegram", "instagram"]
  }'
```

---

## 💰 How Much? (Cheaper Than A Coffee)

| What | Price | Value Comparison |
|---|---|---|
| **Full scan** (all 12 sites) | **$0.50** | Half a servo pie |
| **Quick check** (pick 3-4 sites) | **$0.20** | Less than a scratchie |
| **Private investigator** | **$150+/hr** | You do the bloody maths |

> Still cheaper than a divorce lawyer. Way cheaper than finding out too late.

---

## 🛟 Stuffed? Need A Hand?

- **Bug or issue?** — [GitHub Issues](https://github.com/YOUR_USERNAME/cheatin-heart-scanner/issues)
- **Wanna chinwag?** — [Discord](https://discord.gg/jyEM2PRvMU)
- **Found a dodgy partner?** — That's between you and them. I'm not ya counsellor.

---

## 📄 Legalese

MIT license. Use it wisely. Don't be a tool. This is an OSINT investigation tool — what you do with the info is your own bloody business.

---

*Strike me roan. Built with 🦘 and a broken heart by someone who's seen too many "just work friends" situations. If you're here, you already bloody know why.*