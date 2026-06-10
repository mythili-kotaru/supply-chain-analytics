from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import asyncpg
from database import get_db
from auth import verify_password, create_access_token

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str
    full_name: str

@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: asyncpg.Pool = Depends(get_db)):
    # Look up user in DB
    user = await db.fetchrow(
        "SELECT username, password_hash, role, full_name FROM users WHERE username = $1",
        req.username.lower().strip()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
        
    # Generate token
    token_data = {
        "sub": user["username"],
        "role": user["role"],
        "full_name": user["full_name"]
    }
    access_token = create_access_token(token_data)
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"]
    )
