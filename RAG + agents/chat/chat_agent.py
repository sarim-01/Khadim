import os
import json
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from retrieval.search_agent import SearchAgent
from retrieval.rag_retriever import RAGRetriever

# AFTER the existing imports, add:
try:
    import requests
except ImportError:
    requests = None
load_dotenv()

# Initialize the LLM
llm = ChatGroq(model="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

# --- 1. TOOL DEFINITIONS ---

@tool
def search_menu(query: str) -> str:
    """Search for specific menu items by name. Use this to find individual items the customer is asking about."""
    sa = SearchAgent()
    results = sa.search(query)
    
    # PRIORITY: Show individual menu items first, deals second
    menu_items = [r for r in results if r.get("type") == "menu_item"]
    deals = [r for r in results if r.get("type") == "deal"]
    
    if not menu_items and not deals:
        return f"No items found matching '{query}'."
    
    output = []
    
    # Format individual menu items with FULL details
    if menu_items:
        output.append(f"=== INDIVIDUAL MENU ITEMS ({len(menu_items)} found) ===\n")
        for item in menu_items:
            raw = item.get("raw", "")
            output.append(raw)
            output.append("")  # Add spacing
    
    # Format deals
    if deals:
        output.append(f"\n=== DEALS ({len(deals)} found) ===\n")
        for deal in deals:
            raw = deal.get("raw", "")
            output.append(raw)
            output.append("")  # Add spacing
    
    return "\n".join(output)

@tool
def retrieve_menu_context(query: str) -> str:
    """Retrieve general menu information using semantic search (RAG). Use when customer asks about general menu info."""
    rag = RAGRetriever()
    results = rag.search(query, k=10)  # Get more results to filter
    
    # Split by type: prioritize menu items
    lines = results.split("\n\n---\n\n")
    menu_items = [l for l in lines if "Menu Item:" in l]
    deals = [l for l in lines if "Deal:" in l]
    
    # Return menu items first, then deals
    prioritized = menu_items + deals
    prioritized_text = "\n\n---\n\n".join(prioritized[:5])  # Limit to top 5
    
    return prioritized_text if prioritized_text else results

@tool
def add_to_cart(item_name: str, quantity: int = 1) -> str:
    """Add an item to the shopping cart."""
    return f"Added {quantity}x {item_name} to your cart."

@tool
def remove_from_cart(item_name: str) -> str:
    """Remove an item from the shopping cart."""
    return f"Removed {item_name} from your cart."

@tool
def show_cart() -> str:
    """Display the current items in the shopping cart."""
    return "Your cart is empty."

@tool
def place_order() -> str:
    """Place the final order and checkout."""
    return "Order placed successfully! Your order has been sent to the kitchen."

@tool
def weather_upsell(city: str = "Islamabad") -> str:
    """
    Check weather and suggest food. 
    NOTE: This is a direct check. The Orchestrator handles the actual 'Upsell Agent' Redis call if needed,
    but this tool allows the Chat Agent to be aware of weather context directly if asked.
    """
    if not requests:
        return "Weather check unavailable (requests library missing)."
        
    API_KEY = os.getenv("OPENWEATHER_KEY")
    if not API_KEY:
        return "Weather info unavailable (Key missing)."

    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
        r = requests.get(url, timeout=3).json()
        
        temp = r.get("main", {}).get("temp", 25)
        weather = r.get("weather", [{}])[0].get("main", "").lower()

        if "rain" in weather or "drizzle" in weather:
            return f"It's raining ({temp}°C) — suggest Fries, Pakoras, or Hot Coffee/Tea."
        if temp < 15:
            return f"It's cold ({temp}°C) — suggest Soup, Hot Coffee, or Warm Desserts."
        if temp > 30:
            return f"It's hot ({temp}°C) — suggest Cold Drinks, Shakes, or Ice Cream."
            
        return f"Weather is mild ({temp}°C) — suggest our popular Zinger Burger or Club Sandwich."
    except Exception as e:
        return "Could not fetch weather data."

# --- 2. TOOL REGISTRY (maps tool names to functions) ---
tool_registry = {
    "search_menu": search_menu,
    "retrieve_menu_context": retrieve_menu_context,
    "add_to_cart": add_to_cart,
    "remove_from_cart": remove_from_cart,
    "show_cart": show_cart,
    "place_order": place_order, 
    "weather_upsell": weather_upsell,    
}

# --- 3. DETAILED SYSTEM PROMPT ---
SHORT_SYSTEM_PROMPT = """You are Khadim, an experienced and friendly restaurant waiter AI for a pakistani restaurant Salt n Pepper restaurant.

YOUR PERSONALITY:
- Be warm, professional, and enthusiastic
- Speak naturally like a real waiter would
- Help customers make informed choices
- Use conversational language

HOW TO PRESENT MENU ITEMS:
Never use general knowledge for menu questions
Always check the database first via tools
If nothing found, say "We don't have that" instead of making up alternatives
When showing items to customers, REFORMAT the raw menu data into natural language.

EXAMPLE OF WHAT TO DO:
Raw data: "Chicken Tikka, Marinated chicken pieces grilled on skewers, Price: 1200.0, Serves: 1 person, Portion Quantity: 200g, Prep Time: 20 minutes"
What to say: "We have Chicken Tikka - marinated chicken pieces grilled on skewers, served for 1 person with 200g portion, ready in 20 minutes, priced at just Rs. 1200."

FORMATTING RULES:
1. Present items in a natural, flowing way (not like a database dump)
2. Lead with the item name, then description, serving size, portion, time, and price
3. Group similar items together naturally
4. Use conversational phrases like "We have...", "Try our...", "Perfect for..."
5. NO database field names - never say "Price:", "Cuisine:", "Category:" etc.
6. ALWAYS use Rs. for prices (never dollars)
7. Make it sound like a real waiter describing food

WHEN SEARCHING FOR ITEMS:
1. First use search_menu to find items
2. Then present them naturally in conversational format
3. Suggest combinations or offer to add items to cart
4. Be helpful and engaging, not mechanical

CRITICAL RULES:
- NEVER show raw database format
- NEVER list field names
- ONLY use data from search results
- NEVER make up prices or items
- Always be friendly and helpful
- only include items and deals that are actually on the menu, dont make them up"""

# --- 4. BUILD TOOL DESCRIPTIONS FOR LLM ---
tool_descriptions = """
1. search_menu | query=<term>
   - Search specific items/deals by name/category.

2. weather_upsell | city=<name>
   - Checks current weather to suggest food (e.g., Soup if cold, Soda if hot).

3. add_to_cart | item_name=<name> | quantity=<number>
   - Adds items to cart.

4. remove_from_cart | item_name=<name>
   - Removes specific item from cart.
   
5. show_cart
   - Shows current cart contents.
   
6. place_order
   - Finalizes order.
"""

# --- 5. EXECUTION FUNCTION WITH MANUAL TOOL CALLING ---

def _format_history(history_list):
    """Helper to convert dictionary history to LangChain Message Objects."""
    langchain_history = []
    for msg in history_list:
        if msg['role'] == 'user':
            langchain_history.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            langchain_history.append(AIMessage(content=msg['content']))
    return langchain_history

def _call_tool(tool_name: str, tool_input: dict):
    """Execute a tool by name with given inputs."""
    if tool_name not in tool_registry:
        return f"Tool '{tool_name}' not found."
    
    tool_func = tool_registry[tool_name]
    try:
        # Call the tool with unpacked kwargs
        result = tool_func.invoke(tool_input)
        return str(result)
    except Exception as e:
        return f"Error calling {tool_name}: {str(e)}"

def get_ai_response(user_input: str, conversation_history: list, menu_context: str = ""):
    """
    Get AI response and detect tool calls to return to orchestrator.
    Returns an AIMessage with tool_calls attribute for orchestrator to handle database operations.
    """
    try:
        # Build the system message
        system_message = f"""{SHORT_SYSTEM_PROMPT}

{tool_descriptions}

CRITICAL INSTRUCTION FOR TOOL USAGE:
When you need to perform an action (search menu, add, remove, show cart, place order), respond EXACTLY in this format on a new line:

TOOL_CALL: search_menu | query=chicken
TOOL_CALL: weather_upsell | city=Islamabad
TOOL_CALL: add_to_cart | item_name=Chicken Tikka | quantity=2
TOOL_CALL: remove_from_cart | item_name=Chicken Tikka
TOOL_CALL: show_cart
TOOL_CALL: place_order

Then provide your friendly response BEFORE the TOOL_CALL line.

Example:
Great! Let me add that for you.
TOOL_CALL: add_to_cart | item_name=Chicken Tikka | quantity=1

IMPORTANT: The orchestrator will execute these tool calls and update the database. Never execute tools yourself - just indicate what tool to use.


ADDITIONAL MANDATORY RULE FOR TOOL SELECTION:
If the user asks about ANY cuisine, category, or group such as:
"desi", "bbq", "fast food", "chinese", "drinks", "bread", "deals",
OR asks generally like "desi khana", "bbq khana", "chinese dishes", "show deals",
you MUST ALWAYS use:

TOOL_CALL: search_menu | query=<that word>

Never use retrieve_menu_context for cuisine, category, or deal queries.
Only use retrieve_menu_context for vague or open-ended questions like:
"recommend something", "what is good", "suggest something tasty".

This rule ensures accurate SQL results for both menu items and deals.

"""
        
        if menu_context:
            system_message += f"\n\nMENU DATA (use this to respond naturally):\n{menu_context}"
        
        # Build conversation messages
        messages = [HumanMessage(content=system_message)]
        
        # Add conversation history
        for msg in conversation_history:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            else:
                messages.append(AIMessage(content=msg['content']))
        
        # Add current user input
        reminder_text = """
(SYSTEM NOTE: 
Check your tools. If the user is asking to add, remove, search,
 or place an order, you MUST generate the 'TOOL_CALL:' line. 
 Do not just say you did it. If no action is needed, just chat.)
"""
        messages.append(HumanMessage(content=user_input + reminder_text))
        
        # Get response from LLM
        response = llm.invoke(messages)
        response_text = response.content
        
        # Extract tool calls from response
        tool_calls = []
        lines = response_text.split('\n')
        
        for line in lines:
            if 'TOOL_CALL:' in line:
                try:
                    # Parse: TOOL_CALL: tool_name | param1=value1 | param2=value2
                    tool_part = line.split('TOOL_CALL:')[1].strip()
                    parts = [p.strip() for p in tool_part.split('|')]
                    
                    tool_name = parts[0]
                    tool_args = {}
                    
                    for part in parts[1:]:
                        if '=' in part:
                            key, val = part.split('=', 1)
                            tool_args[key.strip()] = val.strip()
                    
                    tool_calls.append({
                        'name': tool_name,
                        'args': tool_args
                    })
                except Exception as e:
                    print(f"Error parsing tool call: {e}")
                    continue
        
        # Remove TOOL_CALL lines from response for display
        final_response = '\n'.join([l for l in lines if 'TOOL_CALL:' not in l]).strip()
        
        # Create AIMessage with tool_calls
        ai_msg = AIMessage(content=final_response)
        ai_msg.tool_calls = tool_calls
        
        return ai_msg
        
    except Exception as e:
        msg = AIMessage(content=f"Sorry, I encountered an error: {str(e)}")
        msg.tool_calls = []
        return msg