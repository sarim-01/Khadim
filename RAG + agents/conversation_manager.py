from typing import List, Dict

class ConversationManager:
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.conversation_history: List[Dict[str, str]] = []
    
    def add_message(self, role: str, content: str):
        """Add a new message to the conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content
        })
        # Keep only the last max_history messages
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get the current conversation history"""
        return self.conversation_history
    
    def clear_history(self):
        """Clear the conversation history"""
        self.conversation_history = []