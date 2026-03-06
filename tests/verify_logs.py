import os
import sys

def analyze():
    print("Checking recent_grok.log for Limit Order anomalies...")
    if not os.path.exists("tests/recent_grok.log"):
        print("No recent_grok.log found.")
        return

    try:
        with open("tests/recent_grok.log", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log: {e}")
        return
        
    limit_orders = 0
    skips = 0
    ghost_rechecks = 0
    aggressive_cancels = 0
    boxed_errors = 0
    dedup_stops = 0

    for line in lines:
        if "[LIMIT] Submitting" in line:
            limit_orders += 1
        elif "already pending for" in line and "skipping duplicate" in line:
            dedup_stops += 1
        elif "skip stacking" in line:
            skips += 1
        elif "Aggressively cancelling" in line:
            aggressive_cancels += 1
        elif "Cancel sweep found 0 orders" in line:
             ghost_rechecks += 1
        elif "Boxed Position Error" in line:
             boxed_errors += 1

    print(f"------------ LOG METRICS ------------")
    print(f"Total Limit Orders Submitted: {limit_orders}")
    print(f"Dedup Locks (Prevented Double Submission): {dedup_stops}")
    print(f"Aggressive Cancels Triggered: {aggressive_cancels}")
    print(f"API Delay Ghost Rechecks: {ghost_rechecks}")
    print(f"Boxed Position Errors: {boxed_errors}")
    print(f"Stacking Prevented: {skips}")

if __name__ == "__main__":
    analyze()
