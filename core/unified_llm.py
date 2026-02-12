import os
import json
import google.generativeai as genai
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
import time

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"  # Fast model for single-call architecture

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"✓ Unified Gemini API configured with model: {MODEL_NAME}")
else:
    print("✗ Warning: GEMINI_API_KEY not found")

class UnifiedLLMOrchestrator:
    """
    Single API call orchestrator that handles:
    1. Memory extraction
    2. Memory retrieval analysis
    3. Response generation
    All in ONE API call.
    """
    
    def __init__(self):
        self.model = None
        if GEMINI_API_KEY:
            self.model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                generation_config={
                    "temperature": 0.3,  # Balanced temperature
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 4096,  # Enough for extraction + response
                }
            )
    
    def process_turn_unified(self, 
                           user_input: str,
                           existing_memories: List[Dict[str, Any]],
                           turn_number: int) -> Dict[str, Any]:
        """
        Processes a complete turn with ONE API call.
        Returns: {
            "extracted_memories": List[Dict],
            "response": str,
            "relevant_memories": List[Dict],
            "processing_time": float
        }
        """
        if not self.model:
            return self._fallback_response(user_input)
        
        start_time = time.time()
        
        # Prepare existing memories context
        memories_context = self._format_memories_for_prompt(existing_memories)
        
        # Create unified prompt
        prompt = self._create_unified_prompt(
            user_input=user_input,
            memories_context=memories_context,
            turn_number=turn_number
        )
        
        try:
            # SINGLE API CALL
            response = self.model.generate_content(prompt)
            
            if response and response.text:
                # Parse the unified response
                result = self._parse_unified_response(response.text)
                
                # Calculate processing time
                result["processing_time"] = time.time() - start_time
                result["api_calls"] = 1  # Track that we only made 1 call
                
                return result
            else:
                return self._fallback_response(user_input)
                
        except Exception as e:
            print(f"✗ Unified API call error: {e}")
            return self._fallback_response(user_input)
    
    def _create_unified_prompt(self, 
                              user_input: str,
                              memories_context: str,
                              turn_number: int) -> str:
        """
        Creates a single prompt that handles everything.
        """
        prompt = f"""# TURN {turn_number}: UNIFIED PROCESSING

## CONTEXT:
You are an AI assistant with memory capabilities. Process the following in ONE response.

## EXISTING MEMORIES:
{memories_context if memories_context else "No memories yet."}

## USER INPUT:
"{user_input}"

## YOUR TASKS (Do ALL in order):

1. **MEMORY EXTRACTION** (FIRST):
   - Extract any NEW long-term memories from the user input
   - Only extract: Personal facts, Preferences, Constraints, Commitments
   - Format as JSON array
   - Example: [{{"type": "fact", "key": "name", "value": "John", "confidence": 0.95}}]
   - If nothing to extract: []

2. **CONTEXT AWARENESS**:
   - Use provided memories naturally if relevant

3. **RESPONSE GENERATION** (THIRD AND FINAL):
   - Generate a natural, helpful response to the user
   - Incorporate relevant memories naturally (don't say "I remember")
   - Be conversational and helpful

## OUTPUT FORMAT:
Your ENTIRE response must follow this EXACT format:

===EXTRACTION===
[YOUR JSON ARRAY HERE OR []]
===ANALYSIS===
- Memory 1: [why relevant]
- Memory 2: [why relevant] (if any)
===RESPONSE===
[YOUR NATURAL RESPONSE HERE]
"""

        return prompt
    
    def _format_memories_for_prompt(self, memories: List[Dict[str, Any]]) -> str:
        """Format memories for the prompt."""
        if not memories:
            return ""
        
        formatted = []
        for i, mem in enumerate(memories[:10]):  # Limit to 10 most recent
            mem_type = mem.get('type', 'unknown')
            key = mem.get('key', 'unknown')
            value = mem.get('value', 'unknown')
            confidence = mem.get('confidence', 0.5)
            source_turn = mem.get('source_turn', 0)
            
            formatted.append(f"{i+1}. [{mem_type}] {key} = {value} (conf: {confidence}, turn: {source_turn})")
        
        return "\n".join(formatted)
    
    def _parse_unified_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the unified response into structured data."""
        result = {
            "extracted_memories": [],
            "relevant_memories": [],
            "response": "",
            "analysis": []
        }
        
        try:
            # Parse extraction section
            if "===EXTRACTION===" in response_text:
                parts = response_text.split("===EXTRACTION===")
                if len(parts) > 1:
                    extraction_part = parts[1].split("===ANALYSIS===")[0].strip()
                    try:
                        result["extracted_memories"] = json.loads(extraction_part)
                    except json.JSONDecodeError:
                        # Try to extract JSON if wrapped
                        import re
                        json_match = re.search(r'\[.*\]', extraction_part, re.DOTALL)
                        if json_match:
                            try:
                                result["extracted_memories"] = json.loads(json_match.group())
                            except:
                                pass
            
            # Parse analysis section
            if "===ANALYSIS===" in response_text:
                parts = response_text.split("===ANALYSIS===")
                if len(parts) > 1:
                    analysis_part = parts[1].split("===RESPONSE===")[0].strip()
                    result["analysis"] = [line.strip() for line in analysis_part.split("\n") if line.strip()]
            
            # Parse response section
            if "===RESPONSE===" in response_text:
                parts = response_text.split("===RESPONSE===")
                if len(parts) > 1:
                    result["response"] = parts[1].strip()
            
            # Fallback: if format parsing failed, use the whole text as response
            if not result["response"]:
                result["response"] = response_text.strip()
                
        except Exception as e:
            print(f"✗ Error parsing unified response: {e}")
            result["response"] = response_text.strip()
        
        return result
    
    def _fallback_response(self, user_input: str) -> Dict[str, Any]:
        """Fallback response when API fails."""
        return {
            "extracted_memories": [],
            "relevant_memories": [],
            "response": f"I'm having trouble processing that. You said: {user_input}",
            "analysis": [],
            "processing_time": 0.1,
            "api_calls": 0
        }


# Singleton instance for efficiency
_unified_orchestrator = None

def get_unified_orchestrator() -> UnifiedLLMOrchestrator:
    """Get or create singleton orchestrator."""
    global _unified_orchestrator
    if _unified_orchestrator is None:
        _unified_orchestrator = UnifiedLLMOrchestrator()
    return _unified_orchestrator