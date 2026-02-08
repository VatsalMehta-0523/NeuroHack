import streamlit as st
import sys
import os
from dotenv import load_dotenv
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# --------------------------------------------------
# Environment + Path Setup
# --------------------------------------------------
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------
# Core Imports
# --------------------------------------------------
from core.db import init_db
from core.llm_interface import get_llm_response, llm_extract_func
from core.memory_controller import LongTermMemoryController

# --------------------------------------------------
# Initialize Database
# --------------------------------------------------
@st.cache_resource
def initialize_system():
    """Initialize the memory system once per session."""
    try:
        init_db()
        return True
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        return False

# Initialize system
if not initialize_system():
    st.stop()

# --------------------------------------------------
# Streamlit Page Config
# --------------------------------------------------
st.set_page_config(
    page_title="NeuroHack - Long-Term Memory AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------
# Session State Initialization
# --------------------------------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = "demo_user_001"

if "turn_count" not in st.session_state:
    st.session_state.turn_count = 1

if "messages" not in st.session_state:
    st.session_state.messages = []

if "memory_controller" not in st.session_state:
    st.session_state.memory_controller = LongTermMemoryController(
        user_id=st.session_state.user_id,
        llm_response_func=get_llm_response,
        llm_extract_func=llm_extract_func  # Fixed: passing the correct function
    )

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

if "show_memory_details" not in st.session_state:
    st.session_state.show_memory_details = False

# --------------------------------------------------
# Header
# --------------------------------------------------
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🧠 NeuroHack - Long-Term Memory AI")
    st.markdown("**Retaining and recalling information across 1000+ conversation turns**")
with col2:
    st.metric("Current Turn", st.session_state.turn_count)
    st.metric("User ID", st.session_state.user_id[:10])

# --------------------------------------------------
# Sidebar - Memory Management & Analytics
# --------------------------------------------------
with st.sidebar:
    st.header("📊 Memory Analytics")
    
    # Get memory statistics
    stats = st.session_state.memory_controller.get_memory_summary()
    
    # Key metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Memories", stats.get('total_memories', 0))
    with col2:
        st.metric("Utilization", f"{stats.get('utilization_rate', 0)}%")
    
    # Memory type distribution
    if stats.get('type_distribution'):
        st.subheader("Memory Types")
        for mem_type, count in stats['type_distribution'].items():
            st.progress(min(count / max(stats['total_memories'], 1), 1.0), 
                       text=f"{mem_type}: {count}")
    
    # Controls
    st.divider()
    st.subheader("Controls")
    
    if st.button("🔄 Refresh All Data"):
        st.rerun()
    
    if st.button("📊 Show Memory Details"):
        st.session_state.show_memory_details = not st.session_state.show_memory_details
    
    if st.button("🧹 Clear Conversation"):
        st.session_state.messages = []
        st.session_state.conversation_history = []
        st.session_state.turn_count = 1
        st.success("Conversation cleared!")
    
    # Export option
    if st.button("💾 Export Memory Log"):
        import json
        export_data = {
            "user_id": st.session_state.user_id,
            "total_turns": st.session_state.turn_count,
            "memory_stats": stats,
            "conversation_summary": st.session_state.conversation_history[-10:] if st.session_state.conversation_history else []
        }
        st.download_button(
            label="Download JSON",
            data=json.dumps(export_data, indent=2),
            file_name=f"memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

# --------------------------------------------------
# Main Layout
# --------------------------------------------------
tab1, tab2, tab3 = st.tabs(["💬 Chat", "📚 Memory Bank", "📈 Analytics"])

with tab1:
    # Chat interface
    st.subheader("Conversation")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Show memory indicators for assistant messages
            if message["role"] == "assistant" and "metadata" in message:
                if message["metadata"].get("memories_used"):
                    with st.expander("🔍 Memories Used"):
                        for mem in message["metadata"]["memories_used"]:
                            st.caption(f"**{mem.get('key', 'Unknown')}**: {mem.get('value', '')[:100]}...")
    
    # Chat input
    if prompt := st.chat_input("Type your message here..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Process turn with memory
        with st.chat_message("assistant"):
            with st.spinner("Thinking with long-term memory..."):
                result = st.session_state.memory_controller.process_turn(
                    user_input=prompt,
                    turn_number=st.session_state.turn_count
                )
                
                # Display response
                st.write(result["response"])
                
                # Show memory insights
                if result.get("retrieved_memories"):
                    with st.expander(f"🎯 Used {len(result['retrieved_memories'])} memories"):
                        for i, mem in enumerate(result["retrieved_memories"], 1):
                            st.markdown(f"""
                            **{i}. {mem.get('key', 'Memory')}**  
                            *{mem.get('value', '')[:100]}...*  
                            Score: `{mem.get('retrieval_score', 0):.2f}` • Type: `{mem.get('type', 'unknown')}`
                            """)
                
                # Store metadata
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["response"],
                    "metadata": {
                        "memories_used": result.get("retrieved_memories", []),
                        "processing_time": result.get("processing_time", 0)
                    }
                })
        
        # Update conversation history
        st.session_state.conversation_history.append({
            "turn": st.session_state.turn_count,
            "user_input": prompt,
            "response": result["response"],
            "memories_extracted": len(result.get("extracted_memories", [])),
            "memories_retrieved": len(result.get("retrieved_memories", [])),
            "intent": result.get("intent", "unknown"),
            "processing_time": result.get("processing_time", 0)
        })
        
        # Increment turn counter
        st.session_state.turn_count += 1
        
        # Auto-refresh to show updates
        st.rerun()

# In the sidebar or Memory Bank tab, add category selection
with tab2:
    # Memory bank visualization
    st.subheader("Long-Term Memory Storage")
    
    # Category-based memory view
    st.subheader("Browse by Category")
    
    categories = [
        "Personal Information", "Education", "Hobbies & Interests",
        "Preferences", "Skills", "Goals"
    ]
    
    selected_category = st.selectbox("Select category:", ["All Memories"] + categories)
    
    if selected_category != "All Memories":
        # Map display categories to internal concepts
        category_map = {
            "Personal Information": ["name", "identity", "location", "job", "age"],
            "Education": ["education", "degree", "year", "subjects"],
            "Hobbies & Interests": ["hobbies", "sports", "games", "preferences"],
            "Preferences": ["preferences"],
            "Skills": ["skills", "languages"],
            "Goals": ["goals", "plans"]
        }
        
        # Get memories for selected category
        category_concepts = category_map.get(selected_category, [])
        all_memories = st.session_state.memory_controller.search_memories("", threshold=0)
        
        category_memories = []
        for mem in all_memories:
            memory_key = mem.get('key', '').lower()
            for concept in category_concepts:
                if concept in memory_key:
                    category_memories.append(mem)
                    break
        
        if category_memories:
            st.write(f"Found {len(category_memories)} memories in {selected_category}:")
            for mem in category_memories:
                with st.expander(f"📍 {mem.get('key', 'Unknown')}"):
                    st.write(f"**Value:** {mem.get('value', '')}")
                    st.write(f"**Type:** {mem.get('type', 'unknown')}")
                    st.write(f"**Confidence:** {mem.get('confidence', 0):.2f}")
                    st.write(f"**Source Turn:** {mem.get('source_turn', 'N/A')}")
                    st.write(f"**Last Used:** {mem.get('last_used_turn', 'Never')}")
        else:
            st.info(f"No memories found in {selected_category} category.")
            
with tab3:
    # Analytics dashboard
    st.subheader("Memory System Analytics")
    
    if st.session_state.conversation_history:
        # Create analytics dataframe
        history_df = pd.DataFrame(st.session_state.conversation_history)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            avg_memories = history_df['memories_retrieved'].mean()
            st.metric("Avg. Memories per Turn", f"{avg_memories:.1f}")
        with col2:
            avg_time = history_df['processing_time'].mean()
            st.metric("Avg. Response Time", f"{avg_time:.2f}s")
        with col3:
            total_turns = len(history_df)
            st.metric("Total Turns Processed", total_turns)
        
        # Visualization
        st.subheader("Memory Usage Over Time")
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=history_df['turn'],
            y=history_df['memories_retrieved'],
            mode='lines+markers',
            name='Memories Retrieved',
            line=dict(color='#FF6B6B', width=3)
        ))
        
        fig.add_trace(go.Scatter(
            x=history_df['turn'],
            y=history_df['memories_extracted'],
            mode='lines+markers',
            name='Memories Extracted',
            line=dict(color='#4ECDC4', width=3)
        ))
        
        fig.update_layout(
            title="Memory Activity Across Turns",
            xaxis_title="Turn Number",
            yaxis_title="Number of Memories",
            hovermode='x unified',
            template="plotly_white",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Intent distribution
        st.subheader("Intent Distribution")
        intent_counts = history_df['intent'].value_counts()
        
        fig2 = go.Figure(data=[go.Pie(
            labels=intent_counts.index,
            values=intent_counts.values,
            hole=.3,
            marker_colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        )])
        
        fig2.update_layout(
            title="User Intent Distribution",
            height=400
        )
        
        st.plotly_chart(fig2, use_container_width=True)
        
        # Performance metrics table
        st.subheader("Performance Metrics")
        metrics_df = history_df.describe().round(3)
        st.dataframe(metrics_df, width='stretch')
        
    else:
        st.info("Start a conversation to see analytics here.")

# --------------------------------------------------
# Footer
# --------------------------------------------------
st.divider()
st.caption("""
**NeuroHack Long-Term Memory System** • Built for 1000+ turn conversations  
*Features:* Memory extraction • Intelligent retrieval • Decay mechanisms • Real-time analytics
""")