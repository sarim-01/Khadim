# Backend Overview

This directory contains the backend implementation for the restaurant chatbot project.  The code is organised as a set of independent agents that communicate over Redis pub/sub.  The Streamlit `orchestrator.py` is used for the UI and drives the system in a development environment.

## Agent Modules

| File | Purpose |
|------|---------|
| `cart_agent.py` | Handles shopping cart lifecycle and order finalisation. |
| `chat_agent.py` | Wraps LLM calls to provide conversational responses and tools. |
| `search_agent.py` | Performs text search over the menu/database. |
| `order_agent.py` | Persists final orders and generates confirmation summaries. |
| `kitchen_agent.py` | Plans and updates kitchen tasks, assigns chefs. |
| `recommender_agent.py` | Suggests items based on cart context. |
| `custom_deal_agent.py` | Creates dynamic deals during chat interactions. |
| `upsell_agent.py` | Recommends extras based on weather or other signals. |
| `agent_health_dashboard.py` | Metrics and status for running agents (Streamlit). |
| `kitchen_dashboard.py` | Kitchen display UI for chefs to update task status. |
| `order_coordinator.py` | Pipeline that glues cart & kitchen agents (can run standalone). |
| `redis_connection.py` | Singleton wrapper around Redis client. |
| `redis_lock.py` | Distributed locking primitives used by kitchen planning. |
| `agent_lifecycle_manager.py` | Utility to restart/monitor long‑running agents. |
| `database_connection.py` | PostgreSQL connection manager.
| `config.py` | Shared constants (channels, redis host, etc.).

## Getting Started

1. Ensure Redis and PostgreSQL are running.  Example Docker command for Redis:
   ```bash
   docker run -d --name redis -p 6379:6379 redis
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Populate `.env` with credentials (API keys, DB URL, etc.).
4. Initialize the database schema using the provided `.sql` scripts in `Database/`.
5. Run agents individually or use `run_all.bat` (Windows) to start them all.

## Scripts

* `run_all.bat` – example batch file to start all agents and dashboards concurrently.

For detailed explanation of each agent's behaviour, consult the source files directly.
