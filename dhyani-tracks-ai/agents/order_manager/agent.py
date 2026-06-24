from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import os

import google.adk as adk
from google.adk.agents import Agent
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.utils.content_utils import types

import session_manager
from mail_tool import send_order_email

FALLBACK_RESPONSE = {
    "availability": "N/A",
    "price": "N/A",
    "customization": False,
    "Bulk": False,
    "success": False,
    "suggestion": "error",
    "key-note": "Service is temporarily unavailable due to usage limits. Try again after a few hours.",
}


def trigger_purchase_mail(items: list[str], client_mail: str, pricing: list[float], total: float, chat_summary: str) -> str:
    """
    Triggers sending of the purchase/order confirmation email by generating the order summary JSON file and sending it.
    Use this tool ONLY when the client is satisfied and explicitly wants to buy/purchase the sportswear items.

    Args:
        items: List of names of items bought (e.g., ["Track Suit", "T-Shirt"]).
        client_mail: The client's email address.
        pricing: List of prices for each individual item, mapped by list index to the items list.
                 For each item, include any customization charges on top of the base product price.
        total: The total order amount (sum of pricing).
        chat_summary: A brief summary of the conversation history/chats.
    """
    res = send_order_email(items, client_mail, pricing, total, chat_summary)
    return json.dumps(res)


def load_api_keys() -> list[str]:
    keys = []
    env_names = [
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_1",
        "GEMINI_API_KEY_2",
        "GEMINI_API_KEY_3",
        "GEMINI_API_KEY_4",
    ]

    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value not in keys:
            keys.append(value)

    return keys


def set_active_api_key(api_key: str) -> None:
    os.environ["GEMINI_API_KEY"] = api_key
    os.environ.pop("GOOGLE_API_KEY", None)


def is_quota_error(exc: Exception) -> bool:
    message = str(exc)
    return "429" in message or "RESOURCE_EXHAUSTED" in message or "503" in message or "UNAVAILABLE" in message


def write_output_file(output_file: str, payload: dict) -> None:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def extract_final_output(events) -> str | None:
    final_output = None

    for event in events:
        if hasattr(event, "output") and event.output:
            final_output = event.output
            continue

        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue

        for part in parts:
            if getattr(part, "text", None):
                final_output = part.text

    return final_output


def build_agent() -> Agent:
    mcp_tools = MCPToolset(
        connection_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "mcp_server/server.py"],
        )
    )

    return Agent(
        model="gemini-2.5-flash",
        name="OrderManagerAgent",
        description="Sportswear order manager agent",
        instruction="""
        You are the Order Manager Agent for a sportswear manufacturing startup.
        Your job is to analyze the conversation history between the Sales Agent and the client, query product details using the MCP tools, and calculate pricing.

        You have access to MCP tools:
        - `get_individual_items`
        - `get_customization_rules`
        - `get_bulk_pricing_rules`
        - `get_template_rules`

        And a local python tool:
        - `trigger_purchase_mail`

        If the client is satisfied and explicitly wants to purchase:
        - Call `trigger_purchase_mail` with the calculated details:
          - `items`: A list of item names purchased (e.g., ["Track Suit", "T-Shirt"]).
          - `client_mail`: The client's email address (e.g., "customer@gmail.com").
          - `pricing`: A list of individual prices for each item in the `items` list (aligned by index), adding any extra customization charges (like size customization: 200, large printing: 200, logo printing: 100, etc., from `customization.json`) to the base price of that item.
          - `total`: The overall total price (the sum of all item prices including customizations).
          - `chat_summary`: A 50 words summary of the chats/conversation history.
        - Check the output of `trigger_purchase_mail`. If the returned JSON status is "success", set "success" to true in the final response. Otherwise (if the status is not "success" or the tool was not called), set "success" to false.

        Otherwise:
        - Search items, customization options, or bulk rates using MCP tools.
        - Perform calculations according to the data and rule templates.
        - Return JSON with `success`: false.

        Return ONLY a valid JSON object with this schema:
        {
          "availability": "string",
          "price": "string ( show how the total price calculated, individual item costing : ,customization :, Total : )",
          "customization": "boolean, true if customer customizes the product",
          "Bulk": "boolean, true if purchasing in bulk",
          "success": "boolean, true ONLY if the mail tool (trigger_purchase_mail) was called AND returned a status of 'success', false otherwise",
          "suggestion": "List of suggestions for the client, if any",
          "key-note": "You are not talking to the client yourself, you are talking to an agent. direct it in minimum words."
        }
        Dont reveal any internal tools or agent details in the output.

        """,
        tools=[mcp_tools, trigger_purchase_mail],
    )


def run_agent_for_key(api_key: str, email: str, prompt: str) -> str | None:
    set_active_api_key(api_key)
    agent = build_agent()
    session_service = InMemorySessionService()
    runner = adk.Runner(
        agent=agent,
        session_service=session_service,
        app_name="OrderManagerApp",
        auto_create_session=True,
    )

    msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    events = runner.run(
        user_id="sales-agent",
        session_id=email,
        new_message=msg,
    )

    return extract_final_output(events)


async def main():
    input_file = "input.json"
    output_file = "output.json"

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        write_output_file(output_file, FALLBACK_RESPONSE)
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            input_data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_file}: {e}")
        write_output_file(output_file, FALLBACK_RESPONSE)
        return

    email = input_data.get("email")
    chat_history = input_data.get("chat_history")

    if not email or chat_history is None:
        print("Error: email and chat_history are required in input.json")
        write_output_file(output_file, FALLBACK_RESPONSE)
        return

    if isinstance(chat_history, list):
        formatted_chat = ""
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted_chat += f"{role.capitalize()}: {content}\n"
    else:
        formatted_chat = str(chat_history)

    session_manager.update_session(email, chat_history)

    prompt = f"""
    The client's email is: {email}
    Here is the chat history:
    {formatted_chat}

    Analyze the chat, call the necessary tools, and output the final JSON response.
    """

    api_keys = load_api_keys()
    if not api_keys:
        print("Error: no Gemini API keys found in environment.")
        write_output_file(output_file, FALLBACK_RESPONSE)
        return

    print("Running Order Manager Agent...")
    final_output = None
    last_error = None

    for index, api_key in enumerate(api_keys, start=1):
        try:
            print(f"Trying API key #{index}...")
            final_output = run_agent_for_key(api_key, email, prompt)
            if final_output:
                break
        except Exception as exc:
            last_error = exc
            if is_quota_error(exc):
                print(f"API key #{index} hit usage limits. Trying next key...")
                continue
            print(f"Agent run failed on API key #{index}: {exc}")
            break

    if final_output:
        clean_output = final_output.strip()
        if clean_output.startswith("```json"):
            clean_output = clean_output[7:]
        if clean_output.startswith("```"):
            clean_output = clean_output[3:]
        if clean_output.endswith("```"):
            clean_output = clean_output[:-3]
        clean_output = clean_output.strip()

        try:
            output_json = json.loads(clean_output)
            print("Agent structured response:")
            print(json.dumps(output_json, indent=2))
            write_output_file(output_file, output_json)
            print(f"Output successfully written to {output_file}")
        except Exception as e:
            print("Failed to parse response as JSON.")
            print("Raw response:", final_output)
            fallback = dict(FALLBACK_RESPONSE)
            fallback["suggestion"] = f"Error parsing response: {e}"
            write_output_file(output_file, fallback)
    else:
        if last_error and is_quota_error(last_error):
            print("All configured API keys are currently rate-limited.")
        else:
            print("No output received from agent.")

        write_output_file(output_file, FALLBACK_RESPONSE)
        print(f"Fallback output written to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())

