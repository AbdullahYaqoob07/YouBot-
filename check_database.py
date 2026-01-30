import pymysql
import sys

# Database connection details
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'pak88523',
    'database': 'sweden_relocators_ai',
    'charset': 'utf8mb4'
}

print("Checking database connection and tables...")
print("=" * 60)

try:
    # Connect to database
    connection = pymysql.connect(**db_config)
    print("✓ Database connection successful\n")
    
    with connection.cursor() as cursor:
        # Check tables
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()
        
        if tables:
            print(f"✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"  - {table[0]}")
        else:
            print("✗ No tables found in database!")
            print("\nPlease run the SQL script in MySQL Workbench:")
            print("  File: C:\\Users\\ABDULLAH\\OneDrive\\Desktop\\RAG_bot\\langgraph_agent\\quick_setup.sql")
            sys.exit(1)
        
        print("\n" + "=" * 60)
        print("Checking table structures...")
        print("=" * 60 + "\n")
        
        # Check each table
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DESCRIBE {table_name};")
            columns = cursor.fetchall()
            print(f"{table_name}:")
            print(f"  Columns: {len(columns)}")
            for col in columns[:5]:  # Show first 5 columns
                print(f"    - {col[0]} ({col[1]})")
            if len(columns) > 5:
                print(f"    ... and {len(columns) - 5} more columns")
            print()
    
    connection.close()
    print("=" * 60)
    print("✓ Database is properly configured!")
    print("=" * 60)
    
except pymysql.Error as e:
    print(f"\n✗ Database Error: {e}")
    print("\nPlease ensure:")
    print("  1. MySQL is running")
    print("  2. Database 'sweden_relocators_ai' exists")
    print("  3. Tables are created (run quick_setup.sql in MySQL Workbench)")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)
