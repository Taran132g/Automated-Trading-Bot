import sys
import os
from dotenv import load_dotenv
load_dotenv()
sys.path.append('.')
from schwab.auth import easy_client

client = easy_client(
    os.getenv('SCHWAB_API_KEY'),
    os.getenv('SCHWAB_API_SECRET'),
    'https://127.0.0.1:8182/'
)
resp = client.get_quote(["BBAI"])
print(resp.json())
