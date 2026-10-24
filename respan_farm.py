#!/usr/bin/env python3
"""
Respan Suite - Automated Camoufox Account Generator & Kimi K3.1 Pro Harvester.
Bypasses Cloudflare Turnstile, completes email verification via Tempik,
bootstraps workspace, extracts gateway API keys, and auto-injects into 9router.
"""

import argparse
import asyncio
import json
import os
import random
import re
import sqlite3
import string
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Dict, Any, Optional, Tuple

from camoufox.async_api import AsyncCamoufox
from tempmail import TempikClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.txt")
KEYS_FILE = os.path.join(BASE_DIR, "keys.txt")
ROUTER_DB_PATH = "/var/lib/9router/db/data.sqlite"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"


def random_string(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def generate_credentials() -> Tuple[str, str]:
    username = f"respan_{random_string(8)}"
    password = f"Resp!{random_string(10)}@9A"
    return username, password


def print_step(step: str):
    print(f"\n[+] {step}", flush=True)


def print_sub(msg: str):
    print(f"    -> {msg}", flush=True)


async def solve_and_register(page, email: str, password: str) -> Dict[str, Any]:
    print_step("Step 1: Navigating to platform.respan.ai...")
    
    register_result = {}
    async def on_response(resp):
        if "auth/users/" in resp.url and resp.status in (200, 201):
            try:
                register_result["data"] = json.loads(await resp.text())
            except Exception:
                pass
                
    page.on("response", on_response)

    await page.goto("https://platform.respan.ai", timeout=35000)
    await asyncio.sleep(2)

    print_sub("Opening email authentication form...")
    await page.get_by_text("Continue with Email").click()
    await asyncio.sleep(1)

    print_sub(f"Entering email: {email}")
    await page.fill('input[type="email"]', email)
    await page.press('input[type="email"]', "Enter")
    await asyncio.sleep(2.5)

    print_sub("Entering password...")
    await page.type('input[type="password"]', password, delay=40)
    await asyncio.sleep(1)

    print_sub("Detecting and solving Cloudflare Turnstile...")
    # Dynamic unhide if hidden
    await page.evaluate("""() => {
        const input = document.querySelector('input[name="cf-turnstile-response"]');
        if (!input) return null;
        let cur = input;
        while (cur && cur.parentElement) {
            if (cur.parentElement.hasAttribute('hidden')) {
                cur.parentElement.removeAttribute('hidden');
                cur.parentElement.style.display = 'block';
                cur.parentElement.style.minHeight = '75px';
            }
            cur = cur.parentElement;
        }
    }""")

    # Coordinate click
    rect = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.parentElement?.getBoundingClientRect()")
    if rect and rect.get("height", 0) >= 30:
        click_x = rect["x"] + 35
        click_y = rect["y"] + (rect["height"] / 2)
        await page.mouse.move(click_x, click_y)
        await asyncio.sleep(0.15)
        await page.mouse.click(click_x, click_y)

    # Wait for Turnstile solution
    turnstile_passed = False
    for s in range(12):
        await asyncio.sleep(1)
        tok = await page.evaluate("() => document.querySelector('input[name=\"cf-turnstile-response\"]')?.value")
        if tok and len(tok) > 20:
            print_sub(f"Cloudflare Turnstile solved in {s+1}s! (token len: {len(tok)})")
            turnstile_passed = True
            break

    if not turnstile_passed:
        raise RuntimeError("Cloudflare Turnstile verification timed out")

    # Wait for Continue button to enable
    for _ in range(10):
        await asyncio.sleep(0.5)
        disabled = await page.evaluate("() => Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Continue'))?.disabled")
        if disabled is False:
            break

    print_sub("Submitting registration form...")
    btn = page.locator('button:has-text("Continue")')
    await btn.click()
    await asyncio.sleep(5)

    if not register_result.get("data"):
        err_text = await page.evaluate("() => document.body.innerText")
        for line in err_text.splitlines():
            if "fail" in line.lower() or "error" in line.lower() or "invalid" in line.lower():
                raise RuntimeError(f"Registration failed: {line.strip()}")
        raise RuntimeError("Registration failed or timed out")

    return register_result["data"]


def poll_activation_email(tempmail: TempikClient, email: str, max_wait: int = 40) -> Tuple[str, str]:
    print_step("Step 2: Polling Tempik inbox for confirmation email...")
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            msgs = tempmail.get_messages(email)
            for m in msgs:
                subj = m.get("subject", "")
                if "confirm" in subj.lower() or "respan" in subj.lower():
                    mid = m.get("id")
                    detail = tempmail.get_message_detail(email, mid)
                    body = detail.get("body", "") or detail.get("body_html", "")
                    # Look for /activate/<uid>/<token>
                    match = re.search(r'/activate/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)', body)
                    if match:
                        uid, token = match.group(1), match.group(2)
                        print_sub(f"Found activation token! (uid: {uid}, token: {token[:12]}...)")
                        return uid, token
        except Exception as e:
            print_sub(f"Polling warning: {e}")
        time.sleep(2)
    raise TimeoutError(f"Activation email not received within {max_wait}s")


def activate_account(uid: str, token: str) -> bool:
    print_step("Step 3: Activating account via Respan REST API...")
    req = urllib.request.Request(
        "https://api.respan.ai/auth/users/activation/",
        data=json.dumps({"uid": uid, "token": token}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status in (200, 204):
            print_sub("Account successfully activated (HTTP 204)!")
            return True
    return False


def login_jwt(email: str, password: str) -> Tuple[str, str]:
    print_step("Step 4: Authenticating JWT session...")
    req = urllib.request.Request(
        "https://api.respan.ai/auth/jwt/create/",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode())
        access = res["access"]
        refresh = res["refresh"]
        print_sub(f"JWT access token acquired (len: {len(access)})!")
        return access, refresh


def bootstrap_workspace(access_token: str, user_id: int) -> Tuple[str, str]:
    print_step("Step 5: Bootstrapping workspace & generating gateway key...")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": UA
    }
    payload = {
        "is_span_behaviors_enabled": True,
        "user": user_id,
        "name": "Default project",
        "workspace_name": "Default",
        "organization_size": 1
    }
    req = urllib.request.Request(
        "https://api.respan.ai/user/organizations/",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode())
        onboarding_key = res.get("onboarding_key", "")
        unique_org_id = res.get("unique_organization_id", "")
        print_sub(f"Workspace created! Org ID: {unique_org_id}")
        print_sub(f"Gateway Key: {onboarding_key}")
        return onboarding_key, unique_org_id


def verify_chat_model(api_key: str, model: str = "kimi-k3.1-pro") -> str:
    print_step(f"Step 6: Verifying live chat completion for '{model}'...")
    req = urllib.request.Request(
        "https://api.respan.ai/api/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Tes performa, jawab 1 kata: GAS"}]
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": UA
        },
        method="POST"
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=30) as r:
        elapsed = time.time() - t0
        res = json.loads(r.read().decode())
        reply = res["choices"][0]["message"]["content"].strip()
        print_sub(f"Verified in {elapsed:.2f}s! Reply: '{reply}'")
        return reply


