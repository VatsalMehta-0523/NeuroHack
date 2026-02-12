"""
Database Initialization Script
Run this ONCE to set up the database schema.

Usage:
    python init_db.py

This script:
1. Creates all required tables
2. Sets up indexes for performance
3. Initializes constraints
4. Does NOT drop existing data
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Creates and returns a database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"✗ Database connection error: {e}")
        raise

def check_database_exists():
    """Check if database is accessible."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        cur.close()
        conn.close()
        print(f"✓ Database connected successfully")
        print(f"  PostgreSQL version: {version[0][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Cannot connect to database: {e}")
        return False

def create_tables():
    """Create all required tables."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n Creating tables...")
        
        # Create memories table
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
        print("  ✓ Created 'memories' table")
        
        # Create memory_usage table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_usage (
                id SERIAL PRIMARY KEY,
                memory_id VARCHAR(50) REFERENCES memories(memory_id) ON DELETE CASCADE,
                used_at_turn INTEGER NOT NULL,
                relevance_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("  ✓ Created 'memory_usage' table")
        
        conn.commit()
        print("✓ All tables created successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error creating tables: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def create_indexes():
    """Create indexes for performance optimization."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n🔍 Creating indexes...")
        
        # Index on user_id and type for fast filtering
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_id_type 
            ON memories(user_id, type);
        """)
        print("  ✓ Created index: idx_memories_user_id_type")
        
        # Index on user_id and last_used_turn for recency queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_id_turn 
            ON memories(user_id, last_used_turn DESC);
        """)
        print("  ✓ Created index: idx_memories_user_id_turn")
        
        # Index on memory_usage for faster joins
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_usage_memory_id 
            ON memory_usage(memory_id);
        """)
        print("  ✓ Created index: idx_memory_usage_memory_id")
        
        # Index on created_at for cleanup operations
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_usage_created_at 
            ON memory_usage(created_at);
        """)
        print("  ✓ Created index: idx_memory_usage_created_at")
        
        conn.commit()
        print("✓ All indexes created successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error creating indexes: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def verify_setup():
    """Verify that all tables and indexes exist."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("\n Verifying setup...")
        
        # Check tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('memories', 'memory_usage')
            ORDER BY table_name;
        """)
        tables = cur.fetchall()
        
        print(f"  Tables found: {len(tables)}/2")
        for table in tables:
            print(f"    ✓ {table['table_name']}")
        
        # Check indexes
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename IN ('memories', 'memory_usage')
            ORDER BY indexname;
        """)
        indexes = cur.fetchall()
        
        print(f"  Indexes found: {len(indexes)}")
        for index in indexes:
            print(f"    ✓ {index['indexname']}")
        
        # Check constraints
        cur.execute("""
            SELECT constraint_name, constraint_type 
            FROM information_schema.table_constraints 
            WHERE table_name IN ('memories', 'memory_usage')
            AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
            ORDER BY constraint_name;
        """)
        constraints = cur.fetchall()
        
        print(f"  Constraints found: {len(constraints)}")
        for constraint in constraints:
            print(f"    ✓ {constraint['constraint_name']} ({constraint['constraint_type']})")
        
        print("\n✓ Database setup verified successfully!")
        
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def get_table_stats():
    """Display current database statistics."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("\n Current Database Statistics:")
        
        # Count memories
        cur.execute("SELECT COUNT(*) as count FROM memories;")
        result = cur.fetchone()
        mem_count = result['count'] if result else 0
        print(f"  Total memories: {mem_count}")
        
        # Count memory usage records
        cur.execute("SELECT COUNT(*) as count FROM memory_usage;")
        result = cur.fetchone()
        usage_count = result['count'] if result else 0
        print(f"  Total usage records: {usage_count}")
        
        # Count unique users
        cur.execute("SELECT COUNT(DISTINCT user_id) as count FROM memories;")
        result = cur.fetchone()
        user_count = result['count'] if result else 0
        print(f"  Unique users: {user_count}")
        
        # Memory types distribution
        cur.execute("""
            SELECT type, COUNT(*) as count 
            FROM memories 
            GROUP BY type 
            ORDER BY count DESC;
        """)
        types = cur.fetchall()
        
        if types:
            print(f"  Memory types:")
            for type_row in types:
                print(f"    - {type_row['type']}: {type_row['count']}")
        
    except Exception as e:
        print(f"⚠️  Could not retrieve statistics: {e}")
    finally:
        cur.close()
        conn.close()

def reset_database():
    """
    DANGEROUS: Drops all tables and recreates them.
    Only use for development/testing.
    """
    print("\n⚠️  WARNING: This will DELETE ALL DATA!")
    print("   All memories and usage records will be permanently lost.")
    print("   This action CANNOT be undone.")
    confirm = input("\nType 'y' to confirm: ")
    
    if confirm != "y":
        print("✗ Reset cancelled")
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n Dropping tables...")
        
        # Drop in correct order (child tables first)
        cur.execute("DROP TABLE IF EXISTS memory_usage CASCADE;")
        print("  ✓ Dropped memory_usage table")
        
        cur.execute("DROP TABLE IF EXISTS memories CASCADE;")
        print("  ✓ Dropped memories table")
        
        conn.commit()
        print("✓ All tables dropped successfully")
        
        cur.close()
        conn.close()
        
        # Recreate everything
        print("\n Recreating database schema...")
        create_tables()
        create_indexes()
        verify_setup()
        
        print("\n✓ Database reset complete!")
        print("   All tables have been recreated with no data.")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error during reset: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if not cur.closed:
            cur.close()
        if not conn.closed:
            conn.close()

def main():
    """Main initialization flow."""
    print("=" * 60)
    print("**NeuroHack Memory System - Database Initialization**")
    print("=" * 60)
    
    if not DATABASE_URL:
        print("✗ ERROR: DATABASE_URL not found in environment variables")
        print("   Please set DATABASE_URL in your .env file")
        sys.exit(1)
    
    print(f"\nDatabase URL: {DATABASE_URL[:30]}...")
    
    # Check database connection
    if not check_database_exists():
        sys.exit(1)
    
    # Show menu
    print("\n" + "=" * 60)
    print("Select an option:")
    print("  1. Initialize database (safe - keeps existing data)")
    print("  2. Show current statistics")
    print("  3. Reset database (DANGEROUS - deletes all data)")
    print("  4. Exit")
    print("=" * 60)
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        print("\n Starting database initialization...")
        try:
            create_tables()
            create_indexes()
            verify_setup()
            get_table_stats()
            print("\n✓ Database initialization complete!")
            print("   You can now run your application.")
        except Exception as e:
            print(f"\n✗ Initialization failed: {e}")
            sys.exit(1)
        
    elif choice == "2":
        try:
            get_table_stats()
        except Exception as e:
            print(f"\n✗ Could not retrieve statistics: {e}")
        
    elif choice == "3":
        try:
            success = reset_database()
            if success:
                print("\n✓ Database reset complete!")
            else:
                print("\n✗ Database reset failed or was cancelled")
        except Exception as e:
            print(f"\n✗ Reset failed: {e}")
            import traceback
            traceback.print_exc()
        
    elif choice == "4":
        print("\n👋 Exiting...")
        sys.exit(0)
        
    else:
        print("\n✗ Invalid choice")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)