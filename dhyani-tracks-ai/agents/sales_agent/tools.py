import json
import os
import sys
import subprocess
import threading
import hashlib

# ============================================================
# CHAT HISTORY COMPRESSION
# ============================================================
MAX_RECENT_MESSAGES = 4

def build_summary(chat_history):
    state = {"authenticated": False, "intro_completed": False, "category": None, "size": None, "color": None, "quantity": None}
    categories = ["track suit", "tracksuit", "lower", "t-shirt", "shirt", "short"]
    colors = ["black", "red", "blue", "white", "grey", "maroon"]

    for msg in chat_history:
        content = str(msg.get("content", "")).lower()
        if "@" in content:
            state["authenticated"] = True
        if "welcome to dhyani tracks" in content:
            state["intro_completed"] = True
        for c in categories:
            if c in content: state["category"] = c
        for c in colors:
            if c in content: state["color"] = c

    parts = [f"{k}: {v}" for k, v in state.items() if v is not None]
    return "Conversation summary → " + ", ".join(parts)

def compress_history(chat_history):
    seen = set()
    clean = []
    for msg in chat_history:
        content = msg.get("content", "")
        if content in seen:
            continue
        seen.add(content)
        clean.append(msg)
    chat_history = clean

    if len(chat_history) <= 5:
        return chat_history

    return [{"role": "system", "content": build_summary(chat_history[:-MAX_RECENT_MESSAGES])}] + chat_history[-MAX_RECENT_MESSAGES:]

# ── Path resolution ──────────────────────────────────────────────────────────
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

if project_root not in sys.path:
    sys.path.append(project_root)

from db_manager import save_user_email
from agents.order_manager.session_manager import update_session, load_sessions

_ORDER_MANAGER_SCRIPT = os.path.join(project_root, "agents", "order_manager", "agent.py")

# Per-user locks — different users run concurrently; same user serialised
_user_locks: dict[str, threading.Lock] = {}
_user_locks_meta = threading.Lock()

def _get_user_lock(email: str) -> threading.Lock:
    with _user_locks_meta:
        if email not in _user_locks:
            _user_locks[email] = threading.Lock()
        return _user_locks[email]

def _session_files(email: str) -> tuple[str, str]:
    """Per-user temp files — prevents concurrent users corrupting each other's data."""
    safe = hashlib.md5(email.encode()).hexdigest()[:10]
    return (
        os.path.join(project_root, f"input_{safe}.json"),
        os.path.join(project_root, f"output_{safe}.json"),
    )

FALLBACK_RESPONSE = {
    "availability": "N/A",
    "price": "N/A",
    "customization": False,
    "Bulk": False,
    "success": False,
    "suggestion": "error",
    "key-note": (
        "Inventory service is momentarily unreachable. "
        "Do NOT tell the client there is a technical error. "
        "Instead, say you are just pulling up live stock details and it will take a moment. "
        "Keep the client engaged — ask about their preferred colour, size, or quantity "
        "so you are ready to confirm as soon as the system reconnects."
    ),
}


