"""Admin controls router."""
import json
import os
import subprocess
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from routers.auth import verify_token

router = APIRouter()
BASE_DIR = Path(__file__).parent.parent.resolve()

# Holds the auth context between /schwab/auth-url and /schwab/save-tokens
_pending_auth_ctx = None
DB_PATH = BASE_DIR / "penny_basing.db"
LIVE_STATE_PATH = BASE_DIR / "live_trader_state_primary.json"
if not LIVE_STATE_PATH.exists():
    LIVE_STATE_PATH = BASE_DIR / "live_trader_state.json"
SCHWAB_TOKEN_PATH = BASE_DIR / "schwab_tokens.json"
MANAGE_SH = BASE_DIR / "manage_backend.sh"


def _load_live_state() -> dict:
    try:
        with open(LIVE_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _is_process_running(name: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", name], capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/status")
def get_admin_status():
    return {
        "loop_running": _is_process_running("restart_loop.sh"),
        "trader_running": _is_process_running("live_trader.py"),
        "grok_running": _is_process_running("grok.py"),
        "paper_running": _is_process_running("paper_trader.py"),
        "token_file_exists": SCHWAB_TOKEN_PATH.exists(),
        "token_file_mtime": SCHWAB_TOKEN_PATH.stat().st_mtime if SCHWAB_TOKEN_PATH.exists() else None,
    }


def _run_manage(action: str) -> dict:
    if not MANAGE_SH.exists():
        return {"success": False, "message": "manage_backend.sh not found"}
    try:
        result = subprocess.run(
            ["bash", str(MANAGE_SH), action],
            capture_output=True, text=True, timeout=30
        )
        return {
            "success": result.returncode == 0,
            "message": result.stdout.strip() or result.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Command timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/start")
def start_backend(_: dict = Depends(verify_token)):
    return _run_manage("start")


@router.post("/stop")
def stop_backend(_: dict = Depends(verify_token)):
    return _run_manage("stop")


@router.post("/flatten")
def flatten_all(_: dict = Depends(verify_token)):
    """Flatten all positions — mirrors Admin_Controls.py flatten logic."""
    state = _load_live_state()
    positions = state.get("positions", {})
    if not positions:
        return {"results": ["No open positions to flatten"], "success": True}

    results = []
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from dotenv import load_dotenv
        load_dotenv()
        import schwab

        token_path = os.getenv("SCHWAB_TOKEN_PATH", str(SCHWAB_TOKEN_PATH))
        client_id = os.getenv("SCHWAB_CLIENT_ID")
        app_secret = os.getenv("SCHWAB_APP_SECRET")
        redirect_uri = os.getenv("SCHWAB_REDIRECT_URI")
        account_id = os.getenv("SCHWAB_ACCOUNT_ID")

        c = schwab.auth.client_from_token_file(token_path, client_id, app_secret)

        for symbol, qty in positions.items():
            if qty == 0:
                continue
            try:
                if qty > 0:
                    order = schwab.orders.equities.market_sell(symbol, abs(qty))
                else:
                    order = schwab.orders.equities.market_buy_to_cover(symbol, abs(qty))
                resp = c.place_order(account_id, order)
                results.append(f"{symbol}: {'OK' if resp.status_code in (200,201) else f'ERROR {resp.status_code}'}")
            except Exception as e:
                results.append(f"{symbol}: ERROR {e}")

        # Clear state
        state["positions"] = {}
        with open(LIVE_STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)

    except Exception as e:
        results.append(f"Flatten error: {e}")

    return {"results": results, "success": True}


@router.post("/full-shutdown")
def full_shutdown(_: dict = Depends(verify_token)):
    stop_result = _run_manage("stop")
    flatten_result = flatten_all()
    return {
        "stop_result": stop_result,
        "flatten_result": flatten_result,
    }


@router.get("/schwab/auth-url")
def get_schwab_auth_url(_: dict = Depends(verify_token)):
    global _pending_auth_ctx
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from dotenv import load_dotenv
        load_dotenv()
        import schwab
        client_id = os.getenv("SCHWAB_CLIENT_ID")
        app_secret = os.getenv("SCHWAB_APP_SECRET")
        redirect_uri = os.getenv("SCHWAB_REDIRECT_URI")
        ctx = schwab.auth.get_auth_context(client_id, app_secret, redirect_uri)
        _pending_auth_ctx = ctx
        return {"authorization_url": ctx.authorization_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaveTokensRequest(BaseModel):
    callback_url: str


@router.post("/schwab/save-tokens")
def save_schwab_tokens(req: SaveTokensRequest, _: dict = Depends(verify_token)):
    global _pending_auth_ctx
    if _pending_auth_ctx is None:
        raise HTTPException(status_code=400, detail="No pending auth context — generate auth URL first")
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from dotenv import load_dotenv
        load_dotenv()
        import schwab
        client_id = os.getenv("SCHWAB_CLIENT_ID")
        app_secret = os.getenv("SCHWAB_APP_SECRET")
        token_path = os.getenv("SCHWAB_TOKEN_PATH", str(SCHWAB_TOKEN_PATH))
        schwab.auth.client_from_received_url(
            req.callback_url, _pending_auth_ctx, client_id, app_secret, token_path
        )
        _pending_auth_ctx = None
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
