import os
import math
from datetime import datetime, timezone
from typing import Any

import requests
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP(
    name="Dana Global MT5 Market MCP",
    instructions=(
        "Read-only market research tools. This server does not connect to a MetaTrader "
        "account, does not read balance or positions, and cannot place trades. "
        "Market quotes are public Yahoo Finance data and may differ from Dana Global "
        "Limited's MT5 prices."
    ),
)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketResearchMCP/1.0)"}

SYMBOLS = {
    "XAUUSD": "XAUUSD=X",
    "GOLD": "XAUUSD=X",
    "XAGUSD": "XAGUSD=X",
    "SILVER": "XAGUSD=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "NZDUSD": "NZDUSD=X",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "USOIL": "CL=F",
    "WTI": "CL=F",
    "NAS100": "NQ=F",
    "US500": "^GSPC",
    "SPX500": "^GSPC",
    "US30": "YM=F",
}

INTERVALS = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "1mo"),
    "30m": ("30m", "1mo"),
    "1h": ("60m", "3mo"),
    "4h": ("60m", "3mo"),
    "1d": ("1d", "1y"),
}


def _resolve_symbol(symbol: str) -> tuple[str, str]:
    key = symbol.strip().upper().replace("/", "").replace("-", "")
    if key in SYMBOLS:
        return key, SYMBOLS[key]
    # Permit Yahoo symbols such as AAPL or user-supplied tickers.
    if not key or len(key) > 30:
        raise ValueError("Simbol tidak valid.")
    return key, symbol.strip()


