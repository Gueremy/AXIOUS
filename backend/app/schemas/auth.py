"""
app/schemas/auth.py
Schemas Pydantic para autenticación JWT.
"""
import re
from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Debe incluir al menos una mayúscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Debe incluir al menos una minúscula")
        if not re.search(r"\d", v):
            raise ValueError("Debe incluir al menos un número")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Debe incluir al menos un carácter especial")
        return v