def inject_to_9router(email: str, api_key: str) -> bool:
    print_step("Step 7: Registering gateway connection into 9router...")
    if not os.path.exists(ROUTER_DB_PATH):
        print_sub(f"9router database not found at {ROUTER_DB_PATH}, skipping.")
        return False

    try:
        conn = sqlite3.connect(ROUTER_DB_PATH)
        cur = conn.cursor()

        node_id = "openai-compatible-chat-respan-001"
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        # Ensure node exists
        cur.execute("SELECT id FROM providerNodes WHERE id = ?;", (node_id,))
        if not cur.fetchone():
            node_data = {
                "prefix": "respan",
                "apiType": "chat",
                "baseUrl": "https://api.respan.ai/api",
                "nodeName": "Respan",
                "logo": "",
                "createdAt": now,
                "updatedAt": now
            }
            cur.execute(
                "INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?);",
                (node_id, "openai-compatible", "Respan", json.dumps(node_data), now, now)
            )

        # Insert Connection
        conn_id = str(uuid.uuid4())
        conn_data = {
            "apiKey": api_key,
            "defaultModel": "respan/kimi-k3.1-pro",
            "testStatus": "active",
            "errorCode": None,
            "backoffLevel": 0,
            "providerSpecificData": {
                "prefix": "respan",
                "apiType": "chat",
                "baseUrl": "https://api.respan.ai/api",
                "nodeName": "Respan",
                "connectionProxyEnabled": False,
                "connectionProxyUrl": "",
                "connectionNoProxy": ""
            }
        }
        cur.execute(
            "INSERT INTO providerConnections (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (conn_id, node_id, "apikey", email.split("@")[0], email, 1, 1, json.dumps(conn_data), now, now)
        )
        conn.commit()
        conn.close()
        print_sub("Successfully added to 9router pool under prefix 'respan'!")
        return True
    except Exception as e:
        print_sub(f"Failed to inject into 9router: {e}")
        return False


