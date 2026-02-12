import streamlit as st
import sys
import os
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
import time

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory_controller import OptimizedMemoryController
from core.db import get_db_connection
import base64
import tempfile
from gtts import gTTS
import streamlit.components.v1 as components

import uuid

# Helper: Text to Speech
def text_to_speech_html(text):
    """Generates HTML for an audio player with the spoken text."""
    try:
        # Create a unique temporary file path
        # Windows requires closing the file before reading it again
        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f"speech_{uuid.uuid4()}.mp3")
        
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(temp_filename)
        
        with open(temp_filename, "rb") as f:
            audio_bytes = f.read()
            
        # Clean up safely
        try:
            os.remove(temp_filename)
        except Exception:
            pass # Best effort cleanup
            
        b64 = base64.b64encode(audio_bytes).decode()
        md = f"""
            <audio controls autoplay>
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
            """
        return md
    except Exception as e:
        return f"Error generating audio: {e}"

# Helper: Voice Input Component
def voice_input_component():
    """Renders a microphone button above the chat input."""
    # JavaScript to directly inject text into Streamlit's chat input
    js_code = """
    <script>
    function startListening() {
        if (!('webkitSpeechRecognition' in window)) {
            alert("Web Speech API not supported in this browser.");
            return;
        }
        
        var recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = "en-US";
        
        var btn = document.getElementById("mic-btn");
        var originalText = btn.innerHTML;
        btn.innerHTML = "🔴";
        btn.style.backgroundColor = "#ff4b4b";
        btn.style.color = "white";
        // Pulse animation
        btn.classList.add("pulse");
        
        recognition.onresult = function(event) {
            var transcript = event.results[0][0].transcript;
            
            // Find the Streamlit chat input textarea
            var chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
            
            if (chatInput) {
                // React needs the native value setter to trigger change events
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                nativeInputValueSetter.call(chatInput, transcript);
                
                // Dispatch input event for React to pick up the change
                var event = new Event('input', { bubbles: true});
                chatInput.dispatchEvent(event);
                
                // Focus the input
                chatInput.focus();
            } else {
                console.error("Chat input not found. Copying to clipboard as fallback.");
                navigator.clipboard.writeText(transcript);
                alert("Speech recognized: " + transcript + "\\n(Copied to clipboard - paste it in the chat!)");
            }
            
            resetButton(btn, originalText);
        };
        
        recognition.onerror = function(event) {
            console.error(event.error);
            btn.innerHTML = "⚠️";
            setTimeout(function() { 
                resetButton(btn, originalText);
            }, 2000);
        };
        
        recognition.onend = function() {
            if (btn.innerHTML.includes("🔴")) {
                 resetButton(btn, originalText);
            }
        };
        
        recognition.start();
    }
    
    function resetButton(btn, text) {
        btn.innerHTML = text;
        btn.style.backgroundColor = "#ffffff";
        btn.style.color = "#31333F";
        btn.classList.remove("pulse");
    }
    </script>
    <style>
    @keyframes pulse {
        0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 75, 75, 0.7); }
        70% { transform: scale(1.1); box-shadow: 0 0 0 10px rgba(255, 75, 75, 0); }
        100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 75, 75, 0); }
    }
    .pulse {
        animation: pulse 1.5s infinite;
    }
    </style>
    <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
        <button id="mic-btn" onclick="startListening()" style="
            background-color: #ffffff; 
            border: 1px solid #e0e0e0; 
            border-radius: 50%; 
            width: 50px;
            height: 50px;
            cursor: pointer;
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: all 0.2s;">
            🎤
        </button>
    </div>
    """
    components.html(js_code, height=60)


# Detect database type
@st.cache_resource
def detect_db_type():
    """Detect whether we're using SQLite or PostgreSQL."""
    try:
        conn = get_db_connection()
        # Check if it's a PostgreSQL connection
        if hasattr(conn, 'get_dsn_parameters'):
            db_type = 'postgresql'
        else:
            db_type = 'sqlite'
        conn.close()
        return db_type
    except Exception:
        return 'sqlite'

DB_TYPE = detect_db_type()
PARAM_PLACEHOLDER = '%s' if DB_TYPE == 'postgresql' else '?'

