from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class CategorySetting(BaseModel):
    name: str
    order: int

class UserSettingsBase(BaseModel):
    categories: List[CategorySetting] = Field(default_factory=list)
    notif_stage_live: bool = True
    notif_stage_comments: bool = True

class UserSettingsUpdate(BaseModel):
    categories: Optional[List[CategorySetting]] = None
    notif_stage_live: Optional[bool] = None
    notif_stage_comments: Optional[bool] = None

class UserBase(BaseModel):
    uid: str
    email: Optional[EmailStr] = None
    is_eternal_pro: bool = False
    subscription_active: bool = False
    subscription_expires_at: Optional[datetime] = None

class UserResponse(UserBase):
    settings: UserSettingsBase

class SubscriptionUpdate(BaseModel):
    is_active: bool
    expires_at: Optional[datetime] = None
