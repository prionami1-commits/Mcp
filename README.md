# Dana Global MT5 Market MCP (read-only market research)

Remote MCP server for Claude using Streamable HTTP at `/mcp`.

## Important limitations

This project does **not** connect to a Dana Global Limited MT5 account. The official MT5 Android app does not expose a public API for third-party MCP servers to read account balance, equity, positions, or trade history. The broker API is also not available according to the user.

This server therefore provides public market-data and calculation tools only. It cannot place, modify, or close trades.

Market data is retrieved from Yahoo Finance's public chart endpoint. It may be delayed, rate-limited, unavailable for some symbols/timeframes, and different from the quote shown by Dana Global Limited MT5. It is not an official broker feed.

## Tools

- `server_status`
- `get_market_price`
- `get_candles`
- `analyze_market`
- `calculate_position_size`
- `calculate_risk_reward`

Supported aliases include XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, BTCUSD, ETHUSD, USOIL, NAS100, US500, US30.

## Deploy to Render

1. Create a GitHub repository named `dana-global-mt5-mcp`.
2. Upload all files in this project to the repository root (not the ZIP itself).
3. Open https://dashboard.render.com and sign in.
4. Choose **New +** > **Web Service**.
5. Connect GitHub and select `dana-global-mt5-mcp`.
6. Set:
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python server.py`
   - Plan: Free (if available in your account)
7. Deploy and wait until the service status is Live.
8. Your MCP URL will be:
   `https://YOUR-SERVICE-NAME.onrender.com/mcp`

Render free web services may spin down after inactivity and take time to wake up. Check current plan limits before relying on it.

## Connect Claude

In Claude, open Settings > Connectors > Add custom connector (wording can vary), then enter the deployed HTTPS MCP URL ending in `/mcp`. Complete any connection confirmation Claude displays.

## Test

Open `https://YOUR-SERVICE-NAME.onrender.com/` in a browser. The MCP endpoint itself is `/mcp`; a normal browser GET may not display a human-friendly page because it speaks MCP Streamable HTTP.

In Claude, ask it to call `server_status`, then `get_market_price` with `XAUUSD`.

## Security

The server only exposes public market data and mathematical calculators. Do not add MT5 passwords, investor passwords, account credentials, or the earlier `metatrader5://account?credentials=...` value to this repository or Render environment variables.
