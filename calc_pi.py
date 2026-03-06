import re

data = """,,2/19/26 14:40:33,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.01,MKT
,,2/19/26 14:39:45,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1101,4.1101,.01,LMT
,,2/19/26 14:38:35,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.01,MKT
,,2/19/26 14:33:35,STOCK,SELL,-99,TO OPEN,BBAI,,,STOCK,4.123,4.12303,.30,LMT
,,2/19/26 14:33:35,STOCK,SELL,-1,TO OPEN,BBAI,,,STOCK,4.123,4.12,.30,LMT
,,2/19/26 14:33:03,STOCK,SELL,-100,TO CLOSE,BBAI,,,STOCK,4.125,4.125,.50,MKT
,,2/19/26 14:32:46,STOCK,BUY,+100,TO OPEN,BBAI,,,STOCK,4.11,4.11,-,LMT
,,2/19/26 12:55:38,STOCK,BUY,+100,TO CLOSE,RIG,,,STOCK,6.215,6.215,.50,MKT
,,2/19/26 12:54:46,STOCK,SELL,-100,TO OPEN,RIG,,,STOCK,6.205,6.205,.50,LMT
,,2/19/26 12:52:46,STOCK,SELL,-100,TO CLOSE,RIG,,,STOCK,6.2001,6.2001,.01,MKT
,,2/19/26 12:51:47,STOCK,BUY,+100,TO OPEN,RIG,,,STOCK,6.2099,6.2099,.01,LMT
,,2/19/26 11:55:56,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.01,MKT
,,2/19/26 11:48:33,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1101,4.1101,.01,LMT
,,2/19/26 11:47:33,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.01,MKT
,,2/19/26 11:46:33,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1144,4.1144,.44,LMT
,,2/19/26 11:45:50,STOCK,SELL,-100,TO CLOSE,BBAI,,,STOCK,4.1101,4.1101,.01,MKT
,,2/19/26 11:45:46,STOCK,BUY,+100,TO OPEN,BBAI,,,STOCK,4.11,4.11,-,LMT
,,2/19/26 11:44:56,STOCK,SELL,-100,TO CLOSE,BBAI,,,STOCK,4.1101,4.1101,.01,MKT
,,2/19/26 11:43:33,STOCK,BUY,+100,TO OPEN,BBAI,,,STOCK,4.12,4.12,-,LMT
,,2/19/26 11:41:33,STOCK,SELL,-100,TO CLOSE,BBAI,,,STOCK,4.14,4.14,1.00,MKT
,,2/19/26 11:38:25,STOCK,BUY,+100,TO OPEN,BBAI,,,STOCK,4.12,4.12,-,LMT
,,2/19/26 11:37:52,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1257,4.1257,.43,MKT
,,2/19/26 11:33:17,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.13,4.13,-,LMT
,,2/19/26 11:32:33,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1255,4.1255,.45,MKT
,,2/19/26 11:31:05,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1245,4.1245,.45,LMT
,,2/19/26 11:30:33,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.117,4.117,.30,MKT
,,2/19/26 11:28:34,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1101,4.1101,.01,LMT
,,2/19/26 11:28:02,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1161,4.1161,.39,MKT
,,2/19/26 11:27:08,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1246,4.1246,.46,LMT
,,2/19/26 11:26:33,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1169,4.1169,.31,MKT
,,2/19/26 11:22:08,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1201,4.1201,.01,LMT
,,2/19/26 11:21:37,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1163,4.1163,.37,MKT
,,2/19/26 11:19:39,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.1235,4.1235,.35,LMT
,,2/19/26 11:18:58,STOCK,BUY,+100,TO CLOSE,BBAI,,,STOCK,4.1299,4.1299,.01,MKT
,,2/19/26 11:17:28,STOCK,SELL,-100,TO OPEN,BBAI,,,STOCK,4.125,4.125,.50,LMT
,,2/19/26 11:15:47,STOCK,BUY,+1000,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.10,MKT
,,2/19/26 11:11:33,STOCK,SELL,-1000,TO OPEN,BBAI,,,STOCK,4.1101,4.1101,.10,LMT
,,2/19/26 11:10:08,STOCK,BUY,+1000,TO CLOSE,BBAI,,,STOCK,4.1199,4.1199,.10,MKT
,,2/19/26 11:05:30,STOCK,SELL,-1000,TO OPEN,BBAI,,,STOCK,4.125,4.125,5.00,LMT
,,2/19/26 11:03:57,STOCK,BUY,+750,TO CLOSE,BBAI,,,STOCK,4.1198,4.1198,.15,MKT
,,2/19/26 11:03:39,STOCK,SELL,-750,TO OPEN,BBAI,,,STOCK,4.1201,4.12011,.075,LMT
,,2/19/26 10:59:58,STOCK,BUY,+1000,TO CLOSE,BBAI,,,STOCK,4.1399,4.1399,.10,MKT
,,2/19/26 10:59:33,STOCK,SELL,-1000,TO OPEN,BBAI,,,STOCK,4.1201,4.1201,.10,LMT
,,2/19/26 10:55:49,STOCK,SELL,-1000,TO CLOSE,BBAI,,,STOCK,4.1202,4.1202,.20,MKT
,,2/19/26 10:55:27,STOCK,BUY,+1000,TO OPEN,BBAI,,,STOCK,4.12,4.12,-,LMT
,,2/19/26 10:54:46,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.1199,4.11992,.025,MKT
,,2/19/26 10:53:36,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1224,4.1224,.60,LMT
,,2/19/26 10:51:48,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.1185,4.11848,.375,MKT
,,2/19/26 10:51:32,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1227,4.12272,.675,LMT
,,2/19/26 10:49:50,STOCK,SELL,-250,TO CLOSE,BBAI,,,STOCK,4.1521,4.15208,-,MKT
,,2/19/26 10:48:33,STOCK,BUY,+250,TO OPEN,BBAI,,,STOCK,4.16,4.16,-,LMT
,,2/19/26 10:47:46,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.1686,4.1686,.35,MKT
,,2/19/26 10:47:34,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1728,4.1728,.70,LMT
,,2/19/26 10:46:33,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.1771,4.17712,.725,MKT
,,2/19/26 10:45:50,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1701,4.17008,.025,LMT
,,2/19/26 10:45:06,STOCK,SELL,-250,TO CLOSE,BBAI,,,STOCK,4.1732,4.1732,.80,MKT
,,2/19/26 10:44:35,STOCK,BUY,+250,TO OPEN,BBAI,,,STOCK,4.16,4.16,-,LMT
,,2/19/26 10:42:17,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.167,4.167,.75,MKT
,,2/19/26 10:42:06,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1627,4.16272,.675,LMT
,,2/19/26 10:37:32,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.177,4.177,.75,MKT
,,2/19/26 10:35:18,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1901,4.19008,.025,LMT
,,2/19/26 10:33:33,STOCK,BUY,+250,TO CLOSE,BBAI,,,STOCK,4.1773,4.17728,.675,MKT
,,2/19/26 10:33:03,STOCK,SELL,-250,TO OPEN,BBAI,,,STOCK,4.1735,4.17352,.875,LMT
,,2/19/26 10:32:06,STOCK,SELL,-250,TO CLOSE,BBAI,,,STOCK,4.165,4.165,1.25,MKT
,,2/19/26 10:29:36,STOCK,BUY,+198,TO OPEN,BBAI,,,STOCK,4.1566,4.15662,.6732,LMT
,,2/19/26 10:29:36,STOCK,BUY,+52,TO OPEN,BBAI,,,STOCK,4.16,4.16,.6732,LMT"""