# Check Database Connection
@st.cache_resource
def check_database():
    """Verify database connection."""
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception as e:
        st.error(f"❌ Database Connection Failed: {e}")
        st.info("Please run 'python init_db.py' first to initialize the database")
        return False

if not check_database():
    st.stop()

# Streamlit config
st.set_page_config(
    page_title="NeuroHack - Memory AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State Initialization
if "user_id" not in st.session_state:
    st.session_state.user_id = "demo_user_001"

if "turn_count" not in st.session_state:
    st.session_state.turn_count = 1

if "messages" not in st.session_state:
    st.session_state.messages = []

if "memory_controller" not in st.session_state:
    try:
        st.session_state.memory_controller = OptimizedMemoryController(
            user_id=st.session_state.user_id
        )
    except Exception as e:
        st.error(f"Failed to initialize memory controller: {e}")
        st.stop()

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

if "show_debug" not in st.session_state:
    st.session_state.show_debug = False

# Header
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.title("🧠 NeuroHack - Memory AI")
    st.markdown("**Conversational AI with long-term memory**")
with col2:
    st.metric("Current Turn", st.session_state.turn_count)
with col3:
    st.metric("User ID", st.session_state.user_id[:8])

# Sidebar
with st.sidebar:
    st.header("📊 Memory Stats")
    
    try:
        summary = st.session_state.memory_controller.get_memory_summary()
        st.metric("Total Memories", summary.get('total_memories', 0))
        st.metric("Conversations", summary.get('conversation_turns', 0))
        
        # Show architecture info
        architecture = summary.get('architecture', 'unknown')
        if architecture == 'single-call-optimized':
            st.success("✨ Optimized Mode Active")
    except Exception as e:
        st.warning(f"Could not load stats: {e}")
    
    st.divider()
    
    st.header("Debug Controls")
    st.session_state.show_debug = st.toggle(
        "Show Memory Logic Breakdown", 
        value=st.session_state.show_debug
    )
    
    st.divider()
    
    if st.button("🔄 Clear & Restart"):
        st.session_state.messages = []
        st.session_state.conversation_history = []
        st.session_state.turn_count = 1
        st.success("Restarted!")
        st.rerun()

# Main Tabs
tab1, tab2, tab3 = st.tabs(["💬 Chat", "🗂️ Memory Explorer", "📈 Analytics"])

# ===== TAB 1: Chat =====
with tab1:
    st.subheader("Chat Interface")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Show debug info if enabled
            if st.session_state.show_debug and message["role"] == "assistant" and "metadata" in message:
                meta = message["metadata"]
                
                with st.expander("🔍 Memory Logic Breakdown"):
                    # Intent Detection
                    st.subheader("1. Intent Detection")
                    intent = meta.get("intent", "UNKNOWN")
                    st.write(f"Detected Intent: `{intent}`")
                    
                    # Memory Retrieval
                    st.subheader("2. Memory Retrieval")
                    retrieved = meta.get("retrieved_memories", [])
                    if retrieved:
                        for m in retrieved:
                            score = m.get('retrieval_score', m.get('score', 0.0))
                            mem_type = m.get('type', m.get('key', 'unknown'))
                            mem_value = m.get('value', 'N/A')
                            st.markdown(f"- **{mem_type.upper()}**: {mem_value} (Score: {score:.2f})")
                    else:
                        st.write("No relevant memories retrieved.")
                    
                    # New Memories Extracted
                    st.subheader("3. New Memories Extracted")
                    extracted = meta.get("extracted_memories", [])
                    if extracted:
                        for m in extracted:
                            mem_type = m.get('type', m.get('key', 'unknown'))
                            mem_value = m.get('value', 'N/A')
                            st.markdown(f"- **{mem_type.upper()}**: {mem_value}")
                    else:
                        st.write("No new memories extracted.")
                    
                    # Processing Time
                    processing_time = meta.get("processing_time", 0)
                    api_time = meta.get("api_time", 0)
                    api_calls = meta.get("api_calls", 1)
                    
                    st.caption(f"Processing Time: {processing_time:.4f}s | API Time: {api_time:.4f}s | API Calls: {api_calls}")
            
            # Voice Output Trigger
            if message["role"] == "assistant":
                col_audio, col_space = st.columns([1, 4])
                with col_audio:
                    if st.button("🔊 Play Audio", key=f"tts_{message.get('metadata', {}).get('processing_time', 0)}_{st.session_state.turn_count}"):
                        st.markdown(text_to_speech_html(message["content"]), unsafe_allow_html=True)
    
    
    # Chat input
    # Voice Input Component (Placed above chat input)
    voice_input_component()
    
    if prompt := st.chat_input("Type your message..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Process turn
        with st.chat_message("assistant"):
            with st.spinner("Processing..."):
                try:
                    result = st.session_state.memory_controller.process_turn_optimized(
                        user_input=prompt,
                        turn_number=st.session_state.turn_count
                    )
                    
                    # Display response
                    response_text = result.get("response", "I couldn't process that.")
                    st.write(response_text)
                    
                    # Store assistant message with metadata
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "metadata": {
                            "intent": result.get("intent", "UNKNOWN"),
                            "extracted_memories": result.get("extracted_memories", []),
                            "retrieved_memories": result.get("retrieved_memories", []),
                            "relevant_memories_analysis": result.get("relevant_memories_analysis", []),
                            "analysis": result.get("analysis", []),
                            "processing_time": result.get("processing_time", 0),
                            "api_time": result.get("api_time", 0),
                            "api_calls": result.get("api_calls", 1)
                        }
                    })
                    
                    # Show debug info immediately for current turn if enabled
                    if st.session_state.show_debug:
                        with st.expander("🔍 Memory Logic Breakdown (Current Turn)", expanded=True):
                            # Intent Detection
                            st.subheader("1. Intent Detection")
                            intent = result.get("intent", "UNKNOWN")
                            st.write(f"Detected Intent: `{intent}`")
                            
                            # Memory Retrieval
                            st.subheader("2. Memory Retrieval")
                            retrieved = result.get("retrieved_memories", [])
                            if retrieved:
                                for m in retrieved:
                                    score = m.get('retrieval_score', m.get('score', 0.0))
                                    mem_type = m.get('type', m.get('key', 'unknown'))
                                    mem_value = m.get('value', 'N/A')
                                    st.markdown(f"- **{mem_type.upper()}**: {mem_value} (Score: {score:.2f})")
                            else:
                                st.write("No relevant memories retrieved.")
                            
                            # New Memories Extracted
                            st.subheader("3. New Memories Extracted")
                            extracted = result.get("extracted_memories", [])
                            if extracted:
                                for m in extracted:
                                    mem_type = m.get('type', m.get('key', 'unknown'))
                                    mem_value = m.get('value', 'N/A')
                                    st.markdown(f"- **{mem_type.upper()}**: {mem_value}")
                            else:
                                st.write("No new memories extracted.")
                            
                            # Processing Time and Performance
                            processing_time = result.get("processing_time", 0)
                            api_time = result.get("api_time", 0)
                            api_calls = result.get("api_calls", 1)
                            overhead = processing_time - api_time
                            
                            st.caption(f"Total: {processing_time:.4f}s | API: {api_time:.4f}s | Overhead: {overhead:.4f}s | Calls: {api_calls}")
                    
                    # Update conversation history
                    st.session_state.conversation_history.append({
                        "turn": st.session_state.turn_count,
                        "user_input": prompt,
                        "response": response_text
                    })
                    
                except Exception as e:
                    st.error(f"Error processing message: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Sorry, I encountered an error: {str(e)}",
                        "metadata": {}
                    })
        
        # Increment turn counter
        st.session_state.turn_count += 1
        
        # Auto-refresh
        st.rerun()

