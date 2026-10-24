#!/usr/bin/env python3
"""
Tempik disposable email client for Respan Suite.
Defaults to corporate domains accepted by Respan's work email validation filter.
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Optional, List, Dict, Any

TEMPIK_BASE = os.getenv("TEMPIK_BASE", "https://mail.xentranetwork.me/api").rstrip("/")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

# Respan accepts corporate / tech domains
RESPAN_COMPLIANT_DOMAINS = ["fantech.tech", "mediterranean.biz.id", "ngurah.biz.id"]


class TempikClient:
    """Tempik disposable email API client."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or TEMPIK_BASE).rstrip("/")
        self.session_id: Optional[str] = None

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            "User-Agent": UA,
            "Accept": "application/json",
        }
        if self.session_id:
            headers["x-session-id"] = self.session_id

        encoded_data = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            encoded_data = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return None
            return json.loads(raw)

    def init_session(self) -> str:
        if not self.session_id:
            res = self._request("GET", "/session")
            self.session_id = res.get("sessionId")
        return self.session_id

    def create_inbox(self, local_part: Optional[str] = None, domain: Optional[str] = None) -> str:
        self.init_session()
        payload = {}
        if local_part:
            payload["name"] = local_part
        payload["domain"] = domain or random.choice(RESPAN_COMPLIANT_DOMAINS)

        res = self._request("POST", "/inboxes", payload)
        return res.get("address")

    def get_messages(self, address: str) -> List[Dict[str, Any]]:
        self.init_session()
        try:
            res = self._request("GET", f"/inboxes/{address}/messages")
            return res if isinstance(res, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    def get_message_detail(self, address: str, message_id: str) -> Dict[str, Any]:
        self.init_session()
        res = self._request("GET", f"/inboxes/{address}/messages/{message_id}")
        return res if isinstance(res, dict) else {}
