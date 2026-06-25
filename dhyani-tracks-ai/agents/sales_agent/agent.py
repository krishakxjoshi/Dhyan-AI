import os
import random
import json
import time
from itertools import cycle
from dotenv import load_dotenv
from google.adk.agents import Agent
from .tools import call_backend
from google.genai.errors import ServerError

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
    print("[DHYAN] API rotated")
    return key

MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash-latest"]
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
    raise RuntimeError("No model available")

def current_model():
    return MODELS[CURRENT_MODEL]

rotate_api_key()
print(f"[DHYAN] Active model → {current_model()}")

def mark_failed(model):
    MODEL_COOLDOWN[model] = time.time() + 60

def next_model(current):
    return MODELS[(MODELS.index(current) + 1) % len(MODELS)]

# ============================================================
# LOAD SYSTEM PROMPT & ERROR DETECTION
# ============================================================
prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.txt")
with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()

RETRY_ERRORS = ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED"]

def is_retryable(exc):
    text = str(exc).upper()
    return any(x in text for x in RETRY_ERRORS)

def is_quota_error(exc):
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text

def is_overload(exc):
    text = str(exc)
    return "503" in text or "UNAVAILABLE" in text

# ============================================================
# RESILIENT AGENT FACTORY & ORCHESTRATION
# ============================================================
MAX_RETRIES = 3
CURRENT_MODEL = 0

def build_agent():
    model = current_model()
    print(f"[DHYAN] Loading {model}")
    return Agent(
        name="sales_agent",
        model=model,
        tools=[call_backend],
        instruction=system_prompt,
    )

def rotate_model():
    global CURRENT_MODEL
    CURRENT_MODEL = (CURRENT_MODEL + 1) % len(MODELS)
    print(f"[DHYAN] Rotated → {MODELS[CURRENT_MODEL]}")

# initialize
import asyncio

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

# ADK loads root_agent lazily.
# Do NOT use asyncio.run() during import.

root_agent = build_agent()

# ============================================================
# RESPONSE GUARDRAIL
# ============================================================
def guardrail_check(response_text):
    if isinstance(response_text, str) and response_text.startswith("{") and response_text.endswith("}"):
        try:
            if json.loads(response_text).get("error_type") == "AUTHENTICATION_REQUIRED":
                return "Authentication is required. Please provide your email."
        except Exception:
            pass

    blocked = ["system instructions", "internal logic", "prompt", "hidden instructions", "tool payload", "backend response"]
    if any(x in str(response_text).lower() for x in blocked):
        return "For security compliance, I cannot share internal configuration details. I can help you choose apparel instead."
    return response_text