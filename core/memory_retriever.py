from typing import List, Dict, Any, Callable, Optional
import math
import json
from .db import get_db_connection

# Intent Detection mappings
# Maps detectable user intents to memory types that should be retrieved
# Intent Detection mappings
# Maps detectable user intents to memory types that should be retrieved
INTENT_MEMORY_MAP = {
    "SCHEDULING": ["preference", "constraint", "commitment", "instruction"],
    "COMMUNICATION": ["preference", "instruction", "fact"], 
    "PERSONAL_QUERY": ["fact", "preference", "commitment"],
    "COMMAND": ["instruction", "constraint"],
    "PLANNING": ["preference", "constraint", "commitment"], # Added PLANNING for better coverage
    "CHIT_CHAT": [] 
}

def detect_intent(user_input: str) -> str:
    """
    Heuristic-based intent detection.
    In a production system, this could be an LLM call, but heuristics constitute a fast, cheap baseline.
    """
    normalized_input = user_input.lower()
    
    # SCHEDULING signals
    if any(keyword in normalized_input for keyword in ["call", "schedule", "meet", "tomorrow", "time", "busy", "free", "calendar"]):
        return "SCHEDULING"
    
    # COMMUNICATION signals (language, tone, medium)
    if any(keyword in normalized_input for keyword in ["language", "speak", "talk", "email", "text", "voice", "kannada", "english"]):
        return "COMMUNICATION"
        
    # PERSONAL_QUERY (About the user or assistant's knowledge of the user)
    if any(keyword in normalized_input for keyword in ["who am i", "my name", "where do i", "do you know", "remember"]):
        return "PERSONAL_QUERY"

    # COMMAND (Direct instruction)
    if any(keyword in normalized_input for keyword in ["always", "never", "remember to", "don't", "do not"]):
        return "COMMAND"

    # PLANNING (Actions, help, simulating)
    if any(keyword in normalized_input for keyword in ["plan", "help me", "can you", "i need to", "organize", "arrange"]):
        return "PLANNING"
        
    return "CHIT_CHAT"

def retrieve_memories(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieves ALL memories for a user from the database.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT user_id, key, value, intent, metadata, created_at, updated_at
            FROM memories
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s;
        """, (user_id, limit))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        memories = []
        for row in rows:
            try:
                metadata = json.loads(row[4]) if row[4] else {}
            except:
                metadata = {}
            
            memories.append({
                'user_id': row[0],
                'key': row[1],
                'value': row[2],
                'intent': row[3],
                'metadata': metadata,
                'created_at': str(row[5]),
                'updated_at': str(row[6])
            })
        
        print(f"✓ Retrieved {len(memories)} memories for user {user_id}")
        return memories
        
    except Exception as e:
        print(f"✗ Memory retrieval failed: {e}")
        return []


def calculate_relevance(
    memory: Dict[str, Any], 
    user_input: str
) -> float:
    """
    Calculates relevance score between a memory and user input.
    Returns 0.0-1.0
    """
    memory_content = (f"{memory.get('key', '')} {memory.get('value', '')}").lower()
    input_tokens = set(user_input.lower().split())
    memory_tokens = set(memory_content.split())
    
    if not memory_tokens or not input_tokens:
        return 0.0
    
    overlap = len(input_tokens.intersection(memory_tokens))
    
    # Boost for exact key match
    if memory.get('key', '').lower() in user_input.lower():
        overlap += 2
    
    if overlap == 0:
        return 0.0
    
    score = min(1.0, overlap / max(len(input_tokens), len(memory_tokens)))
    return score


def retrieve_relevant_memories(
    user_input: str,
    turn_number: int,
    fetch_memories_func: Callable[[List[str]], List[Dict[str, Any]]], # Expected signature: types -> string list
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Retrieves and ranks memories for the current turn.
    
    Args:
        user_input (str): The user's message.
        turn_number (int): Current turn number.
        fetch_memories_func (callable): Function to get memories from DB, filtered by Type.
        top_k (int): Max number of memories to return.

    Returns:
        List[Dict[str, Any]]: Ranked list of memory objects.
    """
    
    # 1. Detect Intent
    intent = detect_intent(user_input)
    target_types = INTENT_MEMORY_MAP.get(intent, [])
    
    if not target_types:
        # If no specific intent mapped, we might fetch "fact" and "preference" broadly if input is short?
        # Or strict adherence: return nothing.
        # Let's be strict to avoid context pollution.
        return []

    # 2. Fetch Candidates
    candidates = fetch_memories_func(target_types)
    if not candidates:
        return []
        
    scored_memories = []
    
    # 3. Score Candidates
    for memory in candidates:
        # Score components
        relevance = calculate_relevance(memory, user_input)
        confidence = memory.get('confidence', 1.0)
        decay = memory.get('decay_score', 1.0)
        
        # Combined Score
        # We weigh relevance highest. If it's not relevant, confidence doesn't matter.
        final_score = relevance * confidence * decay
        
        if final_score > 0.15: # Threshold to cut out low-relevance noise
            scored_memories.append({
                **memory,
                "retrieval_score": final_score
            })
            
    # 4. Rank and Filter
    scored_memories.sort(key=lambda x: x["retrieval_score"], reverse=True)
    
    return scored_memories[:top_k]


def search_memories(user_id: str, query: str, threshold: float = 0.1) -> List[Dict[str, Any]]:
    """
    Searches memories by relevance to the query.
    """
    all_memories = retrieve_memories(user_id, limit=100)
    
    scored_memories = [
        (memory, calculate_relevance(memory, query))
        for memory in all_memories
    ]
    
    # Filter by threshold and sort by score
    relevant = [
        m for m, score in scored_memories 
        if score >= threshold
    ]
    relevant.sort(key=lambda m: calculate_relevance(m, query), reverse=True)
    
    print(f"✓ Found {len(relevant)} relevant memories for query: '{query}'")
    return relevant[:5]


"""
description :
Purpose

Selects only relevant memories for the current turn.

Responsibilities

Detect high-level intent (heuristics, low latency)

Map intent → eligible memory types

Fetch only those memory types from DB

Score memories using:

relevance × confidence × decay


Return Top-K (≤ 3–5)

What it explicitly does NOT do

Does not call LLM

Does not modify memory

Does not inject prompts

Why this matters

This ensures:

No prompt overload

No irrelevant memory leakage

Deterministic, explainable behavior

🔁 FLOW SO FAR (Turn-by-Turn)
Turn N:

User input arrives

memory_extractor decides if anything is worth remembering

Memory (if any) is stored in DB

Same Turn:

memory_retriever infers intent

Retrieves only relevant memories

Scores and filters to Top-K

(Injection and orchestration come next)



🧠 How to Answer “Why not embeddings / RAG?”

Use this exact line:

“Memory here is structured behavioral data, not unstructured knowledge. Using embeddings would increase latency and reduce explainability without improving correctness.”

This is a strong answer.

Final reassurance

You are not expected to memorize all this.
That’s why writing this explanation now is the right move.

You’ve:

Identified real vs superficial flaws

Prioritized system guarantees

Asked for defensibility, not just code

That’s senior-level thinking.
"""