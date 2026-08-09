"""
outlook.py
Send an email via Microsoft Graph API using app-only (client credentials) authentication.

--------------------------------------------------------------------------------
WHY AN APP REGISTRATION IS REQUIRED
--------------------------------------------------------------------------------
Graph API needs to know who's calling and what they're allowed to do before it
lets a script touch mailbox data. The app registration gives this script its own
identity - a Client ID (username) and Client Secret (password) - separate from
the admin personal account.

That identity gets scoped permissions (Mail.Send only, granted via admin consent),
so if the secret ever leaked, the blast radius is "can send mail," not "full
access to admin account." It's also independently revocable - we can kill the
secret or delete the app without touching your own login.

In practice: Tenant ID + Client ID identify the app, the Client Secret is its
password, and Mail.Send + admin consent is its permission slip. This script
trades those for a temporary access token, which is what actually authorizes
the sendMail call below.

--------------------------------------------------------------------------------
SETUP STEPS (one-time, done in portal.azure.com)
--------------------------------------------------------------------------------
1. Create the app registration
   -> Entra ID > App registrations > New registration
   -> Gives the app its identity: copy the Tenant ID and Client ID from Overview

2. Generate the client secret
   -> Certificates & secrets > New client secret > copy the Value immediately
   -> This is the app's "password" used below to request an access token

3. Add the Mail.Send API permission
   -> API permissions > Add a permission > Microsoft Graph > Application
      permissions > Mail.Send > Add permissions
   -> Scopes the app's access to only sending mail, nothing else

4. Click "Grant admin consent"
   -> Still on the API permissions page > Grant admin consent for [org]
   -> Works immediately if you're already an admin - no separate approval
      needed. Without this step, Graph rejects the app's calls with a
      permissions error even though the permission is listed.

Prerequisites:
1. Azure AD (Entra ID) app registration with:
   - API permission: Mail.Send (Application type), with admin consent granted
   - A client secret
2. pip install msal requests

CONFIG SOURCE
--------------------------------------------------------------------------------
MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, and MS_SENDER_EMAIL are read from
the environment (app/.env, loaded by main.py via load_dotenv()).
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import msal
import requests

logger = logging.getLogger(__name__)

SCOPE = ["https://graph.microsoft.com/.default"]


def get_access_token() -> str:
    """
    Acquires an app-only Microsoft Graph access token via client credentials.

    Returns:
        A bearer access token string, valid for Graph API calls.

    Raises:
        KeyError: If MS_TENANT_ID, MS_CLIENT_ID, or MS_CLIENT_SECRET is not set
            in the environment.
        RuntimeError: If MSAL fails to obtain a token (e.g. invalid credentials,
            missing admin consent).
    """
    try:
        tenant_id = os.environ["MS_TENANT_ID"]
        client_id = os.environ["MS_CLIENT_ID"]
        client_secret = os.environ["MS_CLIENT_SECRET"]
    except KeyError as exc:
        raise KeyError(f"Missing required environment variable: {exc}") from exc

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Could not obtain token: {result.get('error_description')}")
    return result["access_token"]


def send_email(
    to_address: str,
    subject: str,
    body: str,
    body_type: str = "Text",
    from_address: str = "james@blackmarlinllc.net",
) -> None:
    """
    Sends an email via Microsoft Graph's sendMail endpoint, on behalf of `from_address`.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        body: Email body content.
        body_type: "Text" or "HTML", matching the format of `body`.
        from_address: Mailbox to send from (must have Mail.Send granted to the app).

    Returns:
        None

    Raises:
        KeyError: If required Graph credentials are missing from the environment.
        RuntimeError: If a token could not be obtained.
        requests.HTTPError: If the Graph API request fails (e.g. bad address, throttling).
    """
    token = get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{from_address}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        },
        "saveToSentItems": "true",
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"Failed to send email to {to_address}: {exc}", response=exc.response
        ) from exc

    logger.info("Email sent to %s (status %s)", to_address, response.status_code)


def get_emails_from_sender(
    sender_address: str, minutes: int, top: int = 10, recipient_address: str = "james@blackmarlinllc.net"
) -> list[dict]:
    """
    Fetches emails from a specific sender received in the last `minutes` minutes,
    most recent first. Requires the Mail.Read (Application) permission with
    admin consent granted, in addition to Mail.Send.

    The receivedDateTime range doubles as what makes server-side $orderby
    valid: Graph only allows sorting on a property that's also in $filter.

    Args:
        sender_address: Email address to filter messages by (the "from" address).
        minutes: How far back, in minutes, to search for messages.
        top: Maximum number of messages to return.
        recipient_address: Mailbox to search (must have Mail.Read granted to the app).

    Returns:
        A list of dicts with subject, from, receivedDateTime, and body, sorted
        by receivedDateTime descending, limited to `top` items.

    Raises:
        KeyError: If required Graph credentials are missing from the environment.
        RuntimeError: If a token could not be obtained.
        requests.HTTPError: If the Graph API request fails.
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://graph.microsoft.com/v1.0/users/{recipient_address}/messages"

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    fmt = "%Y-%m-%dT%H:%M:%SZ"

    filter_clauses = [
        f"from/emailAddress/address eq '{sender_address}'",
        f"receivedDateTime ge {start_time.strftime(fmt)}",
        f"receivedDateTime le {end_time.strftime(fmt)}",
        f"contains(subject, '{os.environ.get('BROKER_BIN_REPORT_SUBJECT')}')",
    ]

    params = {
        "$filter": " and ".join(filter_clauses),
        "$select": "subject,from,receivedDateTime,body",
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"Failed to fetch emails from {sender_address}: {exc}", response=exc.response
        ) from exc

    emails = response.json().get("value", [])
    # sort by receivedDateTime descending (most recent first)
    emails.sort(key=lambda x: x["receivedDateTime"], reverse=True)
    return emails[:min(top, len(emails))]

