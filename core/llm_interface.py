import os
import json
import requests
from typing import Optional

# Groq API configuration (can be swapped for OpenAI, Anthropic, etc.)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile" # High performance model for extraction

def _call_groq_api(messages: list, temperature: float = 0.0, json_mode: bool = False) -> str:
    """
    Internal helper to call Groq API.
    Args:
        messages (list): List of message dicts (role, content).
        temperature (float): Sampling temperature.
        json_mode (bool): Whether to enforce JSON output.
    Returns:
        str: content of the response.
    """
    # Move API key reading inside the function for runtime resolution
    groq_api_key = os.getenv("GROQ_API_KEY")
    
    if not groq_api_key:
        # Fallback for testing/demo if keys are missing
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
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"LLM API Call Error: {e}")
        return ""

def llm_extract_func(prompt: str) -> str:
    """
    Extracts memory from text.
    Must return strict JSON string.
    """
    messages = [
        {"role": "system", "content": "You are a precise memory extraction engine. Output ONLY JSON."},
        {"role": "user", "content": prompt}
    ]
    
    # We use low temperature for deterministic extraction
    # We use json_mode=True to ensure valid JSON structure
    return _call_groq_api(messages, temperature=0.0, json_mode=True)

def llm_response_func(system_prompt: str, user_input: str) -> str:
    """
    Generates a natural language response.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]
    
    # Higher temperature for natural conversation
    return _call_groq_api(messages, temperature=0.7)
