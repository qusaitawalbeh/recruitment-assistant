import os
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _config_path(variable, default):
    path = Path(os.getenv(variable, default)).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_PATH = _config_path("GMAIL_CREDENTIALS_PATH", "credentials/credentials.json")
TOKEN_PATH = _config_path("GMAIL_TOKEN_PATH", "credentials/token.json")


def get_credentials():
    creds = None


    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)


    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  

        if not creds or not creds.valid:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Gmail OAuth setup is required. Download a Desktop app OAuth client JSON "
                    f"from Google Cloud and save it to: {CREDENTIALS_PATH}. "
                    "Enable Gmail API and add your Gmail account as a test user if the app "
                    "is in testing mode. This file is not your Gmail password or an API key."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)


        os.makedirs(os.path.dirname(os.path.abspath(TOKEN_PATH)), exist_ok=True)
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_gmail_service():
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds)
