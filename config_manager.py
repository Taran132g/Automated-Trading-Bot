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
