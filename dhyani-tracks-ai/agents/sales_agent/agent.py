import os
import json
import time
from itertools import cycle
from dotenv import load_dotenv
from google.adk.agents import Agent
from .tools import call_backend
from google.genai.errors import ServerError, APIError # Added explicit APIError handling
from google.genai import types
import asyncio
from google.adk.models import Gemini  # Import the model adapter class

load_dotenv()

# ============================================================
# API KEY + MODEL ROUTER
# ============================================================

def load_api_keys():
    env_names = ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]
    keys = list(dict.fromkeys(filter(None, (os.getenv(env) for env in env_names))))
    if not keys:
        raise RuntimeError("No Gemini API keys found")
    return keys

API_KEYS = load_api_keys()
KEY_POOL = cycle(API_KEYS)

def rotate_api_key():
    key = next(KEY_POOL)
    os.environ["GEMINI_API_KEY"] = key
    os.environ.pop("GOOGLE_API_KEY", None)
    print("[DHYAN] API key rotated")
    return key

# PRODUCTION UPDATE: Removed deprecated 1.5 models. 
# Placed 3.1-flash-lite-preview as high-availability fallback for free quota constraints.
MODELS = ["gemini-2.5-flash", "gemini-3.1-flash-lite-preview"]
CURRENT_MODEL = 0
MODEL_COOLDOWN = {}
COOLDOWN_SECONDS = 60

def mark_failed(model):
    MODEL_COOLDOWN[model] = time.time() + COOLDOWN_SECONDS

def is_available(model):
    return MODEL_COOLDOWN.get(model, 0) < time.time()

def rotate_model():
    global CURRENT_MODEL
    for _ in range(len(MODELS)):
        CURRENT_MODEL = (CURRENT_MODEL + 1) % len(MODELS)
        candidate = MODELS[CURRENT_MODEL]
        if is_available(candidate):
            print(f"[DHYAN] Switched → {candidate}")
            return candidate
    # All in cooldown — reset and use primary
    print("[DHYAN] All models in cooldown, resetting")
    MODEL_COOLDOWN.clear()
    CURRENT_MODEL = 0
    return MODELS[0]

def current_model():
    return MODELS[CURRENT_MODEL]

rotate_api_key()
print(f"[DHYAN] Active model → {current_model()}")

# ============================================================
# LOAD SYSTEM PROMPT & ERROR DETECTION
# ============================================================
prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.txt")
with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()

RETRY_ERRORS = ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED"]

def is_retryable(exc):
    # PRODUCTION UPDATE: Extract explicit status codes from native APIError if applicable
    if isinstance(exc, APIError):
        if exc.code in [429, 503, 504]:
            return True
    text = str(exc).upper()
    return any(x in text for x in RETRY_ERRORS)

def is_quota_error(exc):
    if isinstance(exc, APIError) and exc.code == 429:
        return True
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text

def is_overload(exc):
    if isinstance(exc, APIError) and exc.code == 503:
        return True
    text = str(exc)
    return "503" in text or "UNAVAILABLE" in text

# ============================================================
# RESILIENT AGENT FACTORY & ORCHESTRATION
# ============================================================

MAX_RETRIES = 3

def build_agent():
    model_name = current_model()
    print(f"[DHYAN] Loading {model_name} with native client retries")
    
    # Wrap the string model identifier into a Gemini adapter configured with retries
    model_adapter = Gemini(
        model=model_name,
        retry_options=types.HttpRetryOptions(initial_delay=2, attempts=3),
    )
    
    return Agent(
        name="sales_agent",
        model=model_adapter,  # Pass the configured object instead of a string
        tools=[call_backend],
        instruction=system_prompt,
    )

root_agent = None

async def safe_build_agent():
    global root_agent
    retries = len(MODELS) * len(API_KEYS)
    for attempt in range(retries):
        try:
            root_agent = build_agent()
            return root_agent
        except Exception as exc:
            print(f"[BUILD {attempt+1}] {exc}")
            if is_retryable(exc):
                rotate_api_key()
                mark_failed(current_model())
                rotate_model()
                await asyncio.sleep(min(2**attempt, 10))
                continue
            raise
    raise RuntimeError("All model attempts exhausted")

async def invoke_with_retry(invoke_fn):
    global root_agent
    last = None
    for retry in range(MAX_RETRIES):
        try:
            if root_agent is None:
                await safe_build_agent()
            return await invoke_fn()
        except Exception as exc:
            last = exc
            print(f"[RETRY {retry+1}] {exc}")
            if not is_retryable(exc):
                raise
            rotate_api_key()
            mark_failed(current_model())
            rotate_model()
            root_agent = build_agent()
            await asyncio.sleep(min(2**retry, 12))
    raise last

async def get_root_agent():
    global root_agent
    if root_agent is None:
        await safe_build_agent()
    return root_agent

# ============================================================
# RESPONSE GUARDRAIL
# ============================================================

_LEAK_MARKERS = [
    "system instructions", "internal logic", "hidden instructions",
    "tool payload", "backend response",
    "you are dhyan", "dhyan ai —", "frontend sales agent",
    "mandatory conversation flow", "step 1 —", "step 2 —",
    "step 3 —", "step 4 —", "step 5 —",
    "language policy", "strict guardrails",
]

_CONNECT_FALLBACK = (
    "I'm experiencing a brief delay reconnecting to our inventory system. "
    "While I sort that out — could you tell me what you're looking for? "
    "Track suits, lowers, T-shirts, or shorts? And do you have a preferred colour or size in mind?"
)

def guardrail_check(response_text):
    if isinstance(response_text, str) and response_text.startswith("{") and response_text.endswith("}"):
        try:
            if json.loads(response_text).get("error_type") == "AUTHENTICATION_REQUIRED":
                return "Authentication is required. Please provide your email."
        except Exception:
            pass

    lower = str(response_text).lower()
    if any(marker in lower for marker in _LEAK_MARKERS):
        print("[DHYAN GUARDRAIL] Blocked leaked internal content")
        return _CONNECT_FALLBACK

    return response_text

# ============================================================
# ADK ROOT AGENT — safe initialisation with cascading fallback
# ============================================================
_build_success = False
for _attempt, (_key, _model_idx) in enumerate(
    [(k, i) for k in API_KEYS for i in range(len(MODELS))]
):
    try:
        os.environ["GEMINI_API_KEY"] = _key
        os.environ.pop("GOOGLE_API_KEY", None)
        CURRENT_MODEL = _model_idx
        root_agent = build_agent()
        _build_success = True
        print(f"[DHYAN] root_agent ready → {current_model()}")
        break
    except Exception as _e:
        print(f"[DHYAN] Build attempt {_attempt+1} failed ({current_model()}): {_e}")
        mark_failed(current_model())

if not _build_success:
    raise RuntimeError("[DHYAN] Could not initialise root_agent — check API keys and network.")