import os
import json
import requests
from typing import Optional, Dict, Any

# Groq API configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile"

def _call_groq_api(messages: list, temperature: float = 0.0, json_mode: bool = False) -> str:
    """Internal helper to call Groq API."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    
    if not groq_api_key:
        print("Error: GROQ_API_KEY environment variable not set.")
        return '{"error": "GROQ_API_KEY not found"}'

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"LLM API Call Error: {e}")
        return ""

def llm_extract_func(prompt: str) -> str:
    """
    Extracts memory from text using LLM.
    """
    messages = [
        {
            "role": "system", 
            "content": """You are a memory extraction system. Extract ONLY factual, long-term information.
            
            RULES:
            1. Extract personal facts: names, locations, jobs, education
            2. Extract preferences: likes, dislikes, habits
            3. Extract constraints: rules, limitations
            4. DO NOT extract: questions, temporary info, casual chat
            5. Output MUST be a JSON ARRAY
            6. Each item MUST have: type, key, value, confidence (0.0-1.0)
            7. If nothing to extract, return empty array: []
            
            Example outputs:
            Input: "My name is John and I live in New York"
            Output: [
              {"type": "fact", "key": "name", "value": "John", "confidence": 0.95},
              {"type": "fact", "key": "location", "value": "New York", "confidence": 0.9}
            ]
            
            Input: "What is my name?"
            Output: []
            
            Input: "I'm a software engineer"
            Output: [{"type": "fact", "key": "occupation", "value": "software engineer", "confidence": 0.9}]
            
            REMEMBER: Always return a JSON array, even if empty."""
        },
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = _call_groq_api(messages, temperature=0.1, json_mode=True)
        print(f"  Raw extraction response: {response[:200]}...")
        
        # Force array if single object (but not if empty array)
        response = response.strip()
        if response and response.startswith('{') and response.endswith('}'):
            # Check if it has valid memory data
            try:
                data = json.loads(response)
                if "type" in data and "key" in data and "value" in data:
                    print("  ⚠️ Wrapping single memory object in array")
                    response = f'[{response}]'
            except:
                pass
        
        return response
    except Exception as e:
        print(f"Extraction function error: {e}")
        return "[]"

def get_llm_response(system_prompt: str, user_input: str) -> str:
    """
    Generates a natural language response.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    return _call_groq_api(messages, temperature=0.7)