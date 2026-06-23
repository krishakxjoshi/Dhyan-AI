import os
import json
import time

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "sessions.json")
SESSION_EXPIRY_SECONDS = 30 * 60  # 30 minutes

def load_sessions() -> dict:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_sessions(sessions: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2)

def update_session(email: str, chat_history: list) -> dict:
    """
    Creates or updates the session for the given email with current chat history and timestamp.
    If the session is expired (older than 30 minutes), it gets reset.
    """
    sessions = load_sessions()
    now = time.time()
    
    is_new = True
    if email in sessions:
        last_activity = sessions[email].get("last_activity", 0)
        # Check if the session is still valid (within 30 mins)
        if now - last_activity < SESSION_EXPIRY_SECONDS:
            is_new = False
            
    sessions[email] = {
        "email": email,
        "last_activity": now,
        "chat_history": chat_history,
        "is_new_session": is_new
    }
    
    save_sessions(sessions)
    return sessions[email]

def is_session_expired(email: str) -> bool:
    """
    Checks if a session is expired for the email.
    """
    sessions = load_sessions()
    if email not in sessions:
        return True
    last_activity = sessions[email].get("last_activity", 0)
    return (time.time() - last_activity) >= SESSION_EXPIRY_SECONDS
