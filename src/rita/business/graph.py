"""A thin Microsoft Graph client for Outlook + Teams + Calendar.

API-first (no UI scraping). Auth and HTTP are kept injectable so the client is
testable without network: pass a `session` (a requests.Session-like object with
.get/.post returning objects exposing .status_code and .json()) and a bearer
`token`. `from_env()` wires real auth via MSAL (guarded, opt-in).

Outward-facing actions (send mail, post to Teams) are deliberately NOT bundled
with confirmation here — the plugin layer gates them via the orchestrator's
permission tiers so the policy lives in one place.
"""

from __future__ import annotations

import os

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


class GraphClient:
    def __init__(self, token: str, session=None, base_url: str = GRAPH_BASE,
                 egress=None, vault=None) -> None:
        # `token` may be a 'vault:NAME' reference; resolved here so the raw
        # secret never lives in config or prompts.
        if vault is not None:
            token = vault.resolve(token)
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.egress = egress  # optional security.egress.EgressPolicy
        if session is not None:
            self._session = session
        else:  # pragma: no cover - needs the requests package
            import requests
            self._session = requests.Session()

    # -- auth ---------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "GraphClient":  # pragma: no cover - needs msal + creds
        """Acquire a token via MSAL using env config.

        AICA_GRAPH_CLIENT_ID, AICA_GRAPH_TENANT_ID, and either a device-code or
        client-credentials flow. Least-privilege scopes are requested per use.
        """
        try:
            import msal  # type: ignore
        except Exception as exc:
            raise GraphError("msal not installed (pip install msal)") from exc
        client_id = os.environ.get("RITA_GRAPH_CLIENT_ID",
                                   os.environ.get("AICA_GRAPH_CLIENT_ID"))
        tenant = os.environ.get("RITA_GRAPH_TENANT_ID",
                                os.environ.get("AICA_GRAPH_TENANT_ID", "common"))
        if not client_id:
            raise GraphError("AICA_GRAPH_CLIENT_ID not set")
        authority = f"https://login.microsoftonline.com/{tenant}"
        scopes = ["Mail.ReadWrite", "Mail.Send", "ChannelMessage.Send",
                  "Calendars.ReadWrite"]
        app = msal.PublicClientApplication(client_id, authority=authority)
        flow = app.initiate_device_flow(scopes=scopes)
        print(flow["message"])  # user completes the device-code login
        result = app.acquire_token_by_device_flow(flow)
        token = result.get("access_token")
        if not token:
            raise GraphError(f"auth failed: {result.get('error_description')}")
        return cls(token=token)

    # -- low-level ----------------------------------------------------------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"}

    def _get(self, path: str) -> dict:
        url = self.base_url + path
        if self.egress is not None:
            self.egress.check(url)
        r = self._session.get(url, headers=self._headers())
        if r.status_code >= 400:
            raise GraphError(f"GET {path} -> {r.status_code}")
        return r.json()

    def _post(self, path: str, body: dict | None = None) -> dict:
        url = self.base_url + path
        if self.egress is not None:
            self.egress.check(url)
        r = self._session.post(url, headers=self._headers(), json=body or {})
        if r.status_code >= 400:
            raise GraphError(f"POST {path} -> {r.status_code}")
        return r.json() if (r.text if hasattr(r, "text") else True) else {}

    # -- Outlook mail -------------------------------------------------------
    def list_messages(self, top: int = 10) -> list[dict]:
        data = self._get(
            f"/me/messages?$top={int(top)}"
            "&$select=subject,from,receivedDateTime,bodyPreview,isRead")
        return data.get("value", [])

    def create_draft(self, to: list[str], subject: str, body: str) -> str:
        msg = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }
        return self._post("/me/messages", msg).get("id", "")

    def send_draft(self, message_id: str) -> None:
        self._post(f"/me/messages/{message_id}/send")

    def send_mail(self, to: list[str], subject: str, body: str) -> None:
        self._post("/me/sendMail", {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body},
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            },
            "saveToSentItems": True,
        })

    # -- Teams --------------------------------------------------------------
    def post_channel_message(self, team_id: str, channel_id: str, text: str) -> str:
        body = {"body": {"contentType": "html", "content": text}}
        return self._post(
            f"/teams/{team_id}/channels/{channel_id}/messages", body).get("id", "")

    # -- Calendar -----------------------------------------------------------
    def create_event(self, subject: str, start_iso: str, end_iso: str,
                     attendees: list[str] | None = None, tz: str = "UTC") -> str:
        body = {
            "subject": subject,
            "start": {"dateTime": start_iso, "timeZone": tz},
            "end": {"dateTime": end_iso, "timeZone": tz},
            "attendees": [{"emailAddress": {"address": a}, "type": "required"}
                          for a in (attendees or [])],
        }
        return self._post("/me/events", body).get("id", "")
