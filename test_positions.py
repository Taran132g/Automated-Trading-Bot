import json
from live_trader import SchwabOrderExecutor

executor = SchwabOrderExecutor()
print('RAW POSITIONS DICT:', executor.fetch_positions())

account_data = executor.client.get_account(executor.account_id, fields=[executor.client.Account.Fields.POSITIONS])
try:
    data = account_data.json()
    print('RAW SCHWAB API RESPONSE:')
    print(json.dumps(data.get('securitiesAccount', {}).get('positions', []), indent=2))
except Exception as e:
    print('Failed to parse:', e)
