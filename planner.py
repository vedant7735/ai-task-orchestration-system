# planner.py (Deterministic Rule-Based)

import re
from typing import Dict, List


class Planner:
    """
    Deterministic task decomposition.
    No LLM. Pure logic.
    """

    def __init__(self):
        self.action_verbs = {
            'explain': 'EXPLAIN',
            'describe': 'EXPLAIN',
            'what is': 'EXPLAIN',
            'tell me about': 'EXPLAIN',
            
            'write': 'CODE',
            'code': 'CODE',
            'implement': 'CODE',
            'create': 'CODE',
            'function': 'CODE',
            'program': 'CODE',
            
            'calculate': 'CALCULATE',
            'compute': 'CALCULATE',
            'solve': 'CALCULATE',
            'evaluate': 'CALCULATE',
        }

    def analyze_intent(self, raw_intent: str) -> dict:
        """
        Main entry point: convert user intent to structured tasks.
        """
        intent_lower = raw_intent.lower()

        # Rule 1: List pattern (highest priority)
        if self._is_list_request(raw_intent):
            return self._decompose_list(raw_intent)

        # Rule 2: Multi-part request with 'and'
        if ' and ' in intent_lower and ',' not in raw_intent:
            return self._decompose_conjunction(raw_intent)

        # Rule 3: Comparison pattern
        if self._is_comparison(intent_lower):
            return self._decompose_comparison(raw_intent)

        # Rule 4: Sequential indicators
        if self._is_sequential(intent_lower):
            return self._decompose_sequential(raw_intent)

        # Default: Single task
        return self._create_single_task(raw_intent)

    # ==================== PATTERN DETECTION ====================

    def _is_list_request(self, text: str) -> bool:
        """
        Detect list patterns:
        - "X, Y, and Z" (explicit commas)
        - "three things" / "five languages" (numeric indicators)
        - "top 5" / "best 3" (superlatives with numbers)
        """
        # Pattern 1: Has commas
        if bool(re.search(r'\w+\s*,\s*\w+', text)):
            return True
    
        # Pattern 2: Numeric quantifiers
        numeric_patterns = [
            r'\b(three|four|five|six|seven|eight|nine|ten)\b',
            r'\b\d+\b',
            r'\btop\s+\d+\b',
            r'\bbest\s+\d+\b',
            r'\bmain\s+\d+\b'
        ]
    
        text_lower = text.lower()
        for pattern in numeric_patterns:
            if re.search(pattern, text_lower):
                return True
    
        return False

    def _is_comparison(self, text: str) -> bool:
        """
        Detect: "compare X and Y", "difference between X and Y"
        """
        comparison_patterns = [
            'compare', 'difference between', 'vs', 'versus',
            'contrast', 'distinguish'
        ]
        return any(p in text for p in comparison_patterns)

    def _is_sequential(self, text: str) -> bool:
        """
        Detect: "first X then Y", "X and then Y"
        """
        return 'then' in text or 'after' in text or 'next' in text

    # ==================== DECOMPOSITION STRATEGIES ====================
    
    def _decompose_list(self, text: str) -> dict:
        """
        Handle both explicit lists and numeric requests.
        """
        action = self._extract_action(text)
    
        # Try to extract explicit items first
        items = self._extract_list_items(text)
    
        # If no items found, but we detected a number, create generic tasks
        if len(items) <= 1:
            count = self._extract_count(text)
            if count > 1:
                items = [f"option {i+1}" for i in range(min(count, 5))]
    
        if len(items) <= 1:
            return self._create_single_task(text)

        tasks = []
        for i, item in enumerate(items):
            # If item is generic ("option 1"), use original intent + qualifier
            if item.startswith("option"):
                task_text = f"{action} {self._extract_subject(text)} (part {i+1})"
            else:
                task_text = f"{action} {item}".strip()
        
            tasks.append({
                "id": f"t{i+1}",
                "type": self._classify_task(task_text),
                "target": task_text,
                "depends_on": []
            })

        print(f"\n[PLAN]")
        for t in tasks:
            print(f"{t['id']} -> {t['type']} | depends_on={t['depends_on']}")

        return {
            "status": "ready",
            "mode": "decompose",
            "intent": text,
            "tasks": tasks
        }

    def _decompose_conjunction(self, text: str) -> dict:
        """
        "write a function and test it" →
        [write a function, test it]
        """
        parts = text.split(' and ')
        
        if len(parts) <= 1:
            return self._create_single_task(text)

        tasks = []
        for i, part in enumerate(parts[:3]):  # Max 3
            part = part.strip()
            
            tasks.append({
                "id": f"t{i+1}",
                "type": self._classify_task(part),
                "target": part,
                "depends_on": [f"t{i}"] if i > 0 else []
            })

        print(f"\n[PLAN]")
        for t in tasks:
            print(f"{t['id']} -> {t['type']} | depends_on={t['depends_on']}")

        return {
            "status": "ready",
            "mode": "decompose",
            "intent": text,
            "tasks": tasks
        }

    def _decompose_comparison(self, text: str) -> dict:
        """
        "compare X and Y" →
        [explain X, explain Y, compare them]
        """
        # Extract items being compared
        items = self._extract_comparison_items(text)
        
        if len(items) < 2:
            return self._create_single_task(text)

        tasks = []
        
        # Task 1: Explain first item
        tasks.append({
            "id": "t1",
            "type": "EXPLAIN",
            "target": f"explain {items[0]}",
            "depends_on": []
        })
        
        # Task 2: Explain second item
        tasks.append({
            "id": "t2",
            "type": "EXPLAIN",
            "target": f"explain {items[1]}",
            "depends_on": []
        })
        
        # Task 3: Compare them
        tasks.append({
            "id": "t3",
            "type": "EXPLAIN",
            "target": f"compare {items[0]} and {items[1]}",
            "depends_on": ["t1", "t2"]
        })

        print(f"\n[PLAN]")
        for t in tasks:
            print(f"{t['id']} -> {t['type']} | depends_on={t['depends_on']}")

        return {
            "status": "ready",
            "mode": "decompose",
            "intent": text,
            "tasks": tasks
        }

    def _decompose_sequential(self, text: str) -> dict:
        """
        "first X then Y" →
        [X, Y] with dependency
        """
        # Split on temporal markers
        parts = re.split(r'\bthen\b|\bafter\b|\bnext\b', text, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) <= 1:
            return self._create_single_task(text)

        tasks = []
        for i, part in enumerate(parts[:3]):
            # Remove "first", "second" prefixes
            part = re.sub(r'\b(first|second|third)\b', '', part, flags=re.IGNORECASE).strip()
            
            tasks.append({
                "id": f"t{i+1}",
                "type": self._classify_task(part),
                "target": part,
                "depends_on": [f"t{i}"] if i > 0 else []
            })

        print(f"\n[PLAN]")
        for t in tasks:
            print(f"{t['id']} -> {t['type']} | depends_on={t['depends_on']}")

        return {
            "status": "ready",
            "mode": "decompose",
            "intent": text,
            "tasks": tasks
        }

    def _create_single_task(self, text: str) -> dict:
        """
        Fallback: single task, direct mode.
        """
        print(f"\n[PLAN]\nt1 -> {self._classify_task(text)} | depends_on=[]")
        
        return {
            "status": "ready",
            "mode": "direct",
            "intent": text,
            "tasks": [
                {
                    "id": "t1",
                    "type": self._classify_task(text),
                    "target": text,
                    "depends_on": []
                }
            ]
        }

    # ==================== EXTRACTION HELPERS ====================

    def _extract_action(self, text: str) -> str:
        """
        Extract the primary action verb.
        """
        text_lower = text.lower()
        
        for verb in self.action_verbs.keys():
            if verb in text_lower:
                return verb
        
        return "process"

    def _extract_list_items(self, text: str) -> List[str]:
        """
        Extract items from: "X, Y, and Z"
        """
        # Remove action verb first
        action = self._extract_action(text)
        text_cleaned = re.sub(rf'\b{action}\b', '', text, flags=re.IGNORECASE).strip()
        
        # Split on commas and 'and'
        items = re.split(r',\s*|\s+and\s+', text_cleaned)
        items = [item.strip() for item in items if item.strip() and len(item.strip()) > 1]
        
        # Filter out noise words
        noise = ['with', 'using', 'for', 'in', 'example', 'examples', 'code']
        items = [item for item in items if item.lower() not in noise]
        
        return items[:5]  # Max 5 items

    def _extract_comparison_items(self, text: str) -> List[str]:
        """
        Extract X and Y from "compare X and Y"
        """
        # Remove comparison keywords
        cleaned = re.sub(r'\b(compare|difference between|vs|versus|contrast)\b', '', text, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        # Split on 'and'
        items = re.split(r'\s+and\s+', cleaned)
        items = [item.strip() for item in items if item.strip()]
        
        return items[:2]  # Only take first 2

    def _extract_count(self, text: str) -> int:
        """
        Extract numeric count from text.
        "three languages" → 3
        "top 5 frameworks" → 5
        """
        text_lower = text.lower()
    
        # Word numbers
        word_to_num = {
            'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8,
            'nine': 9, 'ten': 10
        }
    
        for word, num in word_to_num.items():
            if word in text_lower:
                return num
    
        # Digit numbers
        match = re.search(r'\b(\d+)\b', text)
        if match:
            return int(match.group(1))
    
        return 1

    def _extract_subject(self, text: str) -> str:
        """
        Extract the main subject.
        "explain three best coding languages" → "coding languages"
        """
        # Remove action verb and numbers
        action = self._extract_action(text)
        cleaned = re.sub(rf'\b{action}\b', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(three|four|five|\d+)\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(best|top|main)\b', '', cleaned, flags=re.IGNORECASE)
    
        return cleaned.strip()

    # ==================== CLASSIFICATION ====================

    def _classify_task(self, text: str) -> str:
        """
        Determine task type based on keywords.
        """
        text_lower = text.lower()

        for keyword, task_type in self.action_verbs.items():
            if keyword in text_lower:
                return task_type

        return "EXPLAIN"


    def _decompose_list(self, text: str) -> dict:
        """
        Handle both explicit lists and numeric requests.
        """
        action = self._extract_action(text)
    
        # Try to extract explicit items first
        items = self._extract_list_items(text)
    
        # If no items found, but we detected a number, create generic tasks
        if len(items) <= 1:
            count = self._extract_count(text)
            if count > 1:
                items = [f"option {i+1}" for i in range(min(count, 5))]
    
        if len(items) <= 1:
            return self._create_single_task(text)

        tasks = []
        for i, item in enumerate(items):
            # If item is generic ("option 1"), use original intent + qualifier
            if item.startswith("option"):
                task_text = f"{action} {self._extract_subject(text)} (part {i+1})"
            else:
                task_text = f"{action} {item}".strip()
        
            tasks.append({
                "id": f"t{i+1}",
                "type": self._classify_task(task_text),
                "target": task_text,
                "depends_on": []
            })

        print(f"\n[PLAN]")
        for t in tasks:
            print(f"{t['id']} -> {t['type']} | depends_on={t['depends_on']}")

        return {
            "status": "ready",
            "mode": "decompose",
            "intent": text,
            "tasks": tasks
        }