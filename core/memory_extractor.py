import json
import re
from typing import List, Dict, Any, Callable, Optional

def extract_memory_from_input(
    user_input: str, 
    turn_number: int, 
    llm_extract_func: Optional[Callable[[str], str]] = None
) -> List[Dict[str, Any]]:
    """
    Extracts high-signal long-term memories from user input.
    Only extracts information worth remembering for 1000+ turns.
    """
    if not user_input or len(user_input.strip()) < 3:
        return []
    
    # Use provided LLM function or create a mock for testing
    if llm_extract_func is None:
        print("  ⚠️ No LLM extraction function provided")
        return []
    
    # Don't extract from questions
    if user_input.strip().endswith('?'):
        print("  ⚠️ Skipping extraction for question")
        return []
    
    extraction_prompt = f"""Extract long-term memories from user statement: "{user_input}"

CRITICAL: Output must be a JSON array of memory objects.
Each memory object MUST have: type, key, value, confidence

Examples:
- For "my name is John": [{{"type": "fact", "key": "name", "value": "John", "confidence": 0.95}}]
- For "I like coffee": [{{"type": "preference", "key": "beverage", "value": "coffee", "confidence": 0.9}}]
- If nothing to remember: []

Output JSON array:"""
    
    try:
        print(f"  Sending extraction prompt...")
        raw_response = llm_extract_func(extraction_prompt)
        
        if not raw_response or raw_response.strip() == "":
            print("  ⚠️ Empty response from LLM")
            return []
        
        print(f"  Raw LLM response: {raw_response[:200]}...")
        
        # Parse JSON
        extracted_data = _parse_json_response(raw_response)
        
        if extracted_data is None:
            return []
        
        memories = []
        # Handle different response formats
        if isinstance(extracted_data, dict):
            # Check if it has a "memories" key
            if "memories" in extracted_data and isinstance(extracted_data["memories"], list):
                extracted_data = extracted_data["memories"]
            else:
                # Single memory object
                extracted_data = [extracted_data]
        elif not isinstance(extracted_data, list):
            print(f"  ✗ Expected dict or list, got {type(extracted_data)}")
            return []
        
        for i, item in enumerate(extracted_data):
            memory = _validate_and_create_memory(item, turn_number, user_input)
            if memory:
                memories.append(memory)
                print(f"  ✓ Extracted: {memory['key']} = {memory['value'][:50]}...")
        
        print(f"  Total extracted: {len(memories)}")
        return memories
        
    except Exception as e:
        print(f"✗ Extraction error: {e}")
        import traceback
        traceback.print_exc()
        return []

def _parse_json_response(raw_response: str):
    """Parse JSON response with robust error handling."""
    cleaned = raw_response.strip()
    
    # Remove markdown code blocks
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    cleaned = cleaned.strip()
    
    # Try to parse as-is
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
    
    # Try to find JSON object/array
    try:
        # Look for {...} or [...]
        json_match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    except Exception as e:
        print(f"  Regex parse error: {e}")
    
    print(f"  ✗ Could not parse JSON from: {cleaned[:100]}...")
    return None

