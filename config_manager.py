import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Load environment variables as fallback
load_dotenv()

CONFIG_FILE = Path("trading_config.json").resolve()

DEFAULT_CONFIG = {
    "live_symbols": os.getenv("LIVE_SYMBOLS", ""),
    "paper_symbols": os.getenv("SYMBOLS", "AAL,ACHR,BBAI,F,KVUE,PLTR,SOFI"),
    "live_position_size": int(os.getenv("LIVE_POSITION_SIZE", "100")),
    "paper_position_size": int(os.getenv("POSITION_SIZE", "1000")),
    "live_max_trades_per_hour": int(os.getenv("LIVE_MAX_TRADES_PER_HOUR", "60")),
    "account_stop_loss": float(os.getenv("ACCOUNT_STOP_LOSS", "0.0")),
    # Kelly Criterion position sizing
    "kelly_enabled": True,
    "kelly_fraction": 0.5,        # Fractional Kelly (0.5 = half-Kelly reduces variance)
    "kelly_min_trades": 20,       # Min closed trades required to use symbol-level Kelly (DB fallback)
    "kelly_max_multiplier": 2.0,  # Max size multiplier (cap upside)
    "kelly_min_multiplier": 0.25, # Min size multiplier (floor downside)
    "kelly_lookback_days": 30,    # Days of trade history to consider
    # PI-adjusted Kelly: scales multiplier by intraday PnL/share vs neutral
    "pi_neutral": 0.001,          # Neutral PnL/share ($0.001 = breakeven execution quality)
    "pi_kelly_weight": 0.5,       # How aggressively PI shifts the Kelly multiplier (log-scale)
    # Pattern strategy (separate symbol list, position size, and plain Kelly — no PI)
    "pattern_symbols": os.getenv("PATTERN_SYMBOLS", ""),
    "pattern_position_size": int(os.getenv("PATTERN_POSITION_SIZE", "100")),
    "pattern_kelly_enabled": True,
    "pattern_kelly_fraction": 0.5,
    "pattern_kelly_min_trades": 10,
    "pattern_kelly_lookback_days": 30,
    "pattern_kelly_min_multiplier": 0.25,
    "pattern_kelly_max_multiplier": 2.0,
}

def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file, falling back to defaults/env vars."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            saved_config = json.load(f)
            # Merge with defaults to ensure all keys exist
            config = DEFAULT_CONFIG.copy()
            config.update(saved_config)
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_value(key: str, default: Any = None) -> Any:
    """Get a single configuration value."""
    config = load_config()
    return config.get(key, default)
