"""Config router."""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from routers.auth import verify_token

BASE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(BASE_DIR))

router = APIRouter()


class TradingConfig(BaseModel):
    live_symbols: str = ""
    paper_symbols: str = ""
    live_position_size: int = 10
    paper_position_size: int = 500
    live_max_trades_per_hour: int = 60
    account_stop_loss: float = 25000.0
    # Kelly Criterion position sizing
    kelly_enabled: bool = True
    kelly_fraction: float = 0.5
    kelly_min_trades: int = 20
    kelly_max_multiplier: float = 2.0
    kelly_min_multiplier: float = 0.25
    kelly_lookback_days: int = 30


class PatternConfig(BaseModel):
    pattern_symbols: str = ""
    pattern_live_position_size: int = 100
    pattern_paper_position_size: int = 1000
    pattern_kelly_enabled: bool = True
    pattern_kelly_fraction: float = 0.5
    pattern_kelly_min_trades: int = 10
    pattern_kelly_lookback_days: int = 30
    pattern_kelly_min_multiplier: float = 0.25
    pattern_kelly_max_multiplier: float = 2.0


PATTERN_KEYS = set(PatternConfig.model_fields.keys())


@router.get("")
def get_config(_: dict = Depends(verify_token)):
    try:
        import config_manager
        cfg = config_manager.load_config()
        return TradingConfig(**cfg)
    except Exception:
        return TradingConfig()


@router.put("")
def update_config(cfg: TradingConfig, _: dict = Depends(verify_token)):
    try:
        import config_manager
        existing = config_manager.load_config()
        existing.update(cfg.model_dump())
        config_manager.save_config(existing)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/pattern")
def get_pattern_config(_: dict = Depends(verify_token)):
    try:
        import config_manager
        cfg = config_manager.load_config()
        return PatternConfig(**{k: cfg[k] for k in PATTERN_KEYS if k in cfg})
    except Exception:
        return PatternConfig()


@router.put("/pattern")
def update_pattern_config(cfg: PatternConfig, _: dict = Depends(verify_token)):
    try:
        import config_manager
        existing = config_manager.load_config()
        existing.update(cfg.model_dump())
        config_manager.save_config(existing)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
