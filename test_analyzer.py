from trade_analyzer import analyze_trades

data = """
Working Orders
Filled Orders
Date, Time, Action, Quantity, Symbol, Description, Price, Status
 ,, 02/25/2026, 09:30:00 AM, Buy, 100, , AAPL, , , , 150.00, , 0.50, LIMIT
 ,, 02/25/2026, 09:35:00 AM, Sell, 100, , AAPL, , , , 155.00, , 0.20, LIMIT
 ,, 02/25/2026, 09:40:00 AM, Sell Short, 50, , TSLA, , , , 200.00, , -, LIMIT
 ,, 02/25/2026, 09:45:00 AM, Buy to Cover, 50, , TSLA, , , , 190.00, , -, LIMIT
Canceled Orders
"""

print(analyze_trades(data))
