import json
from datetime import datetime
import re

alert_times = {}
order_times = {}

date_format_grok = "%Y-%m-%d %H:%M:%S,%f"
date_format_live = "%Y-%m-%d %H:%M:%S,%f"

try:
    with open("grok.log", "r") as f:
        for line in f:
            if "ALERT" in line and "event" in line:
                try:
                    # e.g., 2026-02-27 12:21:45,000 - INFO - {"event": "ALERT", ...
                    parts = line.split(" - INFO - ")
                    if len(parts) != 2:
                        parts = line.split(" - WARNING - ")
                    
                    if len(parts) == 2:
                        ts_str = parts[0]
                        dt = datetime.strptime(ts_str, date_format_grok)
                        data = json.loads(parts[1])
                        sym = data.get("symbol")
                        if sym:
                            if sym not in alert_times:
                                alert_times[sym] = []
                            alert_times[sym].append(dt)
                except Exception as e:
                    pass
except FileNotFoundError:
    print("grok.log not found.")

try:
    with open("live_trader.log", "r") as f:
        for line in f:
            if " [LIVE] " in line and (" BUY " in line or " SHORT " in line or " SELL " in line or " COVER " in line):
                try:
                    # 2026-03-03 16:30:15,150 [INFO] [LIVE] BUY 10 BBAI ...
                    parts = line.split(" [INFO] ")
                    if len(parts) == 2:
                        ts_str = parts[0]
                        dt = datetime.strptime(ts_str, date_format_live)
                        
                        match = re.search(r" (BUY|SHORT|SELL|COVER) \d+ ([A-Z]+) ", parts[1])
                        if match:
                            action = match.group(1)
                            sym = match.group(2)
                            
                            if sym not in order_times:
                                order_times[sym] = []
                            order_times[sym].append((dt, action))
                except Exception as e:
                    pass
except FileNotFoundError:
    print("live_trader.log not found.")

print(f"Parsed {sum(len(v) for v in alert_times.values())} alerts and {sum(len(v) for v in order_times.values())} live orders.")

diffs = []
for sym, o_times in order_times.items():
    a_times = alert_times.get(sym, [])
    for o_dt, action in o_times:
        if action in ["BUY", "SHORT"]: # Entry orders are directly triggered by alerts
            # Find closest previous alert
            prior_alerts = [a for a in a_times if a <= o_dt]
            if prior_alerts:
                closest_alert = max(prior_alerts)
                diff = (o_dt - closest_alert).total_seconds()
                diffs.append((o_dt, sym, diff))

if diffs:
    avg_diff = sum(d for _, _, d in diffs) / len(diffs)
    max_diff = max(d for _, _, d in diffs)
    print(f"Average latency from ALERT to [LIVE] Entry Order: {avg_diff:.4f} seconds")
    print(f"Max latency: {max_diff:.4f} seconds")
    print("\nTop latencies:")
    diffs.sort(key=lambda x: x[2], reverse=True)
    for dt, sym, d in diffs[:10]:
        print(f"  {dt}: {sym} - {d:.4f} s")
else:
    print("Could not find matching pairs of alerts and entry orders.")
