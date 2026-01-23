import os
import sys
from dotenv import load_dotenv
from live_trader import SchwabOrderExecutor

def main():
    load_dotenv()
    
    # Initialize executor (live mode)
    try:
        executor = SchwabOrderExecutor(dry_run=False)
    except Exception as e:
        print(f"Failed to initialize executor: {e}")
        return

    symbol = "F"
    qty = 1
    side = "SELL"

    print(f"Attempting to {side} {qty} share of {symbol}...")
    
    # Submit Market Order
    result = executor.submit_market(symbol=symbol, qty=qty, side=side)
    
    print("\n--- Order Result ---")
    print(f"Status Code: {result.get('status_code')}")
    print(f"Order ID:    {result.get('order_id')}")
    print(f"Error:       {result.get('error')}")
    
    if result.get('order_id'):
        print("\nSUCCESS! Order placed.")
    else:
        print("\nFAILURE. Order not placed.")

if __name__ == "__main__":
    main()
