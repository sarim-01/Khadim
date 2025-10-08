import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import uuid

__all__ = ['AddToCartAgent', 'Cart', 'CartItem']


@dataclass
class CartItem:
    """Represents a single item in the cart"""
    item_id: str
    item_name: str
    price: float
    quantity: int
    special_requests: Optional[str] = None
    
    @property
    def subtotal(self) -> float:
        return self.price * self.quantity


@dataclass
class Cart:
    """Represents a user's shopping cart"""
    cart_id: str
    items: List[CartItem]
    created_at: datetime
    updated_at: datetime
    
    @property
    def total_price(self) -> float:
        return sum(item.subtotal for item in self.items)
    
    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)
    
    def to_dict(self) -> Dict:
        return {
            'cart_id': self.cart_id,
            'items': [asdict(item) for item in self.items],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'total_price': self.total_price,
            'total_items': self.total_items
        }


class AddToCartAgent:
    """
    Agent responsible for managing user's cart operations
    """
    
    def __init__(self):
        self.carts: Dict[str, Cart] = {}  # In-memory storage for demo
        # In production, you'd use Redis or database for persistent storage
        
    def get_cart_summary(self, cart_id: str) -> Dict[str, Any]:
        """Get a summary of the cart contents"""
        if cart_id not in self.carts:
            return {
                'cart_id': cart_id,
                'items': [],
                'total_items': 0,
                'total_price': 0,
                'message': 'Your cart is empty'
            }
            
        cart = self.carts[cart_id]
        summary = cart.to_dict()
        
        # Format the items for display
        items_summary = []
        for item in cart.items:
            items_summary.append({
                'item_name': item.item_name,
                'quantity': item.quantity,
                'price': item.price,
                'subtotal': item.subtotal
            })
            
        summary['items'] = items_summary
        return summary
    
    def create_cart(self, user_id: str = None) -> str:
        """Create a new cart and return cart_id"""
        cart_id = user_id or str(uuid.uuid4())
        now = datetime.now()
        
        self.carts[cart_id] = Cart(
            cart_id=cart_id,
            items=[],
            created_at=now,
            updated_at=now
        )
        
        return cart_id
    
    def add_item(self, cart_id: str, item_data: Dict, quantity: int = 1, 
                 special_requests: str = None) -> Dict[str, Any]:
        """
        Add an item to the cart
        
        Args:
            cart_id: Cart identifier
            item_data: Dictionary with item details (item_id, item_name, price)
            quantity: Number of items to add
            special_requests: Any special instructions
            
        Returns:
            Dictionary with operation status and cart summary
        """
        try:
            # Get or create cart
            if cart_id not in self.carts:
                self.create_cart(cart_id)
            
            cart = self.carts[cart_id]
            
            # Check if item already exists in cart
            existing_item = None
            for item in cart.items:
                if item.item_id == item_data['item_id']:
                    existing_item = item
                    break
            
            if existing_item:
                # Update quantity of existing item
                existing_item.quantity += quantity
                existing_item.special_requests = special_requests or existing_item.special_requests
                message = f"Updated {item_data['item_name']} quantity to {existing_item.quantity}"
            else:
                # Add new item to cart
                new_item = CartItem(
                    item_id=item_data['item_id'],
                    item_name=item_data['item_name'],
                    price=float(item_data['price']),
                    quantity=quantity,
                    special_requests=special_requests
                )
                cart.items.append(new_item)
                message = f"Added {quantity}x {item_data['item_name']} to cart"
            
            # Update cart timestamp
            cart.updated_at = datetime.now()
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error adding item to cart: {str(e)}",
                'cart_summary': None
            }
    
    def remove_item(self, cart_id: str, item_id: str = None, 
                    item_name: str = None) -> Dict[str, Any]:
        """
        Remove an item from the cart
        
        Args:
            cart_id: Cart identifier
            item_id: ID of item to remove (optional)
            item_name: Name of item to remove (optional)
            
        Returns:
            Dictionary with operation status and cart summary
        """
        try:
            if cart_id not in self.carts:
                return {
                    'success': False,
                    'message': "Cart not found",
                    'cart_summary': None
                }
            
            cart = self.carts[cart_id]
            
            # Find item to remove
            item_to_remove = None
            for item in cart.items:
                if (item_id and item.item_id == item_id) or \
                   (item_name and item_name.lower() in item.item_name.lower()):
                    item_to_remove = item
                    break
            
            if item_to_remove:
                cart.items.remove(item_to_remove)
                cart.updated_at = datetime.now()
                message = f"Removed {item_to_remove.item_name} from cart"
            else:
                message = "Item not found in cart"
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error removing item: {str(e)}",
                'cart_summary': None
            }
    
    def update_quantity(self, cart_id: str, item_id: str, new_quantity: int) -> Dict[str, Any]:
        """
        Update quantity of an item in cart
        
        Args:
            cart_id: Cart identifier
            item_id: ID of item to update
            new_quantity: New quantity (0 will remove item)
            
        Returns:
            Dictionary with operation status and cart summary
        """
        try:
            if cart_id not in self.carts:
                return {
                    'success': False,
                    'message': "Cart not found",
                    'cart_summary': None
                }
            
            cart = self.carts[cart_id]
            
            # Find item to update
            target_item = None
            for item in cart.items:
                if item.item_id == item_id:
                    target_item = item
                    break
            
            if not target_item:
                return {
                    'success': False,
                    'message': "Item not found in cart",
                    'cart_summary': None
                }
            
            if new_quantity <= 0:
                cart.items.remove(target_item)
                message = f"Removed {target_item.item_name} from cart"
            else:
                target_item.quantity = new_quantity
                message = f"Updated {target_item.item_name} quantity to {new_quantity}"
            
            cart.updated_at = datetime.now()
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error updating quantity: {str(e)}",
                'cart_summary': None
            }
    
    def get_cart_summary(self, cart_id: str) -> Optional[Dict]:
        """Get complete cart summary"""
        if cart_id not in self.carts:
            return None
        
        cart = self.carts[cart_id]
        
        if not cart.items:
            return {
                'cart_id': cart_id,
                'items': [],
                'total_items': 0,
                'total_price': 0.0,
                'message': "Your cart is empty"
            }
        
        return cart.to_dict()
    
    def clear_cart(self, cart_id: str) -> Dict[str, Any]:
        """Clear all items from cart"""
        try:
            if cart_id in self.carts:
                self.carts[cart_id].items = []
                self.carts[cart_id].updated_at = datetime.now()
                message = "Cart cleared successfully"
            else:
                message = "Cart not found"
            
            return {
                'success': True,
                'message': message,
                'cart_summary': self.get_cart_summary(cart_id)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error clearing cart: {str(e)}",
                'cart_summary': None
            }
    
    def process_natural_language_request(self, cart_id: str, user_input: str, 
                                       context: Dict = None) -> Dict[str, Any]:
        """
        Process natural language cart requests
        This is a simplified version - in production you'd use NLP/LLM for intent recognition
        """
        user_input = user_input.lower()
        
        # Simple keyword-based intent recognition
        if "add" in user_input or "put" in user_input:
            # Extract item details from context (would come from search agent)
            if context and 'selected_item' in context:
                quantity = self._extract_quantity(user_input)
                return self.add_item(cart_id, context['selected_item'], quantity)
            else:
                return {
                    'success': False,
                    'message': "Please specify which item you want to add",
                    'cart_summary': None
                }
        
        elif "remove" in user_input or "delete" in user_input:
            # Try to extract item name
            item_name = self._extract_item_name(user_input)
            return self.remove_item(cart_id, item_name=item_name)
        
        elif "show" in user_input or "what" in user_input or "cart" in user_input:
            return {
                'success': True,
                'message': "Here's your current cart:",
                'cart_summary': self.get_cart_summary(cart_id)
            }
        
        elif "clear" in user_input or "empty" in user_input:
            return self.clear_cart(cart_id)
        
        else:
            return {
                'success': False,
                'message': "I didn't understand that cart operation. Try 'add item', 'remove item', or 'show cart'",
                'cart_summary': None
            }
    
    def _extract_quantity(self, text: str) -> int:
        """Extract quantity from text - simplified version"""
        import re
        numbers = re.findall(r'\d+', text)
        return int(numbers[0]) if numbers else 1
    
    def _extract_item_name(self, text: str) -> str:
        """Extract item name from text - simplified version"""
        # This would be more sophisticated with proper NLP
        words = text.split()
        # Remove common words
        stop_words = ['remove', 'delete', 'the', 'from', 'cart']
        item_words = [word for word in words if word not in stop_words]
        return ' '.join(item_words) if item_words else ""


# Example usage and testing
if __name__ == "__main__":
    # Create agent instance
    cart_agent = AddToCartAgent()
    
    # Create a cart
    cart_id = cart_agent.create_cart("user123")
    print(f"Created cart: {cart_id}")
    
    # Sample item data (would come from search agent)
    sample_item = {
        'item_id': 'burger_001',
        'item_name': 'Chicken Burger',
        'price': 15.99
    }
    
    # Test adding items
    result = cart_agent.add_item(cart_id, sample_item, quantity=2)
    print(f"Add result: {result['message']}")
    
    # Test cart summary
    summary = cart_agent.get_cart_summary(cart_id)
    print(f"Cart total: ${summary['total_price']:.2f}")
    
    # Test removing item
    result = cart_agent.remove_item(cart_id, item_name="Chicken Burger")
    print(f"Remove result: {result['message']}")
    
    print("\nFinal cart summary:", cart_agent.get_cart_summary(cart_id))