from typing import List, Dict, Any

def inject_memories(retrieved_memories: List[Dict[str, Any]]) -> List[str]:
    """
    Converts retrieved memory objects into behavioral system instructions.
    
    Args:
        retrieved_memories (List[Dict]): usage-ranked memory objects.
        
    Returns:
        List[str]: A list of system prompt lines to inject.
                   Returns empty list if input is empty.
    """
    
    if not retrieved_memories:
        return []
        
    system_instructions: List[str] = []
    
    for memory in retrieved_memories:
        mem_type = memory.get("type")
        key = memory.get("key", "").strip()
        value = memory.get("value", "").strip()
        
        if not key or not value:
            continue
            
        # Formulate instruction based on memory type
        # The goal is behavioral enforcement, not just information listing.
        
        instruction = ""
        
        if mem_type == "preference":
            # "language" -> "Kannada" => "User prefers language: Kannada. Adapt response accordingly."
            instruction = f"User preference ({key}): {value}."
            
        elif mem_type == "constraint":
            # "call_time" -> "after 11 AM" => "Constraint: Do not violate {key}: {value}."
            instruction = f"Strict Constraint: {key} must occur {value}."
            
        elif mem_type == "commitment":
            # "promise" -> "call tomorrow" => "Active Commitment: You must {value}."
            instruction = f"Active Commitment: {value}."
            
        elif mem_type == "instruction":
            # "tone" -> "formal" => "System Rule: {value}."
            instruction = f"Permanent Instruction: {value}."
            
        elif mem_type == "fact":
             # "job" -> "Engineer" => "Context: User is {value}."
            instruction = f"User Context: {key} is {value}."
            
        else:
            # Fallback
            instruction = f"Note: {key} is {value}."
            
        if instruction:
            system_instructions.append(instruction)
            
    return system_instructions


"""
description : 
Purpose

Transforms retrieved long-term memory into system-level behavioral rules that influence the LLM without exposing memory explicitly to the user.

Why this file exists

Retrieval alone is not enough.
Memory must:

influence behavior

without repeating itself

without sounding conversational

without growing the prompt uncontrollably

This file ensures memory is applied, not spoken.

Input
List[MemoryObject]


These are already:

filtered

ranked

Top-K relevant memories

Output
List[str]


Each string is a system instruction, not a chat message.

How transformation works
Memory Type	Injected Behavior
preference	bias how assistant responds
constraint	enforce strict boundaries
commitment	ensure obligations are followed
instruction	permanent system rule
fact	contextual grounding
Example Flow

Memory

{
  "type": "constraint",
  "key": "call_time",
  "value": "after 11 AM"
}


Injected system rule

Strict Constraint: call_time must occur after 11 AM.


The assistant never says this explicitly,
but its behavior is constrained by it.

Key Design Principles

Deterministic

Stateless

No LLM usage

No memory mutation

Safe when empty

🔁 Flow Position (So You Remember)

At runtime:

User sends input

Extractor decides what to remember

DB persists memory

Retriever selects relevant memory

Injector converts memory → behavior rules

Controller assembles system prompt

LLM generates response
"""