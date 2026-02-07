import os
import time
from typing import Dict, Any, List, Optional, Callable

# Import core components
from core.db import add_memory, get_memories, update_memory_decay
from core.memory_extractor import extract_memory_from_input
from core.memory_retriever import retrieve_relevant_memories, detect_intent
from core.memory_injector import inject_memories

class MemoryController:
    """
    Orchestrates the Long-Form Memory lifecycle:
    Extraction -> Persistence -> Retrieval -> Injection -> Response
    """
    
    def __init__(self, llm_response_func: Callable, llm_extract_func: Callable):
        """
        Args:
            llm_response_func: Function to generate chat response (system_prompt, user_msg) -> str
            llm_extract_func: Function to extract JSON memory (prompt) -> json_str
            
        Dependency injection allows swapping LLM providers or mocking for tests.
        """
        self.llm_response_func = llm_response_func
        self.llm_extract_func = llm_extract_func
        
    def process_turn(self, user_input: str, turn_number: int) -> Dict[str, Any]:
        """
        Full pipeline for a single conversation turn.
        
        Returns:
            Dict containing:
            - response: The assistant's reply
            - extracted_memories: What was learned this turn
            - retrieved_memories: What was recalled
            - intent: Detected user intent
        """
        start_time = time.time()
        
        # 1. Extraction (Fire and Forget in async world, but sync here for correctness)
        # We extract BEFORE generating response to capture immediate corrections/facts
        extracted_memories = extract_memory_from_input(
            user_input, 
            turn_number, 
            self.llm_extract_func
        )
        
        # 2. Persistence
        for mem in extracted_memories:
            try:
                add_memory(
                    memory_type=mem["type"],
                    key=mem["key"],
                    value=mem["value"],
                    confidence=mem["confidence"],
                    source_turn=mem["source_turn"]
                )
            except Exception as e:
                print(f"Failed to persist memory: {e}")

        # 3. Hybrid Intent Detection
        # Try heuristic first (fast, cheap)
        intent = detect_intent(user_input)
        
        # If heuristic is weak (CHIT_CHAT) but input is substantial, try LLM fallback
        if intent == "CHIT_CHAT" and len(user_input.split()) > 3:
             # Fast, stateless classification
             fallback_intent = self._get_fallback_intent(user_input)
             if fallback_intent != "UNKNOWN":
                 intent = fallback_intent
        
        # 4. Retrieval
        # We define a helper to fetch by type from DB
        def fetch_by_types(types: List[str]) -> List[Dict[str, Any]]:
            return get_memories(memory_types=types, limit=50) # fetch candidates
        
        # We need to import the map from retriever to know what to fetch for the new intent
        from core.memory_retriever import INTENT_MEMORY_MAP
        target_types = INTENT_MEMORY_MAP.get(intent, [])
        
        # Explicitly fetch if we have a valid intent, even if the retriever's internal heuristic check assumes "CHIT_CHAT"
        # We bypass the retriever's internal detection if we already have a better intent
        
        # Actually, retrieve_relevant_memories internally calls detect_intent again.
        # We should modify retrieve_relevant_memories OR just pass the types directly.
        # To avoid changing the signature of retrieve_relevant_memories too much, we will just pass the types logic here
        # But wait, retrieve_relevant_memories does the scoring...
        
        # Let's fix this by manually calling the inner logic of retrieval since we are the controller.
        # Or better, we trust our 'intent' and pass it? 
        # The current retrieve_relevant_memories signature is: (user_input, turn_number, fetch_memories_func, top_k)
        # It calls detect_intent internally. We can't easily override it without changing the file.
        # HOWEVER, the Prompt says "Modify memory_controller.py accordingly".
        
        # So we will replicate the retrieval orchestration here using the helpers we have.
        candidates = fetch_by_types(target_types) if target_types else []
        retrieved_memories = []
        
        if candidates:
            # We import specific scoring logic or reimplement the sorting here? 
            # Reusing the function is better. Let's rely on the function but we need to ensure IT uses the extracted intent.
            # Since we can't pass intent, we might get a mismatch.
            # BUT, we can make `fetch_by_types` closure smart.
            # If the retrieve_relevant_memories calls detect_intent and gets "CHIT_CHAT", it returns [].
            
            # SOLUTION: We will just do the scoring here if we have candidates.
            from core.memory_retriever import calculate_relevance
            
            scored_memories = []
            for memory in candidates:
                relevance = calculate_relevance(memory, user_input)
                confidence = memory.get('confidence', 1.0)
                decay = memory.get('decay_score', 1.0)
                final_score = relevance * confidence * decay
                
                if final_score > 0.12: # Slightly lower threshold for robustness
                    scored_memories.append({**memory, "retrieval_score": final_score})
            
            scored_memories.sort(key=lambda x: x["retrieval_score"], reverse=True)
            retrieved_memories = scored_memories[:3] # Top 3

        # 5. Injection
        system_instructions = inject_memories(retrieved_memories)
        
        # 6. Response Generation
        # ROBUST SYSTEM PROMPT (Fixes Problem 1)
        system_prompt = (
            "You are a highly capable AI Assistant with distinct Long-Term Memory.\n"
            "ROLE: You are not just a chat bot; you are a proactive planner and simulator.\n"
            "   - If asked to do something physical (call, email, drive), SIMULATE planning it.\n"
            "   - NEVER say 'I cannot do that' for reasonable assistant tasks. Instead, ask for details or confirm the plan.\n"
            "   - Be helpful, direct, and natural.\n\n"
            "MEMORY RULES:\n"
            "   - The following rules are strict constraints from the user's past.\n"
            "   - You MUST follow them blindly.\n"
            "   - Do NOT say 'I see you prefer...' or 'According to my memory...'. Just act on it.\n"
        )
        
        if system_instructions:
            system_prompt += "\nACTIVE MEMORY CONTEXT:\n"
            for instr in system_instructions:
                system_prompt += f"   * {instr}\n"
        
        response_text = self.llm_response_func(system_prompt, user_input)
        
        # 7. Update Metadata (Decay/Last Used)
        for mem in retrieved_memories:
            try:
                if "memory_id" in mem:
                    update_memory_decay(mem["memory_id"], new_decay=1.0, last_used_turn=turn_number)
            except Exception as e:
                print(f"Failed to update memory stats: {e}")

        return {
            "response": response_text,
            "extracted_memories": extracted_memories,
            "retrieved_memories": retrieved_memories,
            "intent": intent,
            "processing_time": time.time() - start_time
        }

    def _get_fallback_intent(self, user_input: str) -> str:
        """
        Uses LLM to classify intent when heuristics fail.
        Stateless, fast, distinct prompt.
        """
        prompt = (
            "Classify the USER INTENT into one of these exact categories:\n"
            "['SCHEDULING', 'COMMUNICATION', 'PERSONAL_QUERY', 'COMMAND', 'PLANNING', 'CHIT_CHAT']\n"
            "Rules:\n"
            "- 'PLANNING' if the user asks for help, plans, or hypothetical actions.\n"
            "- 'SCHEDULING' for time/dates.\n"
            "- 'COMMUNICATION' for language/tone.\n"
            "- 'CHIT_CHAT' only if it's purely casual.\n\n"
            f"USER INPUT: \"{user_input}\"\n\n"
            "CATEGORY OUTPUT (Just the word):"
        )
        try:
            # We reuse the extract func wrapper or response func? 
            # Response func has temp 0.7, extract has 0.0 and JSON mode.
            # We want deterministic, so we define a quick helper or reuse extract with a wrapper?
            # We'll use the llm_response_func but simpler since we don't have a tailored 'intent' func injected.
            # Actually, reusing llm_extract_func is risky if it enforces JSON.
            # We will use llm_response_func but asking for a single word.
            intent = self.llm_response_func("You are an intent classifier. Output ONLY the category name.", prompt).strip().upper()
            
            valid_intents = {"SCHEDULING", "COMMUNICATION", "PERSONAL_QUERY", "COMMAND", "PLANNING", "CHIT_CHAT"}
            # Clean up potential extra chars
            for v in valid_intents:
                if v in intent:
                    return v
            return "UNKNOWN"
        except:
            return "UNKNOWN"







