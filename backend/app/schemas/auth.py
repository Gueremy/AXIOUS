"""
app/schemas/auth.py
Schemas Pydantic para autenticación JWT.
"""
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Cuerpo del POST /auth/login"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Respuesta exitosa del login y refresh"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Cuerpo del POST /auth/refresh"""
    refresh_token: str
