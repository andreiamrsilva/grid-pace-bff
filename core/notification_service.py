import os
import logging
from typing import Optional, List
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

# Initialize Firebase app only once
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            # We look for the file in secrets/
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cred_path = os.path.join(base_dir, "secrets", "firebase-adminsdk.json")
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully.")
            else:
                logger.warning(f"Firebase credentials not found at {cred_path}. Push notifications will not work.")
        except Exception as e:
            logger.error(f"Error initializing Firebase Admin SDK: {e}")

initialize_firebase()

def send_topic_notification(topic: str, title: str, body: str, data: Optional[dict] = None) -> bool:
    """Sends a notification to a specific FCM topic."""
    if not firebase_admin._apps:
        logger.warning("Firebase app not initialized. Skipping notification.")
        return False
        
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            topic=topic,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent notification to topic {topic}: {response}")
        return True
    except Exception as e:
        logger.error(f"Error sending notification to topic {topic}: {e}")
        return False

def subscribe_to_topic(tokens: List[str], topic: str) -> bool:
    """Subscribes a list of device tokens to a topic."""
    if not firebase_admin._apps:
        return False
    try:
        response = messaging.subscribe_to_topic(tokens, topic)
        logger.info(f"Subscribed {response.success_count} tokens to topic {topic}")
        return response.success_count > 0
    except Exception as e:
        logger.error(f"Error subscribing to topic {topic}: {e}")
        return False

def unsubscribe_from_topic(tokens: List[str], topic: str) -> bool:
    """Unsubscribes a list of device tokens from a topic."""
    if not firebase_admin._apps:
        return False
    try:
        response = messaging.unsubscribe_from_topic(tokens, topic)
        logger.info(f"Unsubscribed {response.success_count} tokens from topic {topic}")
        return response.success_count > 0
    except Exception as e:
        logger.error(f"Error unsubscribing from topic {topic}: {e}")
        return False

# Domain specific notification helpers

def send_live_stage_notification(category: str, stage_id: int, stage_name: str, event_name: str) -> bool:
    """Sends a notification when a stage/session for any category goes live."""
    topic = f"{category.lower()}_live_stages"
    title = f"{category.upper()} Live: {stage_name}"
    body = f"The {stage_name} at {event_name} is now live! Follow the live times."
    data = {
        "type": f"{category.lower()}_live",
        "stage_id": str(stage_id),
        "event_name": event_name,
        "category": category.upper()
    }
    logger.info(f"[PUSH OUT] Sending LIVE Notification -> Topic: {topic} | Title: {title} | Data: {data}")
    return send_topic_notification(topic, title, body, data)

def send_comment_notification(category: str, event_id: int, message_preview: str) -> bool:
    """Prepared for sending notifications about new comments."""
    topic = f"{category.lower()}_comments"
    title = f"New update on {category.upper()}"
    body = message_preview
    data = {
        "type": f"{category.lower()}_comment",
        "event_id": str(event_id),
        "category": category.upper()
    }
    logger.info(f"[PUSH OUT] Sending COMMENT Notification -> Topic: {topic} | Body: {body} | Data: {data}")
    return send_topic_notification(topic, title, body, data)