# ===== TAB 2: Memory Explorer =====
with tab2:
    st.subheader("🗂️ Stored Memories")
    
    try:
        # Fetch all memories from database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
            SELECT key, value, type, created_at, updated_at 
            FROM memories 
            WHERE user_id = {PARAM_PLACEHOLDER}
            ORDER BY updated_at DESC
        """
        cursor.execute(query, (st.session_state.user_id,))
        
        memories = cursor.fetchall()
        conn.close()
        
        if memories:
            # Create DataFrame
            df = pd.DataFrame(memories, columns=['Key', 'Value', 'Type', 'Created', 'Updated'])
            
            # Display metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Memories", len(df))
            with col2:
                memory_types = df['Type'].value_counts()
                most_common = memory_types.index[0] if len(memory_types) > 0 else "N/A"
                st.metric("Most Common Type", most_common)
            with col3:
                st.metric("Memory Types", df['Type'].nunique())
            
            st.divider()
            
            # Filter by type
            all_types = df['Type'].unique().tolist()
            memory_type_filter = st.multiselect(
                "Filter by Memory Type",
                options=all_types,
                default=all_types
            )
            
            filtered_df = df[df['Type'].isin(memory_type_filter)] if memory_type_filter else df
            
            # Display table
            st.dataframe(
                filtered_df,
                width="stretch",
                hide_index=True
            )
            
            # Individual memory viewer
            if not filtered_df.empty:
                st.subheader("Memory Details")
                selected_key = st.selectbox("Select a memory to view details", filtered_df['Key'].tolist())
                
                if selected_key:
                    memory_row = filtered_df[filtered_df['Key'] == selected_key].iloc[0]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Key:** {memory_row['Key']}")
                        st.write(f"**Type:** {memory_row['Type']}")
                    with col2:
                        st.write(f"**Created:** {memory_row['Created']}")
                        st.write(f"**Updated:** {memory_row['Updated']}")
                    
                    st.write(f"**Value:**")
                    st.info(memory_row['Value'])
        else:
            st.info("No memories stored yet. Start chatting to build your memory!")
            
    except Exception as e:
        st.error(f"Error loading memories: {e}")
        import traceback
        st.code(traceback.format_exc())

# ===== TAB 3: Analytics =====
with tab3:
    st.subheader("📈 Memory Analytics")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Memory count over time
        query = f"""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM memories
            WHERE user_id = {PARAM_PLACEHOLDER}
            GROUP BY DATE(created_at)
            ORDER BY date
        """
        cursor.execute(query, (st.session_state.user_id,))
        
        daily_memories = cursor.fetchall()
        
        if daily_memories:
            df_daily = pd.DataFrame(daily_memories, columns=['Date', 'Count'])
            st.subheader("Memory Creation Over Time")
            st.line_chart(df_daily.set_index('Date'))
        else:
            st.info("No data available for time-based analysis yet.")
        
        st.divider()
        
        # Memory type distribution
        query = f"""
            SELECT type, COUNT(*) as count
            FROM memories
            WHERE user_id = {PARAM_PLACEHOLDER}
            GROUP BY type
            ORDER BY count DESC
        """
        cursor.execute(query, (st.session_state.user_id,))
        
        type_dist = cursor.fetchall()
        
        if type_dist:
            df_types = pd.DataFrame(type_dist, columns=['Memory Type', 'Count'])
            st.subheader("Memory Type Distribution")
            st.bar_chart(df_types.set_index('Memory Type'))
        else:
            st.info("No memory type distribution data available yet.")
        
        st.divider()
        
        # Conversation statistics
        st.subheader("Conversation Statistics")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Turns", st.session_state.turn_count - 1)
            st.metric("Messages Sent", len([m for m in st.session_state.messages if m["role"] == "user"]))
        with col2:
            st.metric("Responses Received", len([m for m in st.session_state.messages if m["role"] == "assistant"]))
            
            # Average processing time
            processing_times = [
                m.get("metadata", {}).get("processing_time", 0) 
                for m in st.session_state.messages 
                if m["role"] == "assistant" and "metadata" in m
            ]
            avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
            st.metric("Avg Processing Time", f"{avg_time:.3f}s")
        
        # Performance metrics (if available)
        st.divider()
        st.subheader("Performance Metrics")
        
        api_calls = [
            m.get("metadata", {}).get("api_calls", 0)
            for m in st.session_state.messages
            if m["role"] == "assistant" and "metadata" in m
        ]
        
        if api_calls:
            col1, col2, col3 = st.columns(3)
            with col1:
                total_calls = sum(api_calls)
                st.metric("Total API Calls", total_calls)
            with col2:
                avg_calls = sum(api_calls) / len(api_calls) if api_calls else 0
                st.metric("Avg Calls/Turn", f"{avg_calls:.1f}")
            with col3:
                if avg_calls > 0:
                    efficiency = f"{(1/avg_calls)*100:.0f}%"
                    st.metric("Efficiency", efficiency)
        
        conn.close()
        
    except Exception as e:
        st.error(f"Error loading analytics: {e}")
        import traceback
        st.code(traceback.format_exc())