def _validate_and_create_memory(item: Dict, turn_number: int, user_input: str) -> Optional[Dict[str, Any]]:
    """Validate memory item and create memory object."""
    try:
        # Check if it's a valid memory object
        if not isinstance(item, dict):
            return None
        
        # Get fields
        mem_type = str(item.get("type", "")).lower().strip()
        key = str(item.get("key", "")).strip()
        value = item.get("value", "")
        
        # Handle null/None value
        if value is None:
            print(f"  ✗ Skipping memory with null value: {key}")
            return None
        
        value = str(value).strip()
        
        # Get confidence
        confidence = item.get("confidence")
        if confidence is None:
            confidence = item.get("confidence_score", item.get("score", 0.8))
        
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.8  # Default
        
        # Validate required fields
        if not mem_type or not key or not value:
            print(f"  ✗ Missing required fields: type={mem_type}, key={key}, value={value}")
            return None
        
        # Skip if confidence is too low or value is problematic
        if confidence < 0.5 or value.lower() in ["null", "none", "", "unknown"]:
            print(f"  ✗ Skipping low-confidence or empty memory: {key}={value} (conf: {confidence})")
            return None
        
        # Validate and normalize type
        valid_types = {"preference", "constraint", "fact", "instruction", "commitment"}
        if mem_type not in valid_types:
            # Try to map to valid type
            if mem_type in ["query", "question"]:
                print(f"  ✗ Skipping query type memory")
                return None
            elif "name" in key.lower() or "location" in key.lower() or "job" in key.lower():
                mem_type = "fact"
            elif "like" in key.lower() or "prefer" in key.lower() or "hate" in key.lower():
                mem_type = "preference"
            else:
                mem_type = "fact"  # Default
        
        # Ensure confidence is reasonable
        confidence = max(0.5, min(1.0, confidence))
        
        # Additional validation based on user input
        if len(value) < 2:  # Too short
            print(f"  ✗ Value too short: '{value}'")
            return None
        
        # Check if this looks like a real value vs placeholder
        if value.lower() in ["n/a", "not specified", "unknown", "null"]:
            print(f"  ✗ Skipping placeholder value: {value}")
            return None
        
        return {
            "type": mem_type,
            "key": key,
            "value": value,
            "confidence": confidence,
            "source_turn": turn_number
        }
        
    except Exception as e:
        print(f"  ✗ Error validating memory: {e}")
        return None

def simple_extract_memory(user_input: str, turn_number: int) -> List[Dict[str, Any]]:
    """Simple regex-based extraction as fallback."""
    import re
    memories = []
    
    user_input_lower = user_input.lower()
    
    # Skip questions
    if user_input_lower.strip().endswith('?'):
        return memories
    
    # Extract name (more robust patterns)
    name_patterns = [
        r"my name is ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"i am ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"call me ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"i'm ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"name is ([A-Za-z]+(?: [A-Za-z]+)*)"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, user_input_lower)
        if match:
            name = match.group(1).title()
            if len(name) > 1:  # Valid name
                memories.append({
                    "type": "fact",
                    "key": "name",
                    "value": name,
                    "confidence": 0.95,
                    "source_turn": turn_number
                })
                print(f"  ✓ Simple extraction: name = {name}")
            break
    
    # Extract preferences (I like/love/enjoy)
    preference_patterns = [
        r"i like to ([a-z]+) ([a-z]+)",
        r"i like ([a-z]+)",
        r"i love ([a-z]+)",
        r"i enjoy ([a-z]+)",
        r"i love to ([a-z]+)"
    ]
    
    for pattern in preference_patterns:
        match = re.search(pattern, user_input_lower)
        if match:
            if len(match.groups()) == 2:
                # Pattern like "I like to play chess"
                activity = f"{match.group(1)} {match.group(2)}"
                key = "activity"
            else:
                # Pattern like "I like chess"
                activity = match.group(1)
                key = "interest"
            
            if len(activity) > 2:
                memories.append({
                    "type": "preference",
                    "key": key,
                    "value": activity,
                    "confidence": 0.85,
                    "source_turn": turn_number
                })
                print(f"  ✓ Simple extraction: preference = {activity}")
            break
    
    # Extract location
    location_patterns = [
        r"i live in ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"i'm from ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"my city is ([A-Za-z]+(?: [A-Za-z]+)*)",
        r"in ([A-Za-z]+(?: [A-Za-z]+)*)"
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, user_input_lower)
        if match:
            location = match.group(1).title()
            memories.append({
                "type": "fact",
                "key": "location",
                "value": location,
                "confidence": 0.90,
                "source_turn": turn_number
            })
            print(f"  ✓ Simple extraction: location = {location}")
            break
    
    return memories