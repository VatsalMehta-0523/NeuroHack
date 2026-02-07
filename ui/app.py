import streamlit as st
import sys
import os
from typing import List, Dict, Any

# Ensure we can import from core
# Assumptions about project structure:
# root/
#   core/
#   ui/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from core.memory_controller import MemoryController
from core.llm_interface import llm_response_func, llm_extract_func
from core.db import init_db

# Load environment variables
load_dotenv()

# Page Config
st.set_page_config(
    page_title="Long-Form Memory AI",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = [] # List of {"role": str, "content": str, "debug_info": dict}
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 1
if "controller" not in st.session_state:
    # Initialize DB (idempotent)
    try:
        init_db()
    except Exception as e:
        st.error(f"Database Conneciton Failed: {e}")
        st.stop()
        
    # Initialize Controller with dependency injection
    st.session_state.controller = MemoryController(
        llm_response_func=llm_response_func,
        llm_extract_func=llm_extract_func
    )

# Header
st.title("🧠 Long-Form Memory AI")
st.caption(f"Turn: {st.session_state.turn_count} | Mode: Persistent | Model: Llama-3-70b")

# Sidebar Toggle
with st.sidebar:
    st.header("Debug Controls")
    show_debug = st.toggle("How was this response generated?", value=False)
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        st.session_state.turn_count = 1
        st.rerun()

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Display debug info if available and toggle is high
        if show_debug and "debug_info" in msg and msg["debug_info"]:
            info = msg["debug_info"]
            with st.expander("🔍 Memory Logic Breakdown"):
                st.subheader("1. Intent Detection")
                st.write(f"Detected Intent: `{info.get('intent', 'UNKNOWN')}`")
                
                st.subheader("2. Memory Retrieval")
                retrieved = info.get('retrieved_memories', [])
                if retrieved:
                    for m in retrieved:
                        score = m.get('retrieval_score', 0.0)
                        st.markdown(f"- **{m['type'].upper()}**: {m['value']} (Score: {score:.2f})")
                else:
                    st.write("No relevant memories retrieved.")
                    
                st.subheader("3. New Memories Extracted")
                extracted = info.get('extracted_memories', [])
                if extracted:
                    for m in extracted:
                        st.markdown(f"- **{m['type'].upper()}**: {m['value']}")
                else:
                    st.write("No new memories extracted.")
                    
                st.caption(f"Processing Time: {info.get('processing_time', 0):.4f}s")

# Chat Input
if prompt := st.chat_input("Say something..."):
    # User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process Turn
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Call Core Logic
                result = st.session_state.controller.process_turn(
                    user_input=prompt,
                    turn_number=st.session_state.turn_count
                )
                
                response_text = result["response"]
                
                # Update State
                st.session_state.turn_count += 1
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response_text,
                    "debug_info": result
                })
                
                st.markdown(response_text)
                
                # Immediate debug view for the response just generated
                if show_debug:
                    with st.expander("🔍 Memory Logic Breakdown (Current Turn)", expanded=True):
                         st.subheader("1. Intent Detection")
                         st.write(f"Detected Intent: `{result.get('intent', 'UNKNOWN')}`")
                         
                         st.subheader("2. Memory Retrieval")
                         retrieved = result.get('retrieved_memories', [])
                         if retrieved:
                             for m in retrieved:
                                 score = m.get('retrieval_score', 0.0)
                                 st.markdown(f"- **{m['type'].upper()}**: {m['value']} (Score: {score:.2f})")
                         else:
                             st.write("No relevant memories retrieved.")
                             
                         st.subheader("3. New Memories Extracted")
                         extracted = result.get('extracted_memories', [])
                         if extracted:
                             for m in extracted:
                                 st.markdown(f"- **{m['type'].upper()}**: {m['value']}")
                         else:
                             st.write("No new memories extracted.")
                             
                         st.caption(f"Processing Time: {result.get('processing_time', 0):.4f}s")
                         
            except Exception as e:
                st.error(f"Error processing turn: {e}")