def save_account_record(rec: Dict[str, Any]):
    with open(ACCOUNTS_FILE, "a") as f:
        f.write(
            f"=== {rec['email']} ===\n"
            f"email        : {rec['email']}\n"
            f"password     : {rec['password']}\n"
            f"user_id      : {rec.get('user_id')}\n"
            f"apikey       : {rec['apikey']}\n"
            f"org_id       : {rec.get('org_id')}\n"
            f"status       : active\n"
            f"model        : kimi-k3.1-pro (10M free tokens/day)\n"
            f"timestamp    : {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
    with open(KEYS_FILE, "a") as f:
        f.write(f"{rec['apikey']}\n")


async def generate_single_account(sync_9router: bool = True) -> Optional[Dict[str, Any]]:
    tempmail = TempikClient()
    username, password = generate_credentials()
    
    # Create inbox with verified corporate domain
    email = tempmail.create_inbox(local_part=username, domain="fantech.tech")
    print(f"\n{'='*60}\nGenerating account: {email}\n{'='*60}")

    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        user_info = await solve_and_register(page, email, password)

    user_id = user_info.get("id")
    uid, token = poll_activation_email(tempmail, email)
    activate_account(uid, token)
    access_token, refresh_token = login_jwt(email, password)
    apikey, org_id = bootstrap_workspace(access_token, user_id)

    # Verify live chat
    reply = verify_chat_model(apikey)

    rec = {
        "email": email,
        "password": password,
        "user_id": user_id,
        "apikey": apikey,
        "org_id": org_id,
        "reply": reply
    }
    save_account_record(rec)

    if sync_9router:
        inject_to_9router(email, apikey)

    print(f"\n[+] Account successfully created and verified!")
    print(f"    API Key: {apikey}")
    return rec


async def main_async(count: int, sync_9router: bool):
    success = 0
    for i in range(count):
        print(f"\n>>> Running Batch Job {i+1} of {count} <<<")
        try:
            res = await generate_single_account(sync_9router=sync_9router)
            if res:
                success += 1
        except Exception as e:
            print(f"[-] Error on job {i+1}: {e}", flush=True)

        if i < count - 1:
            wait_gap = 10
            print(f"\nWaiting {wait_gap}s before next account...")
            await asyncio.sleep(wait_gap)

    print(f"\n{'='*60}\nBatch Summary: {success}/{count} accounts created successfully!\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Respan AI Suite - Kimi K3.1 Pro Farm & 9router Pool")
    parser.add_argument("-n", "--count", type=int, default=1, help="Number of accounts to generate (default: 1)")
    parser.add_argument("--no-9router", action="store_true", help="Skip 9router database injection")
    args = parser.parse_args()

    asyncio.run(main_async(args.count, not args.no_9router))


if __name__ == "__main__":
    main()
