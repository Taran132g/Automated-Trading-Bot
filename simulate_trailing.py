import sqlite3
import json
import glob
from collections import defaultdict
from datetime import datetime

# 1. Get trades with >= 3 cents profit from live_trades
db_path = "penny_basing.db"
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT symbol, side, qty, entry_price, price as exit_price, pnl, timestamp, ROUND(pnl * 1.0 / qty, 4) as cps 
        FROM live_trades 
        WHERE pnl > 0 AND (pnl * 1.0 / qty) >= 0.03
        ORDER BY timestamp ASC
    ''')
    trades = cur.fetchall()
except Exception as e:
    print(f"DB Error: {e}")
    exit(1)

if not trades:
    print("No trades with >= 0.03 CPS found.")
    exit(0)

print(f"Found {len(trades)} trades with >= 3 cents profit...")

symbols_to_track = {t['symbol'] for t in trades}
price_history = defaultdict(list)

def parse_ts(raw_line, brace_pos):
    try:
        prefix = raw_line[:brace_pos]
        dash_info = prefix.find(" - ")
        if dash_info > 0:
            dt_str = prefix[:dash_info].strip()
        else:
            dt_str = prefix.strip()
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()
    except Exception:
        return 0.0

log_files = glob.glob("grok.log*")
print(f"Extracting prices from logs for {symbols_to_track}...")
for log_path in log_files:
    try:
        with open(log_path, "r", errors="replace") as f:
            for line in f:
                if "L1_DEBUG" not in line and "CHART_DEBUG" not in line and "IMBALANCE_DEBUG" not in line and "ROLL" not in line:
                    continue
                brace = line.find("{")
                if brace == -1: continue
                
                try:
                    payload = json.loads(line[brace:])
                    sym = payload.get("symbol")
                    if not sym and "payload" in payload:
                        sym = payload.get("symbol") or payload["payload"].get("key")
                    if not sym and "content" in payload and isinstance(payload["content"], list) and len(payload["content"]) > 0:
                        sym = payload["content"][0].get("key")

                    if not sym or sym not in symbols_to_track: continue
                    
                    price = payload.get("price")
                    if not price and "LAST_PRICE" in payload: price = payload["LAST_PRICE"]
                    if not price and "CLOSE_PRICE" in payload: price = payload["CLOSE_PRICE"]
                    if not price and "payload" in payload:
                        p = payload["payload"]
                        price = p.get("LAST_PRICE", p.get("CLOSE_PRICE", p.get("PRICE")))
                        
                    if price:
                        p_val = float(price)
                        ts = parse_ts(line, brace)
                        if ts > 0:
                            price_history[sym].append((ts, p_val))

                except Exception:
                    pass
    except Exception as e:
        pass

for sym in price_history:
    price_history[sym].sort(key=lambda x: x[0])

print("\n--- TRAILING STOP SIMULATION ($0.03 activate, $0.02 trail) ---")
total_actual = 0
total_simulated = 0

for t in trades:
    sym = t['symbol']
    # Closing trade direction
    direction = "LONG" if t['side'] == "SELL" else "SHORT"
    entry_price = float(t['entry_price'])
    exit_ts = float(t['timestamp'])
    actual_cps = float(t['cps'])
    
    # Try finding true entry time
    cur.execute('''
        SELECT timestamp FROM live_trades 
        WHERE symbol = ? AND side IN ('BUY', 'SHORT') AND timestamp < ?
        ORDER BY timestamp DESC LIMIT 1
    ''', (sym, exit_ts))
    entry_row = cur.fetchone()
    entry_ts = entry_row['timestamp'] if entry_row else exit_ts - 3600
    
    hist = [x for x in price_history[sym] if x[0] >= entry_ts]
    
    activated = False
    highest = entry_price
    simulated_exit_price = None
    
    for ts, px in hist:
        pnl = (px - entry_price) if direction == "LONG" else (entry_price - px)
        
        if direction == "LONG": highest = max(highest, px)
        else: highest = min(highest, px)
        
        if not activated and pnl >= 0.03:
            activated = True
            
        if activated:
            trail_stop = highest - 0.02 if direction == "LONG" else highest + 0.02
            execute = False
            if direction == "LONG" and px <= trail_stop: execute = True
            elif direction == "SHORT" and px >= trail_stop: execute = True
            
            if execute:
                simulated_exit_price = px
                break

    simulated_cps = 0
    if simulated_exit_price:
        simulated_cps = (simulated_exit_price - entry_price) if direction == "LONG" else (entry_price - simulated_exit_price)
    else:
        # If it never hit trailing stop, assume actual manual exit or EOD
        simulated_cps = actual_cps 
    
    diff = simulated_cps - actual_cps
    
    total_actual += actual_cps * t['qty']
    total_simulated += simulated_cps * t['qty']
    
    print(f"[{datetime.fromtimestamp(exit_ts).strftime('%Y-%m-%d %H:%M:%S')}] {sym} {direction} (Qty: {t['qty']})")
    print(f"  Entry: ${entry_price:.4f}  | Actual Exit: ${t['exit_price']:.4f} (+${actual_cps:.4f}/sh)")
    if simulated_exit_price:
        print(f"  Simulated Exit (TS): ${simulated_exit_price:.4f} (+${simulated_cps:.4f}/sh)")
    else:
        print(f"  Simulated Exit (TS): NEVER HIT (Assumed Actual: +${actual_cps:.4f}/sh)")
    print(f"  Difference: {'+' if diff >= 0 else ''}${diff:.4f}/sh -> {'PROFITABLE' if diff > 0 else 'LOSS/LESS PROFIT'}\n")

print(f"Total Actual Profit ($):   ${total_actual:.2f}")
print(f"Total Simulated Profit ($): ${total_simulated:.2f}")
diff_total = total_simulated - total_actual
print(f"Net Difference: {'+' if diff_total >= 0 else ''}${diff_total:.2f}")
