"""
Test MySQL database connection for LangGraph AI Agent
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(__file__))

from config import settings


async def test_connection():
    """Test database connection and verify tables"""
    print("=" * 60)
    print("Testing MySQL Database Connection")
    print("=" * 60)
    print()
    
    # Parse connection details
    db_url = settings.DATABASE_URL
    try:
        # Extract host and database name from URL
        if "@" in db_url:
            host_part = db_url.split("@")[1]
            db_name = host_part.split("/")[-1] if "/" in host_part else "unknown"
        else:
            host_part = "unknown"
            db_name = "unknown"
        
        print(f"📊 Database URL: {db_url[:30]}...{db_url[-20:]}")
        print(f"🏠 Host: {host_part}")
        print(f"💾 Database: {db_name}")
        print()
        
        # Create engine
        print("🔌 Creating database engine...")
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True
        )
        
        # Test connection
        print("🔗 Testing connection...")
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            if test_value == 1:
                print("✅ Connection successful!")
                print()
                
                # Get MySQL version
                print("📌 MySQL Version:")
                version_result = await conn.execute(text("SELECT VERSION()"))
                version = version_result.scalar()
                print(f"   {version}")
                print()
                
                # List tables
                print("📋 Checking tables...")
                tables_result = await conn.execute(text("SHOW TABLES"))
                tables = [row[0] for row in tables_result]
                
                expected_tables = [
                    'conversation_logs',
                    'admin_availability', 
                    'admin_queue',
                    'analytics_events'
                ]
                
                print(f"   Found {len(tables)} tables:")
                for table in tables:
                    if table in expected_tables:
                        print(f"   ✅ {table}")
                    else:
                        print(f"   ⚠️  {table} (unexpected)")
                
                # Check for missing tables
                missing = set(expected_tables) - set(tables)
                if missing:
                    print()
                    print("⚠️  Missing tables:")
                    for table in missing:
                        print(f"   ❌ {table}")
                    print()
                    print("Run: mysql -u root -p sweden_relocators_ai < ../database_schema.sql")
                else:
                    print()
                    print("✅ All required tables exist!")
                
                # Test queries on each table
                print()
                print("🧪 Testing table queries...")
                for table in expected_tables:
                    if table in tables:
                        try:
                            count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            count = count_result.scalar()
                            print(f"   ✅ {table}: {count} rows")
                        except Exception as e:
                            print(f"   ❌ {table}: Error - {str(e)[:50]}")
                
        await engine.dispose()
        
        print()
        print("=" * 60)
        print("✅ Database is ready for the LangGraph AI Agent!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Add GROQ_API_KEY to .env file")
        print("  2. Run: python test_workflow.py")
        print("  3. Start API: uvicorn app:app --reload --port 8000")
        print()
        
        return True
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Connection Failed!")
        print("=" * 60)
        print()
        print(f"Error: {str(e)}")
        print()
        print("Troubleshooting:")
        print("  1. Check if MySQL is running:")
        print("     Get-Service MySQL80")
        print()
        print("  2. Verify your password in .env file")
        print("     DATABASE_URL should have correct password")
        print()
        print("  3. Create database if it doesn't exist:")
        print("     mysql -u root -p")
        print("     CREATE DATABASE sweden_relocators_ai;")
        print()
        print("  4. Import schema:")
        print("     mysql -u root -p sweden_relocators_ai < ../database_schema.sql")
        print()
        
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
