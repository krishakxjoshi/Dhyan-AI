# Dhyan AI — Autonomous Multi-Agent Fabric Solutions 🚀

### 🏆 Google & Kaggle 5-Day AI Agents Capstone Project — Agents for Business Track

Dhyan AI is an autonomous multi-agent enterprise framework designed for custom fabric and apparel manufacturing firms (like DHYANI TRACKS). It bridges the operational gap between client customization requests and business floor realities by automating client consultations, cross-referencing live raw material inventory via a custom Model Context Protocol (MCP) server, and routing structured receipts directly to managers for a "Human-in-the-Loop" final approval.

No more hours spent discussing bulk pricing tiers or production schedules on phone calls—just seamless, secure, zero-lag automation.

---

## 📐 System Architecture

Dhyan AI isolates frontend customer conversations from backend data layers using a secure, collaborative multi-agent loop:


1. **Sales Agent (Frontend / Chat):** Interacts politely with the customer to gather customization requirements (fabric type, dimensions, sizes, color). For security, it cannot query the databases directly.
2. **Order Agent (Backend / Analyst):** Communicates internally with the Sales Agent. It utilizes custom MCP tools to check real-time stock levels and compute delivery schedules from the production queue. If materials are out of stock, it dynamically suggests available alternatives.
3. **Dispatcher Agent & Skills:** Extracts raw conversational state into a strict structured JSON receipt, activates mail tools to notify the manager, and pauses the workflow until a final authorization "green flag" is received.

---

## ✨ Key Features & Course Concepts Demonstrated

* **Multi-Agent Collaboration:** Implements an internal agent-to-agent communication loop separating public interaction from enterprise tools.
* **Custom Model Context Protocol (MCP) Server:** Dynamically reads and tracks live `pricing_catalog.json` metrics and `production_queue.json` timeline slots.
* **Shift-Left Security & Guardrails:** Input and output guardrails prevent prompt injection and guarantee that agents never commit to definitive delivery dates before explicit manager confirmation.
* **Human-in-the-Loop (HITL) Verification:** Integrates automated manager email notifications to verify custom project viability before finalizing client orders.

---

## 🛠️ Project Structure

```text
├── data/
│   ├── pricing_catalog.json    # Bulk discount rates & catalog prices
│   └── production_queue.json   # Live factory scheduling & material limits
├── src/
│   ├── mcp_server.py           # Custom Model Context Protocol server setup
│   ├── agents.py               # Sales, Order, and Dispatcher agent definitions
│   ├── tools.py                # check_inventory, check_queue_dates, and mail tools
│   └── main.py                 # Main orchestration loop/chat environment
├── watermarked_img_2619475822265878116.png # Architecture Diagram
├── requirements.txt            # Project dependencies
└── README.md                   # Project documentation
