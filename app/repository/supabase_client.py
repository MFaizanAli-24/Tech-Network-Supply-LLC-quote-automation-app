"""
Creates the shared Supabase client used to persist and query part quote
requests, authenticated via a URL + API key pair read from the environment.
"""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

try:
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]
except KeyError as exc:
    raise KeyError(f"{exc.args[0]} is not set in the environment") from exc

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
