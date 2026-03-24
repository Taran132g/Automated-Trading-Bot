"""Authentication router: TOTP verify → JWT."""
import os
from datetime import datetime, timedelta, timezone

import pyotp
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

load_dotenv()

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

SECRET_KEY = os.getenv("API_JWT_SECRET", "quant-os-dev-secret-change-in-prod")
ALGORITHM = "HS256"
EXPIRE_DAYS = 30


class LoginRequest(BaseModel):
    totp_code: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


def create_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    totp_secret = os.getenv("TOTP_SECRET")
    if not totp_secret:
        raise HTTPException(status_code=500, detail="TOTP_SECRET not configured")
    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(req.totp_code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
    expires = timedelta(days=EXPIRE_DAYS)
    token = create_token({"sub": "trader"}, expires)
    expires_at = (datetime.now(timezone.utc) + expires).isoformat()
    return LoginResponse(token=token, expires_at=expires_at)


@router.post("/logout")
def logout(_: dict = Depends(verify_token)):
    return {"success": True}


@router.get("/verify")
def verify(_: dict = Depends(verify_token)):
    return {"valid": True}
