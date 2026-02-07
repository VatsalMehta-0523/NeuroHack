import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional, Any
import uuid

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    # Move environment variable reading inside the function
    # to avoid import-time errors before load_dotenv() runs.
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set. Ensure .env is loaded.")
        
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise e

def init_db():
    """Initializes the database schema if it does not exist."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create the memories table
    create_table_query = """
    CREATE TABLE IF NOT EXISTS memories (
        memory_id TEXT PRIMARY KEY,
        type TEXT NOT NULL CHECK (type IN ('preference', 'constraint', 'commitment', 'instruction', 'fact')),
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        source_turn INTEGER NOT NULL,
        last_used_turn INTEGER NOT NULL DEFAULT 0,
        decay_score FLOAT NOT NULL CHECK (decay_score >= 0 AND decay_score <= 1),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (type, key)
    );
    """
    
    try:
        cur.execute(create_table_query)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def add_memory(
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
    
    new_memory_id = f"mem_{uuid.uuid4().hex[:8]}"
    
    upsert_query = """
    INSERT INTO memories (memory_id, type, key, value, confidence, source_turn, last_used_turn, decay_score)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (type, key)
    DO UPDATE SET
        value = EXCLUDED.value,
        confidence = EXCLUDED.confidence,
        source_turn = EXCLUDED.source_turn,
        last_used_turn = EXCLUDED.last_used_turn,
        decay_score = EXCLUDED.decay_score
    WHERE EXCLUDED.confidence >= memories.confidence
    RETURNING memory_id;
    """
    
    try:
        # Initial decay score is 1.0 (fresh)
        cur.execute(upsert_query, (
            new_memory_id,
            memory_type,
            key,
            value,
            confidence,
            source_turn,
            source_turn, 
            1.0          
        ))
        
        result = cur.fetchone()
        conn.commit()
        
        if result:
            return result[0]
        else:
            # If no row returned, fetch existing ID
            cur.execute("SELECT memory_id FROM memories WHERE type = %s AND key = %s", (memory_type, key))
            existing_id = cur.fetchone()[0]
            return existing_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_memories(
    memory_types: Optional[List[str]] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetches memories, optionally filtered by type.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM memories"
    params = []
    
    if memory_types:
        query += " WHERE type = ANY(%s)"
        params.append(memory_types)
        
    query += " ORDER BY last_used_turn DESC LIMIT %s"
    params.append(limit)
    
    try:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        raise e
    finally:
        cur.close()
        conn.close()

def update_memory_decay(memory_id: str, new_decay: float, last_used_turn: int):
    """
    Updates the decay score and last used turn for a specific memory.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
    UPDATE memories
    SET decay_score = %s, last_used_turn = %s
    WHERE memory_id = %s;
    """
    
    try:
        cur.execute(query, (new_decay, last_used_turn, memory_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def delete_memory(memory_id: str):
    """Deletes a memory by ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "DELETE FROM memories WHERE memory_id = %s"
    
    try:
        cur.execute(query, (memory_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
