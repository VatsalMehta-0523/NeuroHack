import os
import time
import json
import math
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime

# Import core components
from core.db import (
    add_memory, 
    get_memories_by_types, 
    update_memory_decay,
    record_memory_usage,
    get_memory_statistics
)
from core.memory_extractor import extract_memory_from_input
from core.memory_injector import inject_memories
from core.llm_interface import get_llm_response

class LongTermMemoryController:
    """
    Orchestrates the Long-Form Memory lifecycle for 1000+ turn conversations.
    Implements memory persistence, decay, and intelligent retrieval with semantic understanding.
    """
    
    def __init__(self, user_id: str, llm_response_func: Callable, llm_extract_func: Callable):
        """
        Args:
            user_id: Unique identifier for the user
            llm_response_func: Function to generate chat response
            llm_extract_func: Function to extract JSON memory
        """
        self.user_id = user_id
        self.llm_response_func = llm_response_func
        self.llm_extract_func = llm_extract_func
        self.conversation_turns = 0
        self.memory_cache = {}  # Cache for recently used memories
        self.decay_factor = 0.95  # Exponential decay per 100 turns without use
        
        # Semantic concept mapping for intelligent retrieval
        self.CONCEPT_MAP = {
            # Personal information
            "name": ["name", "called", "call", "identity", "who"],
            "identity": ["name", "person", "individual", "who"],
            
            # Education
            "education": ["study", "student", "college", "university", "school", "learn", "education"],
            "degree": ["degree", "course", "major", "field", "program", "pursuing", "studying"],
            "year": ["year", "semester", "grade", "level", "class"],
            "subjects": ["subjects", "courses", "classes", "modules"],
            
            # Hobbies & Interests
            "hobbies": ["hobbies", "interests", "activities", "pastimes", "free time", "leisure"],
            "sports": ["sports", "games", "play", "cricket", "football", "basketball", "tennis"],
            "games": ["games", "chess", "video games", "board games", "play", "gaming"],
            "preferences": ["like", "love", "enjoy", "prefer", "favorite", "hate", "dislike"],
            
            # Personal facts
            "location": ["live", "location", "city", "from", "country", "residence"],
            "job": ["job", "work", "occupation", "profession", "career", "employer"],
            "age": ["age", "old", "years old", "birthday"],
            
            # Relationships
            "family": ["family", "parents", "mother", "father", "siblings", "brother", "sister"],
            "friends": ["friends", "companions", "buddies", "peers"],
            
            # Skills & Abilities
            "skills": ["skills", "abilities", "talents", "expertise", "know", "can do"],
            "languages": ["languages", "speak", "language", "bilingual", "multilingual"],
            
            # Goals & Plans
            "goals": ["goals", "aspirations", "dreams", "ambitions", "want", "wish"],
            "plans": ["plans", "intentions", "future", "tomorrow", "next", "will"],
        }
        
        # Intent mapping for memory retrieval
        self.INTENT_MEMORY_MAP = {
            "SCHEDULING": ["preference", "constraint", "commitment"],
            "COMMUNICATION": ["preference", "instruction", "fact"],
            "PERSONAL_QUERY": ["fact", "preference", "commitment"],  # Broad for personal questions
            "GENERAL_KNOWLEDGE": [],  # Don't retrieve personal memories for general knowledge
            "COMMAND": ["instruction", "constraint"],
            "PLANNING": ["preference", "constraint", "commitment"],
            "CHIT_CHAT": []  # For casual conversation
        }
        
        print(f"✓ Long-term memory controller initialized for user: {user_id}")
    
    def detect_intent(self, user_input: str) -> str:
        """
        Enhanced intent detection with better personal query handling.
        """
        normalized_input = user_input.lower().strip()
        
        # Personal questions about the user
        personal_question_keywords = [
            "my name", "who am i", "what is my", "do you know", "remember",
            "my hobbies", "my interests", "what do i", "what are my",
            "tell me about myself", "what about me", "my favorite",
            "do you know my", "what do you know about me"
        ]
        
        if any(kw in normalized_input for kw in personal_question_keywords):
            return "PERSONAL_QUERY"
        
        # General knowledge questions (not about the user)
        knowledge_question_keywords = [
            "which is", "what is", "who is", "where is", "when is",
            "national bird", "national animal", "capital of", "population of"
        ]
        
        if any(kw in normalized_input for kw in knowledge_question_keywords):
            return "GENERAL_KNOWLEDGE"
        
        # Heuristic detection (fast)
        if any(kw in normalized_input for kw in ["call", "schedule", "meet", "tomorrow", "time", "calendar", "appointment"]):
            return "SCHEDULING"
        elif any(kw in normalized_input for kw in ["language", "speak", "talk", "email", "text", "tone", "communicate"]):
            return "COMMUNICATION"
        elif any(kw in normalized_input for kw in ["always", "never", "remember to", "don't", "do not", "must", "should"]):
            return "COMMAND"
        elif any(kw in normalized_input for kw in ["plan", "help me", "can you", "i need to", "organize", "create", "make"]):
            return "PLANNING"
        elif len(normalized_input.split()) < 4 or normalized_input.endswith('?'):
            return "CHIT_CHAT"
        
        # Default to personal query for anything about the user
        if "i " in normalized_input or "my " in normalized_input:
            return "PERSONAL_QUERY"
        
        return "CHIT_CHAT"

    def calculate_memory_decay(self, memory: Dict[str, Any], current_turn: int) -> float:
        """
        Calculates decay score based on recency of use.
        Exponential decay: decay = base^(turns_since_last_use / 100)
        """
        last_used = memory.get('last_used_turn', memory.get('source_turn', current_turn))
        turns_since_use = max(0, current_turn - last_used)
        
        if turns_since_use == 0:
            return 1.0
        
        # Exponential decay: loses 5% relevance every 100 turns without use
        decay = math.pow(self.decay_factor, turns_since_use / 100)
        
        # Never decay below 0.1 (always somewhat retrievable)
        return max(0.1, decay)
    
    def calculate_semantic_similarity(self, memory: Dict[str, Any], user_input: str) -> float:
        """
        Calculates semantic similarity between memory and user input.
        Uses concept mapping for intelligent matching.
        """
        user_input_lower = user_input.lower()
        memory_key = memory.get('key', '').lower()
        memory_value = str(memory.get('value', '')).lower()
        memory_text = f"{memory_key} {memory_value}"
        
        similarity_score = 0.0
        
        # 1. Direct keyword matching (highest priority)
        input_words = set(user_input_lower.split())
        memory_words = set(memory_text.split())
        
        direct_matches = input_words.intersection(memory_words)
        if direct_matches:
            similarity_score += min(0.5, len(direct_matches) * 0.1)
        
        # 2. Semantic concept matching - IMPROVED
        for concept, keywords in self.CONCEPT_MAP.items():
            # Check if user input mentions this concept
            concept_in_input = any(keyword in user_input_lower for keyword in keywords)
            
            # Check if memory relates to this concept
            concept_in_memory = (
                concept in memory_key or 
                concept in memory_value or
                any(keyword in memory_text for keyword in keywords)
            )
            
            if concept_in_input and concept_in_memory:
                similarity_score += 0.6  # Increased from 0.4
                break  # Found a match, good enough
        
        # 3. Special case: hobbies/interests - IMPROVED
        hobby_keywords = ["hobby", "hobbies", "interest", "interests", "activities", "pastime", "pastimes"]
        if any(keyword in user_input_lower for keyword in hobby_keywords):
            # Check if memory is about sports, games, or preferences
            memory_type = memory.get('type', '')
            memory_key_lower = memory_key.lower()
            
            hobby_related = (
                memory_type == "preference" or
                "sport" in memory_key_lower or
                "game" in memory_key_lower or
                "play" in memory_key_lower or
                "like" in memory_key_lower or
                "love" in memory_key_lower or
                "enjoy" in memory_key_lower or
                "cricket" in memory_value or
                "chess" in memory_value or
                "activity" in memory_key_lower
            )
            
            if hobby_related:
                similarity_score += 0.8  # Increased from 0.6
        
        # 4. Partial matching for values
        for word in input_words:
            if len(word) > 3 and (word in memory_value or word in memory_key):
                similarity_score += 0.3  # Increased from 0.2
                break
        
        # 5. Category-based matching - IMPROVED
        memory_type = memory.get('type', '')
        if "name" in user_input_lower and ("name" in memory_key or memory_value in user_input_lower):
            similarity_score += 0.9  # Increased from 0.8
        elif "hobby" in user_input_lower or "interest" in user_input_lower:
            if memory_type == "preference" or "sport" in memory_key or "game" in memory_key:
                similarity_score += 0.7
        elif "study" in user_input_lower or "student" in user_input_lower:
            if "education" in memory_text or "student" in memory_text or "college" in memory_text:
                similarity_score += 0.8  # Increased from 0.7
        elif ("like" in user_input_lower or "love" in user_input_lower or "enjoy" in user_input_lower) and memory_type == "preference":
            similarity_score += 0.7  # Increased from 0.6
        
        return min(1.0, similarity_score)

    def calculate_relevance(self, memory: Dict[str, Any], user_input: str, intent: str) -> float:
        """
        Calculates final relevance score combining multiple factors.
        """
        # 1. Semantic similarity
        semantic_score = self.calculate_semantic_similarity(memory, user_input)
        
        # 2. Intent matching
        memory_type = memory.get('type', '')
        target_types = self.INTENT_MEMORY_MAP.get(intent, [])
        intent_score = 0.3 if memory_type in target_types else 0.0
        
        # 3. Combine scores (semantic is more important)
        base_score = semantic_score * 0.7 + intent_score * 0.3
        
        # 4. Apply decay and confidence
        decay = memory.get('current_decay', 1.0)
        confidence = memory.get('confidence', 0.5)
        
        final_score = base_score * decay * confidence
        
        # Debug logging
        if final_score > 0.15:
            print(f"    Memory '{memory.get('key')}': semantic={semantic_score:.2f}, "
                  f"intent={intent_score:.2f}, decay={decay:.2f}, "
                  f"conf={confidence:.2f}, final={final_score:.2f}")
        
        return min(1.0, max(0.0, final_score))
    
    def retrieve_relevant_memories(self, user_input: str, current_turn: int) -> List[Dict[str, Any]]:
        """
        Retrieves and ranks memories relevant to the current input.
        Now with semantic understanding for better matching.
        """
        intent = self.detect_intent(user_input)
        
        # For personal queries, consider all memory types
        if intent == "PERSONAL_QUERY":
            target_types = ["fact", "preference", "commitment", "constraint", "instruction"]
        else:
            target_types = self.INTENT_MEMORY_MAP.get(intent, [])
        
        print(f"  Intent: {intent}, Target types: {target_types}")
        
        # Fetch candidate memories
        candidates = get_memories_by_types(self.user_id, target_types, limit=50)
        
        if not candidates:
            print("  No candidate memories found")
            return []
        
        print(f"  Found {len(candidates)} candidate memories")
        
        # Score and rank candidates
        scored_memories = []
        for memory in candidates:
            # Calculate decay based on current turn
            decay = self.calculate_memory_decay(memory, current_turn)
            memory['current_decay'] = decay
            
            # Calculate relevance
            relevance = self.calculate_relevance(memory, user_input, intent)
            
            if relevance > 0.15:  # Threshold to filter out irrelevant
                memory['retrieval_score'] = relevance
                scored_memories.append(memory)
        
        # Sort by score and take top 3
        scored_memories.sort(key=lambda x: x['retrieval_score'], reverse=True)
        selected = scored_memories[:3]
        
        print(f"  Selected {len(selected)} relevant memories")
        
        # Update cache and record usage
        for mem in selected:
            memory_id = mem.get('memory_id')
            if memory_id:
                self.memory_cache[memory_id] = mem
                # Update decay in database (reset decay on use)
                update_memory_decay(memory_id, 1.0, current_turn)
                record_memory_usage(memory_id, current_turn, mem['retrieval_score'])
        
        return selected
    
    def process_turn(self, user_input: str, turn_number: int) -> Dict[str, Any]:
        """
        Full pipeline for a single conversation turn with long-term memory.
        """
        start_time = time.time()
        self.conversation_turns = turn_number
        
        print(f"\n{'='*60}")
        print(f"TURN {turn_number}: Processing input...")
        print(f"USER: {user_input}")
        
        # 1. EXTRACTION: Extract new memories from current input
        try:
            # Better extraction logic - don't skip too aggressively
            should_extract = True
            
            # Don't extract from pure questions (starting with what, who, where, etc.)
            question_starters = ["what", "who", "where", "when", "why", "how", "do you", "can you", "will you"]
            user_input_lower = user_input.lower().strip()
            
            # Check if it's a question about the user's own information
            is_personal_question = (
                "my " in user_input_lower or 
                "i " in user_input_lower or
                "me " in user_input_lower
            )
            
            # Check if it's a factual statement (not a question)
            is_factual_statement = (
                len(user_input.split()) >= 3 and
                not user_input_lower.endswith('?') and
                not any(user_input_lower.startswith(starter) for starter in question_starters)
            )
            
            if is_factual_statement or (is_personal_question and not user_input_lower.endswith('?')):
                extracted_memories = extract_memory_from_input(
                    user_input=user_input,
                    turn_number=turn_number,
                    llm_extract_func=self.llm_extract_func
                )
            else:
                extracted_memories = []
                print("  ⚠️ Skipping extraction (question or command)")
                
        except Exception as e:
            print(f"  ✗ Extraction failed: {e}")
            extracted_memories = []
        
        # 2. PERSISTENCE: Store new memories
        stored_ids = []
        for mem in extracted_memories:
            try:
                memory_id = add_memory(
                    user_id=self.user_id,
                    memory_type=mem["type"],
                    key=mem["key"],
                    value=mem["value"],
                    confidence=mem["confidence"],
                    source_turn=turn_number
                )
                stored_ids.append(memory_id)
                print(f"  ✓ Stored memory: {mem['key']} = {mem['value'][:50]}...")
            except Exception as e:
                print(f"  ✗ Failed to store memory: {e}")
        
        # 3. RETRIEVAL: Get relevant memories from long-term storage
        retrieved_memories = self.retrieve_relevant_memories(user_input, turn_number)
        
        # 4. INJECTION: Convert memories to system instructions
        system_instructions = inject_memories(retrieved_memories)
        
        # 5. RESPONSE GENERATION: Create response with memory context
        system_prompt = self._build_system_prompt(system_instructions, turn_number, user_input)
        response = self.llm_response_func(system_prompt, user_input)
        
        # 6. Update statistics
        processing_time = time.time() - start_time
        
        result = {
            "response": response,
            "extracted_memories": extracted_memories,
            "retrieved_memories": retrieved_memories,
            "intent": self.detect_intent(user_input),
            "processing_time": round(processing_time, 3),
            "turn_number": turn_number,
            "memory_metrics": {
                "extracted": len(extracted_memories),
                "retrieved": len(retrieved_memories),
                "avg_relevance": round(
                    sum(m.get('retrieval_score', 0) for m in retrieved_memories) / 
                    max(len(retrieved_memories), 1), 
                    3
                )
            }
        }
        
        # Print summary
        print(f"  Memories extracted: {len(extracted_memories)}")
        print(f"  Memories retrieved: {len(retrieved_memories)}")
        if retrieved_memories:
            print(f"  Top memory: {retrieved_memories[0].get('key')} "
                  f"(score: {retrieved_memories[0].get('retrieval_score', 0):.2f})")
        print(f"  Response time: {processing_time:.2f}s")
        print(f"  Response: {response[:100]}...")
        print("=" * 60)
        
        return result
    
    def _build_system_prompt(self, system_instructions: List[str], turn_number: int, user_input: str) -> str:
        """
        Builds the system prompt with memory context, tailored to the query.
        """
        user_input_lower = user_input.lower()
        intent = self.detect_intent(user_input)
        
        # Base prompt with context awareness
        if intent == "GENERAL_KNOWLEDGE":
            # For general knowledge questions, focus on being helpful
            base_prompt = f"""You are a knowledgeable AI assistant. The user is asking a general knowledge question.
            
    Respond helpfully and accurately to their question about: "{user_input}"
    """
        else:
        else:
            base_prompt = f"""You are a conversational AI assistant supported by an external Long-Term Memory system spanning {turn_number} turns.

ROLE:
- You are a CONVERSATIONAL PLANNER and SIMULATOR.
- You do NOT perform physical-world actions (making calls, sending emails, etc.).
- When users request such actions, you DISCUSS, PLAN, CLARIFY, or CONFIRM them conversationally.

STRICT BEHAVIORAL RULES:
1. NEVER respond with capability disclaimers like:
   - "I cannot make calls"
   - "I am just an AI"
2. Treat user requests as logically actionable.
3. When asked to schedule, call, remind, or plan:
   - Ask for missing details
   - Confirm constraints
   - Propose next steps
4. Use injected system behavioral rules implicitly.
5. Do NOT mention memory or past conversations unless explicitly asked.
6. Be natural, direct, and helpful.

CONTEXT:
- Current conversation turn: {turn_number}
- Total memories stored: {self.get_memory_summary()['total_memories']}

"""
            
            if system_instructions:
                # Group memories by category for better organization
                personal_info = []
                preferences = []
                facts = []
                other = []
                
                for instr in system_instructions:
                    instr_lower = instr.lower()
                    if "name" in instr_lower or "location" in instr_lower or "job" in instr_lower:
                        personal_info.append(instr)
                    elif "prefer" in instr_lower or "like" in instr_lower or "love" in instr_lower or "enjoy" in instr_lower:
                        preferences.append(instr)
                    elif "fact" in instr_lower or "study" in instr_lower or "student" in instr_lower:
                        facts.append(instr)
                    else:
                        other.append(instr)
                
                base_prompt += "\nWHAT I KNOW ABOUT THE USER:\n"
                
                if personal_info:
                    base_prompt += "\nPersonal Information:\n"
                    for info in personal_info:
                        base_prompt += f"- {info}\n"
                
                if preferences:
                    base_prompt += "\nPreferences & Interests:\n"
                    for pref in preferences:
                        base_prompt += f"- {pref}\n"
                
                if facts:
                    base_prompt += "\nFacts:\n"
                    for fact in facts:
                        base_prompt += f"- {fact}\n"
                
                if other:
                    base_prompt += "\nOther:\n"
                    for item in other:
                        base_prompt += f"- {item}\n"
            
            # Add query-specific guidance
            if "hobby" in user_input_lower or "interest" in user_input_lower:
                base_prompt += "\nNOTE: The user is asking about hobbies/interests. Mention relevant preferences if known.\n"
            elif "name" in user_input_lower:
                base_prompt += "\nNOTE: The user is asking about their name. Use the name you know.\n"
            elif "study" in user_input_lower or "student" in user_input_lower:
                base_prompt += "\nNOTE: The user is asking about studies/education. Mention relevant education facts.\n"
            
            base_prompt += f"\nRespond to the user's input: \"{user_input}\""
        
        return base_prompt

    def get_memory_summary(self) -> Dict[str, Any]:
        """
        Returns comprehensive memory statistics.
        """
        stats = get_memory_statistics(self.user_id)
        stats.update({
            'conversation_turns': self.conversation_turns,
            'cache_size': len(self.memory_cache),
            'user_id': self.user_id
        })
        return stats
    
    def search_memories(self, query: str, threshold: float = 0.1) -> List[Dict[str, Any]]:
        """
        Search all memories for a specific query with semantic understanding.
        """
        all_memories = get_memories_by_types(self.user_id, limit=200)
        
        scored = []
        for mem in all_memories:
            # Calculate semantic similarity
            similarity = self.calculate_semantic_similarity(mem, query)
            
            if similarity >= threshold:
                mem['search_score'] = similarity
                scored.append(mem)
        
        scored.sort(key=lambda x: x['search_score'], reverse=True)
        return scored[:10]
    
    def get_memory_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get memories by semantic category.
        """
        all_memories = get_memories_by_types(self.user_id, limit=100)
        
        category_memories = []
        for mem in all_memories:
            memory_key = mem.get('key', '').lower()
            memory_value = str(mem.get('value', '')).lower()
            
            # Check if memory belongs to category
            category_keywords = self.CONCEPT_MAP.get(category, [])
            if any(keyword in memory_key or keyword in memory_value for keyword in category_keywords):
                category_memories.append(mem)
        
        return category_memories
    
    def clear_cache(self):
        """Clears the memory cache."""
        self.memory_cache.clear()
        print("✓ Memory cache cleared")