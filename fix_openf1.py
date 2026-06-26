import re

with open("ingestion/openf1_client.py", "r") as f:
    content = f.read()

# 1. Update tenacity import
content = content.replace(
    "from tenacity import retry, stop_after_attempt, wait_exponential",
    "from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception"
)

# 2. Add is_retryable_exception and replace fetch_json_with_retry
new_fetch = """def is_retryable_exception(exception: BaseException) -> bool:
    import httpx
    if isinstance(exception, httpx.HTTPStatusError):
        if exception.response.status_code in (401, 403):
            return False
    return True

def handle_openf1_exception(e: Exception, logger, context_msg: str):
    import httpx
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
        logger.warning(f"OpenF1 API access restricted ({e.response.status_code}) during live session. {context_msg}")
    else:
        logger.error(f"{context_msg}: {e}")

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=2, max=10), 
    reraise=True,
    retry=retry_if_exception(is_retryable_exception)
)"""

content = content.replace(
    "@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)",
    new_fetch
)

# 3. Replace all logger.error(...) with handle_openf1_exception
patterns = [
    (r'logger\.error\(f"Error fetching F1 calendar events for year \{year\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 calendar events for year {year}")'),
     
    (r'logger\.error\(f"Error fetching F1 sessions for meeting \{meeting_key\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 sessions for meeting {meeting_key}")'),
     
    (r'logger\.error\(f"Error fetching final times for F1 session \{session_key\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching final times for F1 session {session_key}")'),
     
    (r'logger\.error\(f"Error fetching F1 overall standings for meeting \{meeting_key\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 overall standings for meeting {meeting_key}")'),
     
    (r'logger\.error\(f"Error fetching F1 championship standings for year \{year\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 championship standings for year {year}")'),
     
    (r'logger\.error\(f"Error fetching F1 team championship standings for year \{year\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 team championship standings for year {year}")'),
     
    (r'logger\.error\(f"Error fetching F1 race control messages for session \{session_key\}: \{e\}"\)',
     r'handle_openf1_exception(e, logger, f"Error fetching F1 race control messages for session {session_key}")')
]

for old, new in patterns:
    content = re.sub(old, new, content)

with open("ingestion/openf1_client.py", "w") as f:
    f.write(content)

print("done")
