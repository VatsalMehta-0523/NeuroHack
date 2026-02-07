from typing import List, Dict, Any, TypedDict, Optional
import json

# Define the structure for a returnable memory object
# This matches the schema but without database-generated fields (id, timestamps)
class MemoryObject(TypedDict):
    type: str # preference | constraint | commitment | instruction | fact
    key: str
    value: str
    confidence: float
    source_turn: int
    decay_score: float # Initialized to 1.0

def extract_memory_from_input(
    user_input: str, 
    turn_number: int, 
    llm_extract_func=None # Dependency injection for LLM call
) -> List[MemoryObject]:
    """
    Analyzes user input to extract high-signal long-term memories.
    
    Args:
        user_input (str): The raw text from the user.
        turn_number (int): The current conversation turn number.
        llm_extract_func (callable): A function that takes a prompt and returns a JSON string.
                                     Input: str (prompt) -> Output: str (JSON)
                                     If None, returns empty list (safety).

    Returns:
        List[MemoryObject]: A list of extracted memories. Empty if no relevant info found.
    """
    
    if not user_input or not user_input.strip():
        return []

    if llm_extract_func is None:
        # Failsafe: if no LLM provided (e.g. unit testing without mock), return nothing
        return []

    # System prompt strictly for extraction
    # We ask the LLM to be conservative and only extract HIGH VALUE information.
    extraction_prompt = f"""
    You are a Memory Extraction System. Your task is to analyze the USER INPUT and extract crucial, long-term information.
    
    RULES:
    1. Extract ONLY:
       - User PREFERENCES (likes/dislikes/habits)
       - Strict CONSTRAINTS (limitations/boundaries)
       - Long-term COMMITMENTS (promises/agreements)
       - Explicit INSTRUCTIONS (how to behave forever)
       - Stable personal FACTS (name/job/location if permanent)
    2. IGNORE:
       - Casual chatter / Greetings
       - Questions ("What is...?")
       - Context-dependent short-term info
       - Ambiguous statements
    3. JSON OUTPUT FORMAT (List of objects):
       [
         {{
           "type": "preference" | "constraint" | "commitment" | "instruction" | "fact",
           "key": "concise_unique_identifier",
           "value": "clear_extraction_value",
           "confidence": float (0.0 to 1.0)
         }}
       ]
    4. CONFIDENCE THRESHOLD: Only include items with confidence > 0.85.
    5. If nothing relevant is found, return strict empty list: []
    
    USER INPUT (Turn {turn_number}):
    "{user_input}"
    
    JSON OUTPUT:
    """

    try:
        # Call the injected LLM function
        # We expect a pure JSON string response
        raw_response = llm_extract_func(extraction_prompt)
        
        # Parse JSON
        extracted_data = json.loads(raw_response)
        
        if not isinstance(extracted_data, list):
             # basic validation
            return []

        memories: List[MemoryObject] = []
        
        for item in extracted_data:
            # Validate required fields
            if not all(k in item for k in ("type", "key", "value", "confidence")):
                continue
                
            # Validate types
            valid_types = {"preference", "constraint", "commitment", "instruction", "fact"}
            if item["type"] not in valid_types:
                continue
                
            # Validate confidence (Double check logic, though prompt says > 0.85)
            if item["confidence"] < 0.85:
                continue

            # Construct MemoryObject
            memory: MemoryObject = {
                "type": item["type"],
                "key": item["key"],
                "value": item["value"],
                "confidence": item["confidence"],
                "source_turn": turn_number,
                "decay_score": 1.0
            }
            memories.append(memory)
            
        return memories

    except json.JSONDecodeError:
        # LLM failed to produce valid JSON
        # In a real system we might log this, but for now safe fail
        return []
    except Exception as e:
        # Catch-all for other errors
        print(f"Error in memory extraction: {e}")
        return []



"""
description : 

Purpose

Decides whether user input contains long-term memory.

Responsibilities

Analyze one user message

Extract only high-signal information

Reject noise, questions, chatter

Output strict JSON-compatible memory objects

What it explicitly does NOT do

Does not write to DB

Does not retrieve memory

Does not influence responses

Key Safeguards

Confidence threshold (>0.85)

Empty list is a valid outcome

Safe failure on invalid JSON

Why this matters

This prevents:

Memory pollution

Hallucinated facts

Storing irrelevant conversation
"""