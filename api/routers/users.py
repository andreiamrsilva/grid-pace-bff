from fastapi import APIRouter, Depends
from core.security import verify_client_token
from core.database_service import get_or_create_user, update_user_settings_in_db
from models.user import UserResponse, UserSettingsUpdate, UserSettingsBase

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_current_user(token_data: dict = Depends(verify_client_token)):
    """
    Retrieves the current user's profile and settings.
    If the user does not exist in the database, it creates a new entry with default settings.
    """
    uid = token_data.get("uid")
    email = token_data.get("email")
    
    # get_or_create_user handles the DB interaction
    user = await get_or_create_user(uid, email)
    return user

@router.patch("/me/settings", response_model=UserSettingsBase)
async def update_current_user_settings(
    settings_update: UserSettingsUpdate,
    token_data: dict = Depends(verify_client_token)
):
    """
    Updates the current user's settings.
    """
    uid = token_data.get("uid")
    updated_settings = await update_user_settings_in_db(uid, settings_update)
    return updated_settings
