@echo off
REM Starts Redis (assuming "redis" container or service), then launches each Python agent in a new window.

echo Starting backend agents...

start "Redis" cmd /k "docker run -d --name redis -p 6379:6379 redis || echo Redis already running"
start "Cart Agent" cmd /k "python -m cart.cart_agent"
start "Chat Agent" cmd /k "python -m chat.chat_agent"
start "Search Agent" cmd /k "python -m retrieval.search_agent"
start "Order Agent" cmd /k "python -m orders.order_agent"
start "Kitchen Agent" cmd /k "python -m kitchen.kitchen_agent"
start "Coordinator" cmd /k "python -m orders.order_coordinator"
start "Health Dashboard" cmd /k "python -m monitoring.agent_health_dashboard"
start "Kitchen Dashboard" cmd /k "streamlit run kitchen/kitchen_dashboard.py"

echo All windows launched. Close them individually when done.
pause