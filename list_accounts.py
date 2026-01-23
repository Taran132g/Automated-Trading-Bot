import os
import sys
import json
from dotenv import load_dotenv
from schwab.auth import easy_client

def main():
    load_dotenv()
    api_key = os.getenv("SCHWAB_CLIENT_ID")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    redirect_uri = os.getenv("SCHWAB_REDIRECT_URI")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./schwab_tokens.json")

    if not all([api_key, app_secret, redirect_uri]):
        print("Error: Missing environment variables. Please ensure SCHWAB_CLIENT_ID, SCHWAB_APP_SECRET, and SCHWAB_REDIRECT_URI are set in .env")
        return

    try:
        client = easy_client(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=redirect_uri,
            token_path=token_path,
        )
    except Exception as e:
        print(f"Error initializing client: {e}")
        return

    try:
        # Fetch account numbers and hashes specifically
        print("\n--- Fetching Account Numbers & Hashes ---")
        resp_nums = client.get_account_numbers()
        if resp_nums.status_code == 200:
            for acc in resp_nums.json():
                print(f"Account Number: {acc.get('accountNumber')}")
                print(f"Account Hash:   {acc.get('hashValue')}")
        else:
            print(f"Failed to fetch account numbers: {resp_nums.status_code}")

    except Exception as e:
        print(f"Error fetching accounts: {e}")

if __name__ == "__main__":
    main()
