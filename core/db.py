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
    
    # First, check if memory exists
    cur.execute("""
        SELECT memory_id, confidence FROM memories 
        WHERE user_id = %s AND type = %s AND key = %s
    """, (user_id, memory_type, key))
    
    existing = cur.fetchone()
    
    try:
        if existing:
            existing_id, existing_confidence = existing
            # Only update if new confidence is significantly better
            if confidence >= existing_confidence * 0.8:
                cur.execute("""
                    UPDATE memories 
                    SET value = %s,
                        confidence = GREATEST(confidence, %s),
                        updated_at = NOW(),
                        decay_score = GREATEST(decay_score, 0.5)
                    WHERE memory_id = %s
                    RETURNING memory_id
                """, (value, confidence, existing_id))
                conn.commit()
                return existing_id
            else:
                # Don't update, return existing ID
                return existing_id
        else:
            # Insert new memory
            cur.execute("""
                INSERT INTO memories (
                    memory_id, user_id, type, key, value, 
                    confidence, source_turn, last_used_turn, decay_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING memory_id
            """, (
                memory_id, user_id, memory_type, key, value,
                confidence, source_turn, source_turn, 1.0
            ))
            conn.commit()
            return memory_id

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
        total_result = cur.fetchone()
        total = total_result['count'] if total_result else 0
        
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
        avg_conf_result = cur.fetchone()
        avg_conf = avg_conf_result['avg_confidence'] if avg_conf_result and avg_conf_result['avg_confidence'] else 0
        
        # Get recently used memories
        cur.execute("""
            SELECT COUNT(*) as recently_used 
            FROM memories 
            WHERE user_id = %s AND last_used_turn > 0
        """, (user_id,))
        recent_result = cur.fetchone()
        recent = recent_result['recently_used'] if recent_result else 0
        
        return {
            'total_memories': total,
            'type_distribution': {row['type']: row['count'] for row in type_dist},
            'average_confidence': round(float(avg_conf), 3),
            'recently_used': recent,
            'utilization_rate': round(recent / max(total, 1) * 100, 1)
        }
        
    except Exception as e:
        print(f"Error getting memory statistics: {e}")
        return {
            'total_memories': 0,
            'type_distribution': {},
            'average_confidence': 0.0,
            'recently_used': 0,
            'utilization_rate': 0.0
        }
    finally:
        cur.close()
        conn.close()

def record_memory_usage_batch(memory_ids: List[str], used_at_turn: int, relevance_scores: List[float]):
    """
    Records multiple memory usages in batch for efficiency.
    """
    if not memory_ids:
        return
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Prepare batch insert
        values = []
        for mem_id, score in zip(memory_ids, relevance_scores):
            values.append((mem_id, used_at_turn, score))
        
        query = """
        INSERT INTO memory_usage (memory_id, used_at_turn, relevance_score)
        VALUES (%s, %s, %s);
        """
        
        cur.executemany(query, values)
        conn.commit()
        print(f"✓ Recorded {len(memory_ids)} memory usages at turn {used_at_turn}")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error recording memory usage batch: {e}")
    finally:
        cur.close()
        conn.close()

def get_memory_usage_stats(user_id: str, days_back: int = 30) -> Dict[str, Any]:
    """
    Returns memory usage statistics.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Total usage count
        cur.execute("""
            SELECT COUNT(*) as total_usage_count
            FROM memory_usage mu
            JOIN memories m ON mu.memory_id = m.memory_id
            WHERE m.user_id = %s
            AND mu.created_at >= NOW() - INTERVAL '%s days'
        """, (user_id, days_back))
        total_usage_result = cur.fetchone()
        total_usage = total_usage_result['total_usage_count'] if total_usage_result else 0
        
        # Most used memories
        cur.execute("""
            SELECT m.key, m.value, m.type, COUNT(mu.id) as usage_count,
                   AVG(mu.relevance_score) as avg_relevance
            FROM memory_usage mu
            JOIN memories m ON mu.memory_id = m.memory_id
            WHERE m.user_id = %s
            GROUP BY m.memory_id, m.key, m.value, m.type
            ORDER BY usage_count DESC
            LIMIT 10
        """, (user_id,))
        top_memories = cur.fetchall()
        
        # Unused memories
        cur.execute("""
            SELECT COUNT(*) as unused_count
            FROM memories m
            WHERE m.user_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM memory_usage mu 
                WHERE mu.memory_id = m.memory_id
            )
        """, (user_id,))
        unused_result = cur.fetchone()
        unused_count = unused_result['unused_count'] if unused_result else 0
        
        # Get total memories for utilization rate
        total_memories = get_memory_statistics(user_id).get('total_memories', 1)
        
        return {
            'total_usage_count': total_usage,
            'top_memories': [dict(row) for row in top_memories],
            'unused_memories_count': unused_count,
            'utilization_rate': round(
                (1 - unused_count / max(total_memories, 1)) * 100, 
                1
            ) if total_usage > 0 else 0
        }
        
    except Exception as e:
        print(f"Error getting memory usage stats: {e}")
        return {
            'total_usage_count': 0,
            'top_memories': [],
            'unused_memories_count': 0,
            'utilization_rate': 0.0
        }
    finally:
        cur.close()
        conn.close()

def cleanup_old_memory_usage(days_to_keep: int = 90):
    """
    Cleans up old memory usage records to prevent database bloat.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        query = f"""
            DELETE FROM memory_usage 
            WHERE created_at < NOW() - INTERVAL '{days_to_keep} days'
        """
        cur.execute(query)
        
        deleted_count = cur.rowcount
        conn.commit()
        
        print(f"✓ Cleaned up {deleted_count} old memory usage records")
        return deleted_count
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error cleaning up memory usage: {e}")
        return 0
    finally:
        cur.close()
        conn.close()