from typing import List, Dict, Any

def inject_memories(retrieved_memories: List[Dict[str, Any]]) -> List[str]:
    """
    Converts retrieved memories into natural system instructions.
    Better grouping and formatting for different memory types.
    """
    if not retrieved_memories:
        return []
    
    # Group memories by type for better organization
    instructions = []
    
    for memory in retrieved_memories:
        mem_type = memory.get("type", "").lower()
        key = memory.get("key", "").strip()
        value = memory.get("value", "").strip()
        
        if not key or not value:
            continue
        
        # Format based on memory type and key
        if mem_type == "preference":
            # Normalize preference keys
            if "sport" in key.lower() or "game" in key.lower():
                instructions.append(f"The user enjoys playing {value}")
            elif "like" in key.lower() or "love" in key.lower():
                instructions.append(f"The user likes {value}")
            else:
                instructions.append(f"Preference: {key} = {value}")
                
        elif mem_type == "fact":
            if "name" in key.lower():
                instructions.append(f"The user's name is {value}")
            elif "location" in key.lower():
                instructions.append(f"The user lives in {value}")
            elif "education" in key.lower() or "student" in key.lower():
                instructions.append(f"The user is a {value}")
            elif "degree" in key.lower():
                instructions.append(f"The user is pursuing {value}")
            elif "year" in key.lower():
                instructions.append(f"The user is in {value} of college")
            else:
                instructions.append(f"Fact: {key} = {value}")
                
        elif mem_type == "constraint":
            instructions.append(f"Constraint: {value}")
        elif mem_type == "instruction":
            instructions.append(f"Always: {value}")
        elif mem_type == "commitment":
            instructions.append(f"Commitment: {value}")
        else:
            instructions.append(f"{key}: {value}")
    
    return instructions