lines = [l.strip() for l in data.strip().split('\n') if l.strip()]

total_pi = 0.0
total_fills = 0
no_pi_count = 0

# PnL tracking via cash flow
# BUY = cash outflow (negative), SELL = cash inflow (positive)
pnl_by_symbol = {}
position_by_symbol = {}
bbai_pi = 0.0
f_pi = 0.0
rig_pi = 0.0
bbai_fills = 0
f_fills = 0
rig_fills = 0

for line in lines:
    parts = line.split(',')
    if len(parts) < 15:
        continue
    
    side = parts[4].strip()
    qty_str = parts[5].strip()
    symbol = parts[7].strip()
    price_str = parts[11].strip()
    pi_str = parts[13].strip()
    total_fills += 1
    
    qty = abs(int(qty_str))
    
    try:
        price = float(price_str)
    except:
        continue
    
    if pi_str == '-' or pi_str == '':
        no_pi_count += 1
        pi_val = 0.0
    else:
        try:
            pi_val = float(pi_str)
        except:
            no_pi_count += 1
            pi_val = 0.0
    
    total_pi += pi_val
    if symbol == 'BBAI':
        bbai_pi += pi_val
        bbai_fills += 1
    elif symbol == 'F':
        f_pi += pi_val
        f_fills += 1
    elif symbol == 'RIG':
        rig_pi += pi_val
        rig_fills += 1
    
    if symbol not in pnl_by_symbol:
        pnl_by_symbol[symbol] = 0.0
        position_by_symbol[symbol] = {'shares_traded': 0}
    
    cash_amount = qty * price
    if side == 'BUY':
        pnl_by_symbol[symbol] -= cash_amount
    elif side == 'SELL':
        pnl_by_symbol[symbol] += cash_amount
    
    position_by_symbol[symbol]['shares_traded'] += qty

print("=" * 50)
print("PRICE IMPROVEMENT SUMMARY (2/19/26)")
print("=" * 50)
print(f"Total Filled Orders: {total_fills}")
print(f"  BBAI: {bbai_fills} fills")
if f_fills > 0:
    print(f"  F:    {f_fills} fills")
if rig_fills > 0:
    print(f"  RIG:  {rig_fills} fills")
print()
print(f"Orders WITH Price Improvement: {total_fills - no_pi_count}")
print(f"Orders WITHOUT Price Improvement: {no_pi_count}")
print()
print(f"BBAI Price Improvement: ${bbai_pi:.2f}")
if f_fills > 0:
    print(f"F Price Improvement:    ${f_pi:.2f}")
if rig_fills > 0:
    print(f"RIG Price Improvement:  ${rig_pi:.2f}")
print(f"GRAND TOTAL PRICE IMPROVEMENT: ${total_pi:.2f}")

print()
print("=" * 50)
print("PNL SUMMARY (Cash Flow Method)")
print("=" * 50)

total_pnl = 0.0
total_shares = 0

for sym in sorted(pnl_by_symbol.keys()):
    pnl = pnl_by_symbol[sym]
    shares = position_by_symbol[sym]['shares_traded']
    pnl_per_share = pnl / shares if shares > 0 else 0
    total_pnl += pnl
    total_shares += shares
    print(f"  {sym}:")
    print(f"    PnL:            ${pnl:>10.2f}")
    print(f"    Shares Traded:  {shares:>10,}")
    print(f"    PnL/Share:      ${pnl_per_share:>10.4f}")
    print()

total_pnl_per_share = total_pnl / total_shares if total_shares > 0 else 0
print(f"  TOTAL:")
print(f"    PnL:            ${total_pnl:>10.2f}")
print(f"    Shares Traded:  {total_shares:>10,}")
print(f"    PnL/Share:      ${total_pnl_per_share:>10.4f}")
