from uuid import UUID
from sqlalchemy.orm import Session

from app.models import User, Business, BusinessUser
from app.auth.security import verify_password


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: UUID):
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, password_hash: str):
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email=email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_business(
    db: Session,
    name: str = "Default Business",
    country_code: str = "BG",
    currency_code: str = "EUR",
    vat_enabled: bool = False,
):
    business = Business(
        name=name,
        country_code=country_code,
        currency_code=currency_code,
        vat_enabled=vat_enabled,
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business


def add_user_to_business(db: Session, business_id: UUID, user_id: UUID, role: str = "admin"):
    link = BusinessUser(business_id=business_id, user_id=user_id, role=role)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def get_first_business_id(db: Session, user_id: UUID):
    link = db.query(BusinessUser).filter(BusinessUser.user_id == user_id).first()
    return link.business_id if link else None