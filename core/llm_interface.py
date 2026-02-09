import os
import json
import google.generativeai as genai
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"  # Options: gemini-1.5-pro, gemini-1.5-flash

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"✓ Gemini API configured with model: {MODEL_NAME}")
else:
    print("✗ Warning: GEMINI_API_KEY not found in environment variables")

def _call_gemini_api(prompt: str, system_instruction: str = "", temperature: float = 0.7, json_mode: bool = False) -> str:
    """
    Internal helper to call Gemini API.
    Args:
        prompt (str): User prompt
        system_instruction (str): System instruction
        temperature (float): Creativity temperature (0.0-1.0)
        json_mode (bool): Whether to enforce JSON output
    Returns:
        str: Content of the response
    """
    if not GEMINI_API_KEY:
        return '{"error": "GEMINI_API_KEY not found"}'
    
    try:
        # Configure generation parameters
        generation_config = {
            "temperature": 0.1 if json_mode else temperature,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        
        # Safety settings (adjust as needed)
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
        
        # Enhance system instruction for JSON mode
        if json_mode:
            enhanced_system_instruction = system_instruction + "\n\nCRITICAL: Output MUST be valid JSON only. No explanations, no additional text."
        else:
            enhanced_system_instruction = system_instruction
        
        # Create the model
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=enhanced_system_instruction
        )
        
        # Generate response
        response = model.generate_content(prompt)
        
        # Check for blocked content
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"⚠️ Content blocked: {response.prompt_feedback.block_reason}")
            return ""
        
        # Extract text from response
        if response and response.text:
            text = response.text.strip()
            
            # For JSON responses, clean up common formatting issues
            if json_mode:
                # Remove markdown code blocks
                text = text.replace("```json", "").replace("```", "").strip()
                
                # Sometimes Gemini adds explanations, extract just the JSON
                try:
                    # Find the first { or [ and last } or ]
                    if "{" in text and "}" in text:
                        start = text.find("{")
                        end = text.rfind("}") + 1
                        text = text[start:end]
                    elif "[" in text and "]" in text:
                        start = text.find("[")
                        end = text.rfind("]") + 1
                        text = text[start:end]
                except:
                    pass  # Keep as-is if parsing fails
            
            return text
        else:
            print(f"⚠️ Gemini returned empty response")
            return ""
            
    except Exception as e:
        print(f"✗ Gemini API Error: {e}")
        import traceback
        traceback.print_exc()
        return ""

def llm_extract_func(prompt: str) -> str:
    """
    Extracts memory from text using Gemini.
    Must return strict JSON string.
    """
    system_instruction = """You are a precise memory extraction system.

RULES:
1. Extract ONLY long-term information worth remembering:
   - Personal facts (name, location, job, education)
   - Preferences (likes, dislikes, hobbies)
   - Constraints (rules, limitations)
   - Commitments (promises, agreements)
   - Instructions (how to behave)

2. IGNORE:
   - Questions
   - Casual conversation
   - Temporary information
   - Context-dependent statements

3. OUTPUT FORMAT: JSON array
   Example for "my name is John":
   [
     {
       "type": "fact",
       "key": "name", 
       "value": "John",
       "confidence": 0.95
     }
   ]

4. If nothing to extract, return: []

Output only JSON, no other text."""
    
    return _call_gemini_api(prompt, system_instruction, temperature=0.1, json_mode=True)

def get_llm_response(system_prompt: str, user_input: str) -> str:
    """
    Generates a natural language response using Gemini.
    """
    return _call_gemini_api(user_input, system_prompt, temperature=0.7, json_mode=False)

# For testing
if __name__ == "__main__":
    # Test the functions
    print("Testing Gemini integration...")
    
    # Test extraction
    test_prompt = "my name is John and I live in New York"
    print(f"\nTest extraction for: '{test_prompt}'")
    result = llm_extract_func(test_prompt)
    print(f"Result: {result}")
    
    # Test chat
    print("\nTest chat response...")
    response = get_llm_response("You are a helpful assistant.", "Hello, how are you?")
    print(f"Response: {response[:100]}...")