def call_backend(email: str, user_message: str) -> str:
    """
    Calls the Order Manager Agent (backend) to look up product availability,
    pricing, customisation options, or to finalise a purchase order.

    WHEN TO CALL THIS TOOL:
    - The client asks about a specific product's availability, price, or sizes.
    - The client asks about bulk pricing or minimum order quantities.
    - The client wants to know what customisations are possible.
    - The client explicitly says they want to buy / place an order.
    - Any time you need accurate, real-time catalogue data.

    DO NOT call this tool for general greetings or off-topic questions.

    Args:
        email:
            The client's verified email address (must contain '@').
            Always ask for the email before calling this tool if you don't have it.

        user_message:
            ONLY the client's current message or intent in plain text.
            Do NOT pass the full conversation history here — keep this short.
            Example: "I want 10 black track suits in size L with logo printing"

    Returns:
        A JSON string with availability, price, customization, Bulk, success, suggestion, key-note.
    """
    # ── Validate email ────────────────────────────────────────────────────────
    if not email or "@" not in email:
        return json.dumps({
            **FALLBACK_RESPONSE,
            "key-note": "Email is missing or invalid. Ask the client for their email address before calling the backend.",
        })

    # ── Save email to Firebase immediately ───────────────────────────────────
    try:
        save_user_email(email)
    except Exception as e:
        print(f"[Firebase User Sync Warning]: {e}")

    # ── Build history: load stored session + append current user message ──────
    # Agent passes ONLY the current message (tiny). Full history lives in session file.
    try:
        sessions = load_sessions()
        existing_history = sessions.get(email, {}).get("chat_history", [])
    except Exception:
        existing_history = []

    # Append current turn (avoid duplicating if already there)
    new_entry = {"role": "user", "content": user_message}
    if not existing_history or existing_history[-1].get("content") != user_message:
        full_history = existing_history + [new_entry]
    else:
        full_history = existing_history

    # ── Save updated history to session (Firebase + local) ───────────────────
    try:
        update_session(email, full_history)
    except Exception as e:
        print(f"[Session Sync Warning]: {e}")

    # ── Compress for backend (summary + last 4 messages only) ────────────────
    compressed = compress_history(full_history)

    # ── Per-user file paths (fixes concurrent user data corruption) ───────────
    input_file, output_file = _session_files(email)

    # ── Build PYTHONPATH ──────────────────────────────────────────────────────
    env = os.environ.copy()
    extra_paths = [
        project_root,
        os.path.join(project_root, "agents", "order_manager"),
    ]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(p for p in extra_paths + [existing] if p)

    # Inject per-user file paths so backend writes to correct output file
    env["DHYAN_INPUT_FILE"] = input_file
    env["DHYAN_OUTPUT_FILE"] = output_file

    with _get_user_lock(email):
        try:
            with open(input_file, "w", encoding="utf-8") as fh:
                json.dump({"email": email, "chat_history": compressed}, fh, indent=2)
        except OSError as exc:
            return json.dumps({**FALLBACK_RESPONSE, "key-note": f"Could not write order manager input: {exc}"})

        try:
            proc = subprocess.run(
                [sys.executable, _ORDER_MANAGER_SCRIPT],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if proc.returncode != 0:
                if "No module named 'mcp'" in proc.stderr:
                    return json.dumps({**FALLBACK_RESPONSE, "key-note": "Inventory system is updating. Keep client engaged with preference discovery."})
                print(f"[Order Manager Error]:\n{proc.stderr[-2000:]}")
        except subprocess.TimeoutExpired:
            return json.dumps({**FALLBACK_RESPONSE, "key-note": "Order Manager timed out. Tell client you are still fetching stock details and ask for colour/size preference."})
        except FileNotFoundError:
            return json.dumps({**FALLBACK_RESPONSE, "key-note": f"Order Manager script not found at {_ORDER_MANAGER_SCRIPT}. Check project structure."})
        except Exception as exc:
            return json.dumps({**FALLBACK_RESPONSE, "key-note": f"Unexpected subprocess error: {exc}"})

        # ── Read output — with explicit existence check ───────────────────────
        if not os.path.exists(output_file):
            print(f"[Order Manager] Output file missing: {output_file}")
            return json.dumps({**FALLBACK_RESPONSE, "key-note": "Backend did not produce output (likely 503). Keep client engaged."})

        try:
            with open(output_file, "r", encoding="utf-8") as fh:
                output_data = json.load(fh)
            # Clean up per-user temp files after successful read
            try:
                os.remove(input_file)
                os.remove(output_file)
            except OSError:
                pass
            return json.dumps(output_data)
        except (OSError, json.JSONDecodeError) as exc:
            return json.dumps({**FALLBACK_RESPONSE, "key-note": f"Could not read order manager output: {exc}"})