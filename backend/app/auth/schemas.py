from pydantic import BaseModel, EmailStr
from uuid import UUID


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    is_active: bool

    model_config = {"from_attributes": True}