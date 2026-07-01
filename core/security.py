import logging
from fastapi import HTTPException, Security, status
import firebase_admin
from firebase_admin import auth, app_check
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

# Import initialize_firebase to ensure Firebase is loaded
from core.notification_service import initialize_firebase
from core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

async def verify_client_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifies the JWT token from Firebase Authentication.
    """
    token = credentials.credentials
    
    # Ensure Firebase is initialized
    if not firebase_admin._apps:
        initialize_firebase()
        if not firebase_admin._apps:
            logger.error("Firebase is not initialized. Cannot verify tokens.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service is unavailable."
            )

    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except ValueError as e:
        logger.warning(f"Invalid token format: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

app_check_header = APIKeyHeader(name="X-Firebase-AppCheck", auto_error=False)

async def verify_app_check_token(app_check_token: str = Security(app_check_header)):
    """
    Verifies the Firebase App Check token.
    Blocks the request if missing or invalid.
    """
    if not app_check_token:
        logger.warning("Missing App Check token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="App Check token is missing.",
        )
        
    if not firebase_admin._apps:
        initialize_firebase()
        
    try:
        decoded_token = app_check.verify_token(app_check_token)
        return decoded_token
    except ValueError as e:
        logger.warning(f"Invalid App Check token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid App Check token.",
        )
    except Exception as e:
        logger.warning(f"App Check verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="App Check verification failed.",
        )

async def verify_cron_secret(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifies the cron secret token for internal cron jobs.
    """
    token = credentials.credentials
    if not settings.CRON_SECRET:
        logger.warning("CRON_SECRET is not configured in settings. Allowing locally or blocking?")
        # If not configured, we might block to be safe, or allow. We block for safety.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cron secret is not configured on the server."
        )
    
    if token != settings.CRON_SECRET:
        logger.warning("Invalid cron secret provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