"""
Full System Explanation (MEMORIZABLE, REPORT-READY)

You said you won’t remember everything — that’s normal.
So here is the one mental model you need.

🧠 One-Line Summary (Use this first)

“We externalize memory from the LLM and treat it as a first-class system with extraction, persistence, retrieval, and behavioral injection.”

🔁 Per-Turn Flow (Say this confidently)

User speaks

Extractor decides what is worth remembering

Database persists long-term memory

Controller detects intent

Retriever selects only relevant memory

Injector converts memory into system rules

LLM generates response under those rules

Memory freshness is updated

No chat replay. No prompt growth.

🧩 Role of Each File (One-Liners)

db.py → Where memory lives

memory_extractor.py → What should be remembered

memory_retriever.py → What matters now

memory_injector.py → How memory influences behavior

memory_controller.py → Who coordinates everything

If you remember only this, you’re safe.

🏆 Why Your System Is Stronger Than Others

Other teams:

extend context window

replay chat

stuff prompts

rely on “LLM magic”

You:

isolate memory

enforce lifecycle

minimize LLM dependence

keep system explainable

That’s a winning design.

🚦 What Comes Next (Clear Roadmap)

Now we move to Phase 3 – LLM Boundary:

👉 core/llm_interface.py

This will:

read API keys from environment

provide llm_response_func

provide llm_extract_func

keep LLM stateless

After that:

.env

venv

requirements.txt

Streamlit UI

Final report & pitch

"""