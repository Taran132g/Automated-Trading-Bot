import sys

log_files = [
    ("live_trader.log", "[LIVE]"),
    ("paper_trader.log", "[PAPER]")
]

print("Starting log check for 2026-03-02...")

for log_file, identifier in log_files:
    last_exit_time = {}
    loss_bucket = 0.0
    print(f"--- Parsing {log_file} ---")
    trades_found = False
    try:
        with open(log_file, "r") as f:
            for line_idx, line in enumerate(f):
                if "2026-03-02" not in line:
                    continue
                if identifier not in line:
                    continue
                if " BUY " not in line and " SELL " not in line and " SHORT " not in line and " COVER " not in line:
                    continue
                
                trades_found = True
                parts = line.split()
                side = None
                qty = 0
                symbol = ""
                for i, p in enumerate(parts):
                    if p in ["BUY", "SELL", "SHORT", "COVER"]:
                        side = p
                        qty = int(parts[i+1])
                        symbol = parts[i+2]
                        break
                        
                pnl = 0.0
                try:
                    pnl_idx = line.find("PnL: $")
                    if pnl_idx != -1:
                        end_idx = line.find(" |", pnl_idx)
                        if end_idx == -1: end_idx = len(line)
                        pnl = float(line[pnl_idx + 6 : end_idx].strip())
                except:
                    pass
                
                if side in ["SELL", "COVER"]:
                    last_exit_time[symbol] = line_idx
                    
                    per_share_pnl = 0.0
                    if qty > 0:
                        per_share_pnl = pnl / qty
                    
                    if per_share_pnl < -0.0001:
                        loss_bucket += abs(per_share_pnl)
                        if loss_bucket >= 0.02:
                            print(f"!!! PENALTY BOX LOGIC MET on line {line_idx+1}: {symbol} loss of ${abs(per_share_pnl):.4f} pushed bucket to ${loss_bucket:.4f}")
                            loss_bucket = 0.0 
                    elif per_share_pnl > 0.0001 or abs(per_share_pnl) <= 0.0001:
                        loss_bucket = 0.0
                        
        if not trades_found:
            print("No trades found for 2026-03-02.")
    except Exception as e:
        print(f"Error parsing {log_file}: {e}")
        
print("Finished checking trades.")
