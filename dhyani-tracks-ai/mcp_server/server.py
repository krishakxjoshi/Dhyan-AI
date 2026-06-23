import os
import json
from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP("Sportswear Inventory MCP Server")

# Helper to read JSON files from the data folder
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def load_json_file(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": f"File {filename} not found."}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

@mcp.tool()
def get_individual_items(category: str = None, name_search: str = None) -> str:
    """
    Retrieve individual sportswear items. 
    Can filter by category (e.g., 'T-Shirt', 'Lower', 'Track Suit', 'Socks', 'Shorts')
    or search by name/description.
    """
    items = load_json_file("individuals.json")
    if isinstance(items, dict) and "error" in items:
        return json.dumps(items)
        
    filtered = items
    if category:
        filtered = [i for i in filtered if i.get("category", "").lower() == category.lower()]
    if name_search:
        ns = name_search.lower()
        filtered = [
            i for i in filtered 
            if ns in i.get("description", "").lower() or ns in i.get("fabric", "").lower()
        ]
    return json.dumps(filtered[:15], indent=2)  # Limit results to 15 to conserve tokens

@mcp.tool()
def get_customization_rules() -> str:
    """
    Retrieve customization options, rules, and charges (e.g., embroidery, logo printing, size customization rates).
    """
    data = load_json_file("customization.json")
    return json.dumps(data, indent=2)

@mcp.tool()
def get_bulk_pricing_rules() -> str:
    """
    Retrieve the bulk pricing policy, initial bulk discounts, minimum bulk quantities, and rules for items like T-Shirts, Lowers, and Track Suits.
    """
    data = load_json_file("bulk.json")
    return json.dumps(data, indent=2)

@mcp.tool()
def get_template_rules() -> str:
    """
    Retrieve order rules templates (Individual, Bulk, Customization) to know conditions and delivery times.
    """
    data = load_json_file("template_rules.json")
    return json.dumps(data, indent=2)

if __name__ == "__main__":
    mcp.run()
