# Fixed cart_parser.py

import re
from typing import Dict, Optional, Tuple

class CartCommandParser:
    ADD_PATTERNS = [
        r"add (?:(\d+)|a|an) (.+?)(?: with (.+?))? to (?:my |the )?cart",
        r"i(?:'d| would) like (?:(\d+)|a|an) (.+?)(?: with (.+?))?(?:\s|$)",
        r"can i (?:get|have) (?:(\d+)|a|an) (.+?)(?: with (.+?))?(?:\s|$)",
        r"put (?:(\d+)|a|an) (.+?)(?: with (.+?))? in (?:my |the )?cart",
        r"order (?:(\d+)|a|an) (.+?)(?: with (.+?))?(?:\s|$)"
    ]

    REMOVE_PATTERNS = [
        r"remove (.+?) from (?:my |the )?cart",
        r"delete (.+?) from (?:my |the )?cart",
        r"take (.+?) out of (?:my |the )?cart"
    ]

    SHOW_PATTERNS = [
        r"show (?:my |the )?cart",
        r"what(?:'s| is) in (?:my |the )?cart",
        r"view (?:my |the )?cart",
        r"check (?:my |the )?cart"
    ]

    CLEAR_PATTERNS = [
        r"clear (?:my |the )?cart",
        r"empty (?:my |the )?cart",
        r"remove everything from (?:my |the )?cart",
        r"start(?:| a) new cart"
    ]

    @classmethod
    def parse_command(cls, query: str) -> Dict:
        """Parse cart-related commands from natural language"""
        query = query.lower().strip()

        # Check for show cart command
        for pattern in cls.SHOW_PATTERNS:
            if re.search(pattern, query):
                return {
                    "command": "show",
                    "item_name": None,
                    "quantity": None,
                    "special_requests": None
                }

        # Check for clear cart command
        for pattern in cls.CLEAR_PATTERNS:
            if re.search(pattern, query):
                return {
                    "command": "clear",
                    "item_name": None,
                    "quantity": None,
                    "special_requests": None
                }

        # Check for add commands
        for pattern in cls.ADD_PATTERNS:
            match = re.search(pattern, query)
            if match:
                quantity_str, item_name, special_requests = match.groups()
                quantity = int(quantity_str) if quantity_str else 1
                return {
                    "command": "add",
                    "item_name": item_name.strip(),
                    "quantity": quantity,
                    "special_requests": special_requests.strip() if special_requests else None
                }

        # Check for remove commands
        for pattern in cls.REMOVE_PATTERNS:
            match = re.search(pattern, query)
            if match:
                item_name = match.group(1)
                return {
                    "command": "remove",
                    "item_name": item_name.strip(),
                    "quantity": None,
                    "special_requests": None
                }

        # No cart command found
        return {
            "command": None,
            "item_name": None,
            "quantity": None,
            "special_requests": None
        }

    # ✅ REMOVED: Duplicate parsing logic that was at the end of the method

    @staticmethod
    def text_to_number(text: str) -> Optional[int]:
        """Convert text numbers to integers"""
        number_map = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        return number_map.get(text.lower())