def _fetch_chart(symbol: str, timeframe: str) -> dict[str, Any]:
    key, yahoo_symbol = _resolve_symbol(symbol)
    tf = timeframe.lower()
    if tf not in INTERVALS:
        raise ValueError("Timeframe tersedia: 1m, 5m, 15m, 30m, 1h, 4h, 1d.")
    interval, period = INTERVALS[tf]
    url = YAHOO_CHART.format(symbol=requests.utils.quote(yahoo_symbol, safe=""))
    response = requests.get(
        url,
        params={"range": period, "interval": interval, "includePrePost": "false"},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(str(chart["error"]))
    result = (chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Tidak ada data untuk {key} ({yahoo_symbol}).")
    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    candles = []
    for i, ts in enumerate(timestamps):
        vals = {}
        for field in ("open", "high", "low", "close", "volume"):
            arr = quote.get(field) or []
            vals[field] = arr[i] if i < len(arr) else None
        if vals["open"] is None or vals["high"] is None or vals["low"] is None or vals["close"] is None:
            continue
        candles.append({
            "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            **{k: (round(float(v), 8) if v is not None else None) for k, v in vals.items()},
        })

    if tf == "4h":
        candles = _aggregate_4h(candles)

    meta = result.get("meta", {})
    return {
        "requested_symbol": key,
        "provider_symbol": yahoo_symbol,
        "currency": meta.get("currency"),
        "exchange_timezone": meta.get("exchangeTimezoneName"),
        "market_state": meta.get("marketState"),
        "candles": candles,
        "source": "Yahoo Finance chart endpoint",
        "disclaimer": (
            "Harga publik indikatif, bukan kuotasi langsung broker Dana Global Limited. "
            "Spread, feed, dan waktu pembaruan dapat berbeda."
        ),
    }


def _aggregate_4h(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Group consecutive hourly candles into 4-hour UTC buckets.
    buckets: dict[str, list[dict[str, Any]]] = {}
    for candle in candles:
        dt = datetime.fromisoformat(candle["time"])
        hour = (dt.hour // 4) * 4
        bucket = dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
        buckets.setdefault(bucket, []).append(candle)
    output = []
    for stamp, group in sorted(buckets.items()):
        output.append({
            "time": stamp,
            "open": group[0]["open"],
            "high": max(x["high"] for x in group),
            "low": min(x["low"] for x in group),
            "close": group[-1]["close"],
            "volume": sum(x.get("volume") or 0 for x in group),
        })
    return output


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(len(values) - period, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    trs = []
    for i in range(1, len(candles)):
        c, prev = candles[i], candles[i - 1]["close"]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return sum(trs[-period:]) / period


@mcp.tool
def get_market_price(symbol: str = "XAUUSD") -> dict:
    """Ambil harga terakhir indikatif untuk XAUUSD, forex, crypto, indeks, atau ticker Yahoo Finance."""
    data = _fetch_chart(symbol, "1m")
    if not data["candles"]:
        raise RuntimeError("Data harga kosong.")
    last = data["candles"][-1]
    previous = data["candles"][-2] if len(data["candles"]) > 1 else None
    change = None
    change_pct = None
    if previous:
        change = last["close"] - previous["close"]
        if previous["close"]:
            change_pct = change / previous["close"] * 100
    return {
        "symbol": data["requested_symbol"],
        "provider_symbol": data["provider_symbol"],
        "last_price": last["close"],
        "last_candle_time_utc": last["time"],
        "change_from_previous_1m": round(change, 8) if change is not None else None,
        "change_percent_from_previous_1m": round(change_pct, 5) if change_pct is not None else None,
        "currency": data["currency"],
        "market_state": data["market_state"],
        "source": data["source"],
        "disclaimer": data["disclaimer"],
    }


@mcp.tool
def get_candles(symbol: str = "XAUUSD", timeframe: str = "15m", limit: int = 100) -> dict:
    """Ambil OHLCV candle. Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d. Batas 300 candle."""
    if limit < 10 or limit > 300:
        raise ValueError("limit harus antara 10 dan 300.")
    data = _fetch_chart(symbol, timeframe)
    candles = data["candles"][-limit:]
    return {
        "symbol": data["requested_symbol"],
        "provider_symbol": data["provider_symbol"],
        "timeframe": timeframe.lower(),
        "count": len(candles),
        "candles": candles,
        "source": data["source"],
        "disclaimer": data["disclaimer"],
    }


@mcp.tool
def analyze_market(symbol: str = "XAUUSD", timeframe: str = "15m", limit: int = 150) -> dict:
    """Hitung SMA20, SMA50, RSI14, ATR14, tren sederhana, dan level support/resistance dari candle publik."""
    if limit < 60 or limit > 300:
        raise ValueError("limit harus antara 60 dan 300.")
    data = _fetch_chart(symbol, timeframe)
    candles = data["candles"][-limit:]
    if len(candles) < 55:
        raise RuntimeError("Data candle tidak cukup untuk analisis SMA50.")
    closes = [c["close"] for c in candles]
    last = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    rsi = _rsi(closes, 14)
    atr = _atr(candles, 14)
    recent = candles[-30:]
    support = min(c["low"] for c in recent)
    resistance = max(c["high"] for c in recent)
    if last > sma20 > sma50:
        trend = "bullish"
    elif last < sma20 < sma50:
        trend = "bearish"
    else:
        trend = "sideways_or_mixed"
    if rsi is not None and rsi >= 70:
        rsi_state = "overbought"
    elif rsi is not None and rsi <= 30:
        rsi_state = "oversold"
    else:
        rsi_state = "neutral"
    return {
        "symbol": data["requested_symbol"],
        "timeframe": timeframe.lower(),
        "last_close": round(last, 8),
        "sma20": round(sma20, 8) if sma20 is not None else None,
        "sma50": round(sma50, 8) if sma50 is not None else None,
        "rsi14": round(rsi, 2) if rsi is not None else None,
        "rsi_state": rsi_state,
        "atr14": round(atr, 8) if atr is not None else None,
        "support_30_candles": round(support, 8),
        "resistance_30_candles": round(resistance, 8),
        "trend_rule": trend,
        "candle_count": len(candles),
        "source": data["source"],
        "disclaimer": (
            data["disclaimer"] + " Indikator bersifat matematis dan bukan kepastian arah harga; "
            "konfirmasi struktur harga dan manajemen risiko tetap diperlukan."
        ),
    }


@mcp.tool
def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    contract_size: float = 100000.0,
) -> dict:
    """Kalkulator ukuran posisi teoretis. Contract size wajib disesuaikan dengan spesifikasi simbol broker."""
    if account_balance <= 0 or entry_price <= 0 or stop_loss_price <= 0 or contract_size <= 0:
        raise ValueError("Semua nilai harus lebih besar dari nol.")
    if not 0 < risk_percent <= 10:
        raise ValueError("risk_percent harus lebih dari 0 dan maksimal 10.")
    distance = abs(entry_price - stop_loss_price)
    if distance == 0:
        raise ValueError("Entry dan Stop Loss tidak boleh sama.")
    risk_amount = account_balance * risk_percent / 100
    units = risk_amount / distance
    lots = units / contract_size
    return {
        "risk_amount_in_account_currency": round(risk_amount, 2),
        "price_distance_to_stop": round(distance, 8),
        "theoretical_units": round(units, 4),
        "theoretical_lots": round(lots, 4),
        "contract_size_used": contract_size,
        "warning": (
            "Perkiraan sederhana. Belum memperhitungkan mata uang profit, nilai tick, "
            "leverage, komisi, swap, slippage, ukuran lot minimum/step, dan spesifikasi kontrak broker. "
            "Verifikasi di kalkulator broker sebelum membuka posisi."
        ),
    }


@mcp.tool
def calculate_risk_reward(
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    direction: str = "BUY",
) -> dict:
    """Hitung jarak risiko, potensi reward, dan rasio risk/reward untuk BUY atau SELL."""
    if min(entry_price, stop_loss_price, take_profit_price) <= 0:
        raise ValueError("Harga harus lebih besar dari nol.")
    side = direction.strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("direction harus BUY atau SELL.")
    if side == "BUY":
        risk = entry_price - stop_loss_price
        reward = take_profit_price - entry_price
    else:
        risk = stop_loss_price - entry_price
        reward = entry_price - take_profit_price
    if risk <= 0 or reward <= 0:
        raise ValueError("Level SL/TP tidak sesuai dengan arah transaksi.")
    return {
        "direction": side,
        "risk_distance": round(risk, 8),
        "reward_distance": round(reward, 8),
        "risk_reward_ratio": round(reward / risk, 3),
        "note": "Rasio ini tidak memperhitungkan spread, komisi, swap, atau slippage.",
    }


@mcp.custom_route("/", methods=["GET"])
async def root_status(request: Request):
    return JSONResponse({"service": "Dana Global MT5 Market MCP", "status": "online", "mcp_endpoint": "/mcp"})


@mcp.tool
def server_status() -> dict:
    """Periksa status MCP server dan cakupan fitur."""
    return {
        "status": "online",
        "server": "Dana Global MT5 Market MCP",
        "mode": "market-analysis-only",
        "broker_account_connection": False,
        "reads_mt5_balance_or_positions": False,
        "places_or_closes_trades": False,
        "market_data_source": "Yahoo Finance chart endpoint",
        "available_timeframes": list(INTERVALS.keys()),
        "available_symbols": sorted(SYMBOLS.keys()),
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
        log_level="INFO",
    )
