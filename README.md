# Respan Suite 🚀

Automated account generator, Cloudflare Turnstile bypass solver, and **Kimi K3.1 Pro** API harvester for **Respan Gateway** with automatic 9router pool integration.

## Features

- **Autonomous Turnstile Solver**: Bypasses Cloudflare Turnstile verification using `Camoufox` (C++ modified Firefox anti-detect engine) via dynamic unhiding and human-like coordinate probing in ~1.0s.
- **Enterprise Domain Compliance**: Automatically provisions corporate/tech email domains (e.g. `fantech.tech`) that pass Respan's strict work email validation filter.
- **Full Automation Lifecycle**:
  1. Solves Turnstile & registers account.
  2. Reads confirmation email via Tempik REST API.
  3. Activates user account via Respan REST API (`POST /auth/users/activation/`).
  4. Obtains JWT session (`POST /auth/jwt/create/`).
  5. Bootstraps organization & generates high-tier Gateway Key (`POST /user/organizations/`).
  6. Validates live model response for `kimi-k3.1-pro` (2M tokens/hr, 10M tokens/day free quota).
  7. Auto-injects API key into local **9router** database (`/var/lib/9router/db/data.sqlite`) under prefix `respan`.

## Quick Start

### 1. Installation

```bash
git clone https://github.com/hudalilsabrina/respan-suite.git
cd respan-suite
chmod +x install.sh
./install.sh
```

### 2. Generate Accounts & Harvest Keys

```bash
# Generate 1 account and inject into 9router
python3 respan_farm.py -n 1

# Generate batch of 5 accounts
python3 respan_farm.py -n 5

# Generate without injecting to 9router
python3 respan_farm.py -n 3 --no-9router
```

### 3. Output Files

- `accounts.txt`: Complete credentials, emails, passwords, user IDs, organization IDs, and API keys.
- `keys.txt`: One API key per line for bulk routing.

---

## Direct Usage via OpenAI SDK

Point standard OpenAI SDK directly at Respan Gateway:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.respan.ai/api",
    api_key="YOUR_RESPAN_API_KEY",
)

response = client.chat.completions.create(
    model="kimi-k3.1-pro",
    messages=[{"role": "user", "content": "Halo Kimi!"}],
)
print(response.choices[0].message.content)
```

---

## 9router Gateway Usage

Once injected, query your 9router instance:

```bash
curl http://127.0.0.1:20127/v1/chat/completions \
  -H "Authorization: Bearer <9ROUTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "respan/kimi-k3.1-pro",
    "messages": [{"role": "user", "content": "Halo Kimi!"}]
  }'
```
