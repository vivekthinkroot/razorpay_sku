from sqlmodel import SQLModel, Field
from typing import Optional
from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class SKUType(str, Enum):
    BASIC = "basic"
    PREMIUM = "premium"
    GOLD = "gold"
    

class SKU(SQLModel, table=True):
    id: int = Field(primary_key=True) 
    name: str
    sku_id: SKUType
    amount: int  # in paise
    validity: int

class UserSKU(SQLModel, table=True):
    __tablename__ = "usersku"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    sku_id: str = Field(foreign_key="sku.sku_id")
    payment_link_id: str
    amount: int
    status: str = "created"

    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaymentLinkResponse(BaseModel):
    payment_url: str
    payment_link_id: str
    status: str

class PaymentStatusResponse(BaseModel):
    status: str
    payment_link_id: str
    payment_url: str
    
class PaymentLinkRequest(BaseModel):
    user_id: str
    sku_id: str
    
