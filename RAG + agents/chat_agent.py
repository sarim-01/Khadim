import os
import json
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from search_agent import SearchAgent
from rag_retriever import RAGRetriever

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
    API_KEY = os.getenv("OPENWEATHER_KEY")
    if not API_KEY:
        return "Weather info unavailable (API Key missing)."

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
        return f"Could not fetch weather data: {str(e)}"

@tool
def create_custom_deal(user_requirement: str) -> str:
    """
    Creates a customized deal based on user requirements.
    Use this when user asks for a 'custom deal', 'make me a deal', or combines specific items like 'Biryani and Burger deal'.
    Input: The user's full requirement text.
    """
    return "success"

# --- 2. TOOL REGISTRY (maps tool names to functions) ---
tool_registry = {
    "search_menu": search_menu,
    "retrieve_menu_context": retrieve_menu_context,
    "add_to_cart": add_to_cart,
    "remove_from_cart": remove_from_cart,
    "show_cart": show_cart,
    "place_order": place_order, 
    "weather_upsell": weather_upsell,  
    "create_custom_deal": create_custom_deal,   
}

# --- 3. DETAILED SYSTEM PROMPT ---
SHORT_SYSTEM_PROMPT = """You are Khadim, an experienced and friendly restaurant waiter AI for a pakistani restaurant Salt n Pepper restaurant.

YOUR PERSONALITY:
- Be warm, professional, and enthusiastic
- Speak naturally like a real waiter would
- Help customers make informed choices
- Use conversational language

YOUR SPECIAL POWER (CUSTOM DEALS) - CRITICAL:
- You MUST use the create_custom_deal tool whenever users ask for custom deals!
- TRIGGER WORDS - When you see these, ALWAYS call create_custom_deal:
  * "custom deal"
  * "make a deal with [items]"
  * "create a deal"
  * "deal for X people"
  * "combine [items] into a deal"

- MANDATORY TOOL USE CASES:
  1. User wants specific items combined: "Make a deal with biryani and burger" → MUST call create_custom_deal
  2. User wants deal for multiple people: "Create a 3 person deal" → MUST call create_custom_deal
  3. User wants cuisine-based deal: "Pakistani food deal" → MUST call create_custom_deal
  4. User asks if you make custom deals: Say YES and ask what they want, then call create_custom_deal

- DO NOT just chat about making deals - ACTUALLY MAKE THEM using the tool!
- Pass the complete user request to create_custom_deal

HOW TO PRESENT MENU ITEMS:
Never use general knowledge for menu questions
Always check the database first via tools
When showing items to customers, REFORMAT the raw menu data into natural language.

WHEN ITEMS AREN'T FOUND - BE CONVERSATIONAL:
If a customer asks for something we don't have, respond like a real waiter would:
- DON'T just say "not found" or show unrelated items
- DO explain kindly and offer similar alternatives
- Examples:
  * User asks for "ice cream" but we only have shakes → "We don't have ice cream, but we do have delicious shakes like Strawberry Shake or Mango Shake!"
  * User asks for "pizza" but we don't have it → "We don't serve pizza, but our Zinger Burger is very popular!"
  * User asks for items from wrong cuisine → "We don't have Chinese food items, but I can show you our Pakistani cuisine or Continental options!"
- Use semantic understanding - if search returns SIMILAR items, offer them intelligently
- If search returns UNRELATED items (like "Iced Coffee" for "ice cream"), ignore them and say we don't have it

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


7. create_custom_deal | user_requirement=<text>
   - Creates a custom discounted deal based on user specs. 
   - Use when user wants to CREATE a deal (not search for existing deals)
   - Examples: 
     * "Make me a deal with biryani and burger" 
     * "Create a 3 person deal"
     * "I want a Pakistani food custom deal"
   - IMPORTANT: Pass the COMPLETE user requirement, not a summary

CRITICAL EXAMPLES:
User: "Make a deal with biryani and burger"
TOOL_CALL: create_custom_deal | user_requirement=Make a deal with biryani and burger

User: "Create a custom deal for 3 people with fast food"
TOOL_CALL: create_custom_deal | user_requirement=Create a custom deal for 3 people with fast food
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
- "deal for X people"

CONTEXT-AWARE TRIGGERING:
- If you previously asked "What items would you like in your deal?" and user responds with items → CALL create_custom_deal
- If conversation is about custom deals and user provides specifications → CALL create_custom_deal
- Look at conversation history - if discussing custom deals, user's response is the requirement

EXAMPLES (YOU MUST FOLLOW THIS PATTERN):

User: "make a deal with biryani and burger"
Response: I'll create a special custom deal for you with biryani and burger!
TOOL_CALL: create_custom_deal | user_requirement=make a deal with biryani and burger

User: "create a 3 person deal"  
Response: Great! I'll create a custom deal for 3 people.
TOOL_CALL: create_custom_deal | user_requirement=create a 3 person deal

User: "can you make custom deals?"
Bot: "Yes! I can create custom deals. What items would you like in your deal?"
User: "biryani and a burger"
Response: Perfect! Let me create that custom deal for you.
TOOL_CALL: create_custom_deal | user_requirement=biryani and a burger

IMPORTANT: The orchestrator will execute these tool calls and update the database. Never execute tools yourself - just indicate what tool to use.
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