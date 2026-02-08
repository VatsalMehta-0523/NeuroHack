import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Creates and returns a database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def init_db():
    """
    Initializes the database with required tables for long-form memory.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Drop old table if exists (for clean migration)
        cur.execute("DROP TABLE IF EXISTS memories;")
        
        # Create memories table with proper long-term memory schema
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                type VARCHAR(50) NOT NULL,
                key VARCHAR(255) NOT NULL,
                value TEXT NOT NULL,
                confidence FLOAT DEFAULT 1.0,
                source_turn INTEGER NOT NULL,
                last_used_turn INTEGER DEFAULT 0,
                decay_score FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, type, key)
            );
        """)
        
        # Create indexes for fast retrieval
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_id_type 
            ON memories(user_id, type);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_id_turn 
            ON memories(user_id, last_used_turn DESC);
        """)
        
        # Create memory_usage table for analytics
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_usage (
                id SERIAL PRIMARY KEY,
                memory_id VARCHAR(50) REFERENCES memories(memory_id),
                used_at_turn INTEGER NOT NULL,
                relevance_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✓ Long-term memory database initialized successfully")
        
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        raise

def query_db(sql: str, params=None):
    """Executes a query and returns results."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        results = cur.fetchall()
        cur.close()
        conn.close()
        return results
    except Exception as e:
        print(f"Query error: {e}")
        return []

def add_memory(
    user_id: str,
    memory_type: str,
    key: str,
    value: str,
    confidence: float,
    source_turn: int
) -> str:
    """
    Inserts a new memory or updates an existing one if the new confidence is higher.
    Returns the memory_id (new or existing).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    memory_id = f"mem_{uuid.uuid4().hex[:12]}"
    
    upsert_query = """
    INSERT INTO memories (memory_id, user_id, type, key, value, confidence, source_turn, last_used_turn, decay_score)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, type, key)
    DO UPDATE SET
        value = CASE 
            WHEN EXCLUDED.confidence >= memories.confidence 
            THEN EXCLUDED.value 
            ELSE memories.value 
        END,
        confidence = GREATEST(memories.confidence, EXCLUDED.confidence),
        source_turn = LEAST(memories.source_turn, EXCLUDED.source_turn),
        updated_at = NOW(),
        decay_score = GREATEST(memories.decay_score, 0.5) -- Preserve some decay if already decayed
    WHERE EXCLUDED.confidence >= memories.confidence * 0.8  -- Update if significantly better
    RETURNING memory_id;
    """
    
    try:
        # Initial last_used_turn is source_turn, decay_score starts at 1.0
        cur.execute(upsert_query, (
            memory_id,
            user_id,
            memory_type,
            key,
            value,
            confidence,
            source_turn,
            source_turn,  # last_used_turn initially = source_turn
            1.0          # decay_score starts fresh
        ))
        
        result = cur.fetchone()
        conn.commit()
        
        if result:
            return result[0]
        else:
            # If no row returned (conflict but not updated), fetch existing ID
            cur.execute("""
                SELECT memory_id FROM memories 
                WHERE user_id = %s AND type = %s AND key = %s
            """, (user_id, memory_type, key))
            existing = cur.fetchone()
            return existing[0] if existing else memory_id

    except Exception as e:
        conn.rollback()
        print(f"Error adding memory: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

def get_memories_by_types(
    user_id: str,
    memory_types: Optional[List[str]] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetches memories filtered by type for a specific user.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if memory_types:
        query = """
            SELECT * FROM memories 
            WHERE user_id = %s AND type = ANY(%s)
            ORDER BY last_used_turn DESC, confidence DESC
            LIMIT %s
        """
        params = (user_id, memory_types, limit)
    else:
        query = """
            SELECT * FROM memories 
            WHERE user_id = %s
            ORDER BY last_used_turn DESC, confidence DESC
            LIMIT %s
        """
        params = (user_id, limit)
    
    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching memories: {e}")
        return []
    finally:
        cur.close()
        conn.close()

def update_memory_decay(memory_id: str, new_decay: float, last_used_turn: int):
    """
    Updates the decay score and last used turn for a specific memory.
    Implements exponential decay based on usage.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
    UPDATE memories
    SET decay_score = %s, 
        last_used_turn = %s,
        updated_at = NOW()
    WHERE memory_id = %s;
    """
    
    try:
        cur.execute(query, (new_decay, last_used_turn, memory_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error updating memory decay: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

def record_memory_usage(memory_id: str, used_at_turn: int, relevance_score: float):
    """
    Records when a memory was used for analytics and decay calculation.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
    INSERT INTO memory_usage (memory_id, used_at_turn, relevance_score)
    VALUES (%s, %s, %s);
    """
    
    try:
        cur.execute(query, (memory_id, used_at_turn, relevance_score))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error recording memory usage: {e}")
    finally:
        cur.close()
        conn.close()

def get_memory_statistics(user_id: str) -> Dict[str, Any]:
    """
    Returns statistics about memory usage and effectiveness.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get total memories
        cur.execute("SELECT COUNT(*) as count FROM memories WHERE user_id = %s", (user_id,))
        total = cur.fetchone()['count']
        
        # Get memory type distribution
        cur.execute("""
            SELECT type, COUNT(*) as count 
            FROM memories 
            WHERE user_id = %s 
            GROUP BY type
        """, (user_id,))
        type_dist = cur.fetchall()
        
        # Get average confidence
        cur.execute("SELECT AVG(confidence) as avg_confidence FROM memories WHERE user_id = %s", (user_id,))
        avg_conf = cur.fetchone()['avg_confidence'] or 0
        
        # Get recently used memories
        cur.execute("""
            SELECT COUNT(*) as recently_used 
            FROM memories 
            WHERE user_id = %s AND last_used_turn > 0
        """, (user_id,))
        recent = cur.fetchone()['recently_used']
        
        return {
            'total_memories': total,
            'type_distribution': {row['type']: row['count'] for row in type_dist},
            'average_confidence': round(float(avg_conf), 3),
            'recently_used': recent,
            'utilization_rate': round(recent / max(total, 1) * 100, 1)
        }
        
    except Exception as e:
        print(f"Error getting memory statistics: {e}")
        return {}
    finally:
        cur.close()
        conn.close()