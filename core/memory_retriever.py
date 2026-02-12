"""
Description >
Purpose: Selects only relevant memories for the current turn.

Responsibilities
- Detect high-level intent (heuristics, low latency)
- Map intent → eligible memory types
- Fetch only those memory types from DB

Score memories using: relevance × confidence × decay => Return Top-K (≤ 3–5)
crea
What it explicitly does NOT do: 
- Does not call LLM
- Does not modify memory
- Does not inject prompts

Why this matters?

This ensures:
- No prompt overload
- No irrelevant memory leakage
- Deterministic, explainable behavior
"""

from typing import List, Dict, Any, Callable, Optional
import math
import json
from .db import get_db_connection

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


def calculate_relevance(memory, user_input):
    text = f"{memory['key']} {memory['value']}".lower()
    query = user_input.lower()

    score = 0.0

    # Exact key mention
    if memory['key'].lower() in query:
        score += 0.6

    # Phrase containment
    if memory['value'].lower() in query:
        score += 0.6

    # Token overlap
    q_tokens = set(query.split())
    m_tokens = set(text.split())
    overlap = len(q_tokens & m_tokens)

    score += min(0.4, overlap / max(len(m_tokens), 1))

    return min(score, 1.0)


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
        age = turn_number - memory['last_used_turn']
        decay = math.exp(-age / 20)

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