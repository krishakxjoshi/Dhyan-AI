import json
import os
import sys
import subprocess
import threading

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
    # ── Deduplicate History ──────────────────────────────────────────────────
    seen = set()
    clean = []
    for msg in chat_history:
        content = msg.get("content", "")
        if content in seen:
            continue
        seen.add(content)
        clean.append(msg)
    chat_history = clean

    # ── Compress Remaining History ───────────────────────────────────────────
    if len(chat_history) <= 5:
        return chat_history
        
    return [{"role": "system", "content": build_summary(chat_history[:-MAX_RECENT_MESSAGES])}] + chat_history[-MAX_RECENT_MESSAGES:]

# ── Path resolution ──────────────────────────────────────────────────────────
# sales_agent/ lives two levels below the project root (dhyan-tracks-ai/)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

if project_root not in sys.path:
    sys.path.append(project_root)

from db_manager import save_user_email
from agents.order_manager.session_manager import update_session

# Paths used by the order manager
_ORDER_MANAGER_SCRIPT = os.path.join(project_root, "agents", "order_manager", "agent.py")
_INPUT_FILE = os.path.join(project_root, "input.json")
_OUTPUT_FILE = os.path.join(project_root, "output.json")

# Lock protects the shared input/output files during testing
_backend_lock = threading.Lock()

# Mirror of the order manager's own fallback so we don't need to import it
FALLBACK_RESPONSE = {
    "availability": "N/A",
    "price": "N/A",
    "customization": False,
    "Bulk": False,
    "success": False,
    "suggestion": "error",
    "key-note": (
        "Service is temporarily unavailable due to usage limits. "
        "Try again after a few hours."
    ),
}


def call_backend(email: str, chat_history_json: str) -> str:
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

        chat_history_json:
            The COMPLETE conversation history encoded as a JSON string.
            Format exactly like this (include both sides of the conversation):
            '[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]'
            Pass the full history every time — the backend needs it to decide what to do.

    Returns:
        A JSON string with the following keys:
            availability  – product availability info
            price         – detailed price breakdown string
            customization – true if the client requested customisation
            Bulk          – true if this is a bulk order
            success       – true ONLY if a purchase email was successfully sent
            suggestion    – list of suggestions for you (the sales agent) to act on
            key-note      – brief internal directive for you to follow
    """
    # ── Validate email ────────────────────────────────────────────────────────
    if not email or "@" not in email:
        return json.dumps({
            **FALLBACK_RESPONSE,
            "key-note": (
                "Email is missing or invalid. "
                "Ask the client for their email address before calling the backend."
            ),
        })
    try:
        save_user_email(email)
    except Exception as e:
        print(f"[Firebase Sync Warning]: {e}")

    # ── Parse chat history ────────────────────────────────────────────────────
    try:
        chat_history = json.loads(chat_history_json) if isinstance(chat_history_json, str) else list(chat_history_json)
        # Backend owns session/history management.
        # Frontend forwards raw history.
        pass
        if not isinstance(chat_history, list):
            raise ValueError("chat_history must be a list")
    except (json.JSONDecodeError, TypeError, ValueError):
        # Graceful fallback: treat the raw string as a single user message
        chat_history = [{"role": "user", "content": str(chat_history_json)}]

    # ── Build PYTHONPATH so the order manager resolves its own imports ─────────
    # The order manager uses bare `import session_manager` and
    # `from mail_tool import send_order_email`, both of which need
    # their respective directories on PYTHONPATH.
    env = os.environ.copy()
    extra_paths = [
        project_root,                                                   # for mail_tool/
        os.path.join(project_root, "agents", "order_manager"),          # for session_manager
    ]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(p for p in extra_paths + [existing] if p)

    # ── Write input, run order manager, read output (serialised by lock) ──────
    with _backend_lock:
        # 1. Write input.json
        try:
            with open(_INPUT_FILE, "w", encoding="utf-8") as fh:
                json.dump({"email": email, "chat_history": chat_history}, fh, indent=2)
        except OSError as exc:
            return json.dumps({
                **FALLBACK_RESPONSE,
                "key-note": f"Could not write order manager input: {exc}",
            })

        # 2. Run the order manager script as a subprocess.
        #    cwd=project_root is critical — the MCP server path in build_agent()
        #    is relative ("mcp_server/server.py") and must resolve from here.
        try:
            proc = subprocess.run(
                [sys.executable, _ORDER_MANAGER_SCRIPT],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,        # 3 minutes; order manager may do several LLM calls
            )
            if proc.returncode != 0:
                if "No module named 'mcp'" in proc.stderr:
                    return json.dumps({**FALLBACK_RESPONSE, "key-note": "Inventory system is updating. Please retry shortly."})
                print(proc.stderr[-2000:])
        except subprocess.TimeoutExpired:
            return json.dumps({
                **FALLBACK_RESPONSE,
                "key-note": "Order Manager timed out. Advise the client to try again.",
            })
        except FileNotFoundError:
            return json.dumps({
                **FALLBACK_RESPONSE,
                "key-note": (
                    f"Order Manager script not found at {_ORDER_MANAGER_SCRIPT}. "
                    "Check the project structure."
                ),
            })
        except Exception as exc:
            return json.dumps({
                **FALLBACK_RESPONSE,
                "key-note": f"Unexpected subprocess error: {exc}",
            })

        # 3. Read output and safely execute Cloud Sync on success
        try:
            with open(_OUTPUT_FILE, "r", encoding="utf-8") as fh:
                output_data = json.load(fh)

            return json.dumps(output_data)

        except (OSError, json.JSONDecodeError) as exc:
            return json.dumps({
                **FALLBACK_RESPONSE,
                "key-note": f"Could not read order manager output: {exc}",
            })