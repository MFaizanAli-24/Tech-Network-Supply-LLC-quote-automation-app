"""
WHY (Service Account) IS REQUIRED / USED HERE
------------------------------------------------
This script needs to run unattended (e.g., scheduled job, server, bot)
with no human available to click "Allow" on a login screen.

WHY IT'S NOT USING OAUTH
------------------------------------------------
OAuth requires a real user to log in via browser at least
once, and the resulting token can expire or be revoked, breaking
automation. A Service Account is its own Google identity — it has
its own email address and its own credentials (the JSON key file),
so the script can authenticate every time without any human step.

WHY IT WORKS
------------
Google Sheets access isn't tied to "who is running the code" — it's
tied to "who has this sheet shared with them." A service account is
treated just like a regular Google user for sharing purposes. Once
you share the target spreadsheet with the service account's email
(Viewer or Editor), the service account can read/write it using its
JSON key to prove its identity — exactly like a person logging in,
except it's all done via a private key instead of a password.

SETUP STEPS
------------
1. Create a Google Cloud project
   console.cloud.google.com -> create a new project (or reuse one).

2. Enable the Google Sheets API
   APIs & Services -> Library -> search "Google Sheets API" -> Enable.
   (Also enable "Google Drive API" if you want to list/search files,
   not just read a sheet you already have the ID for.)

3. Create a Service Account
   APIs & Services -> Credentials -> Create Credentials
   -> Service Account. Give it any name. Skip the optional
   "Permissions" / "Principals with access" steps — those grant
   Cloud IAM roles (e.g. Cloud Storage, BigQuery) and are unrelated
   to Google Sheets access, which is controlled by Sheets sharing.

4. Create a key for it
   Open the service account -> Keys tab -> Add Key -> Create new key
   -> JSON. This downloads a .json file. Treat it like a password —
   never commit it to source control or share it publicly.

5. Share the Google Sheet with the service account
   Open the downloaded JSON and find the "client_email" field
   (looks like something@project-id.iam.gserviceaccount.com).
   Go to the actual Google Sheet -> Share -> paste that email in
   -> give it Viewer (or Editor if the script needs to write too).
   Without this step, the API call below will fail with a 403,
   even though the credentials themselves are valid.

CONFIG SOURCE
------------
GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE are read from the
environment (app/.env, loaded by main.py via load_dotenv()).
GOOGLE_SERVICE_ACCOUNT_FILE is resolved relative to the app/ folder,
so a value like "credentials/service_account_key.json" in .env works
no matter which directory the process is launched from.
"""

import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# app/ directory (two levels up from this file: app/integrations/google/).
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Read-only scope. Use "https://www.googleapis.com/auth/spreadsheets"
# instead if the sheet is shared as Editor and you need to write data too.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          # write access scope, if you need to write to the sheet:
          "https://www.googleapis.com/auth/spreadsheets"]


def get_sheet_values(sheet_id: str, range_name: str = "Sheet1") -> list[list[str]]:
    """
    Reads all values from a range of a Google Sheet using the service account
    credentials configured via GOOGLE_SERVICE_ACCOUNT_FILE.

    Args:
        sheet_id: The Google Sheet's spreadsheet ID (from its URL).
        range_name: The A1 notation range (e.g. sheet/tab name) to read.

    Returns:
        A list of rows, each a list of cell values as strings. The first row
        is the header row. Empty if the range has no data.

    Raises:
        KeyError: If GOOGLE_SERVICE_ACCOUNT_FILE is not set in the environment.
        FileNotFoundError: If the service account key file does not exist.
        RuntimeError: If the Google Sheets API call fails (e.g. bad sheet_id,
            sheet not shared with the service account, network error).
    """
    try:
        service_account_file = os.path.join(APP_DIR, os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
    except KeyError as exc:
        raise KeyError("GOOGLE_SERVICE_ACCOUNT_FILE is not set in the environment") from exc

    if not os.path.isfile(service_account_file):
        raise FileNotFoundError(f"Service account key file not found: {service_account_file}")

    try:
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Failed to read Google Sheet with SheetId: '{sheet_id}' and Range '{range_name}': {exc}") from exc

    return result.get("values", [])


def write_sheet_values(sheet_id: str, range_name: str, values: list[list[str]]) -> None:
    """
    Writes values to a range of a Google Sheet using the service account
    credentials configured via GOOGLE_SERVICE_ACCOUNT_FILE.

    Args:
        sheet_id: The Google Sheet's spreadsheet ID (from its URL).
        range_name: The A1 notation range (e.g. sheet/tab name) to write to.
        values: A list of rows, each a list of cell values as strings.

    Raises:
        KeyError: If GOOGLE_SERVICE_ACCOUNT_FILE is not set in the environment.
        FileNotFoundError: If the service account key file does not exist.
        RuntimeError: If the Google Sheets API call fails (e.g. bad sheet_id,
            sheet not shared with the service account, network error).
    """
    try:
        service_account_file = os.path.join(APP_DIR, os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
    except KeyError as exc:
        raise KeyError("GOOGLE_SERVICE_ACCOUNT_FILE is not set in the environment") from exc

    if not os.path.isfile(service_account_file):
        raise FileNotFoundError(f"Service account key file not found: {service_account_file}")

    try:
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds)
        body = {"values": values}
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id, range=range_name, valueInputOption="RAW", body=body
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"Failed to write to Google Sheet with SheetId: '{sheet_id}' and Range '{range_name}': {exc}") from exc
