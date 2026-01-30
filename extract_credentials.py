"""
Extract credentials from your n8n installation and populate .env file
"""
import os
import json
import re
from pathlib import Path

print("=" * 60)
print("n8n → LangGraph Credential Migration Tool")
print("=" * 60)

def find_n8n_credentials():
    """Try to locate n8n credentials file"""
    possible_paths = [
        Path.home() / ".n8n" / ".env",
        Path.home() / ".n8n" / "config",
        Path("/opt/n8n/.env"),
        Path("C:/Users") / os.environ.get("USERNAME", "") / ".n8n" / ".env",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    return None

def extract_env_vars(file_path):
    """Extract environment variables from file"""
    vars_dict = {}
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    vars_dict[key.strip()] = value.strip()
    return vars_dict

def main():
    print("\n📋 Step 1: Locate n8n credentials")
    print("-" * 60)
    
    # Try to find n8n credentials
    n8n_path = find_n8n_credentials()
    
    if n8n_path:
        print(f"✅ Found n8n credentials at: {n8n_path}")
        creds = extract_env_vars(n8n_path)
        print(f"   Found {len(creds)} environment variables")
    else:
        print("⚠️  Could not auto-locate n8n credentials")
        print("   Please provide the path manually:")
        custom_path = input("   Path to n8n .env file (or press Enter to skip): ").strip()
        
        if custom_path and Path(custom_path).exists():
            creds = extract_env_vars(custom_path)
        else:
            print("   Skipping automatic extraction...")
            creds = {}
    
    print("\n" + "=" * 60)
    print("📝 Step 2: Manual Credential Entry")
    print("=" * 60)
    print("\nPlease provide the following credentials:")
    print("(Press Enter to skip optional fields)")
    
    # Collect credentials
    credentials = {}
    
    # Required
    print("\n🔑 REQUIRED:")
    groq_key = input("  GROQ_API_KEY (from https://console.groq.com/keys): ").strip()
    if groq_key:
        credentials['GROQ_API_KEY'] = groq_key
    elif 'GROQ_API_KEY' in creds:
        credentials['GROQ_API_KEY'] = creds['GROQ_API_KEY']
        print(f"    Using from n8n: {creds['GROQ_API_KEY'][:20]}...")
    
    # Database
    print("\n💾 DATABASE:")
    db_url = input("  DATABASE_URL (e.g., mysql+asyncmy://user:pass@localhost:3306/db): ").strip()
    if db_url:
        credentials['DATABASE_URL'] = db_url
    elif 'DATABASE_URL' in creds:
        credentials['DATABASE_URL'] = creds['DATABASE_URL']
        print(f"    Using from n8n: {creds['DATABASE_URL'][:40]}...")
    else:
        credentials['DATABASE_URL'] = "mysql+asyncmy://root:password@localhost:3306/sweden_relocators_ai"
        print(f"    Using default: {credentials['DATABASE_URL']}")
    
    # Vector DB
    print("\n🔍 VECTOR DATABASE:")
    vector_url = input("  VECTOR_DB_URL (e.g., http://localhost:8000) [Enter for default]: ").strip()
    if vector_url:
        credentials['VECTOR_DB_URL'] = vector_url
    elif 'VECTOR_DB_URL' in creds:
        credentials['VECTOR_DB_URL'] = creds['VECTOR_DB_URL']
        print(f"    Using from n8n: {creds['VECTOR_DB_URL']}")
    
    # Optional - OpenAI
    print("\n🤖 OPTIONAL - OpenAI (for embeddings):")
    openai_key = input("  OPENAI_API_KEY [Enter to skip]: ").strip()
    if openai_key:
        credentials['OPENAI_API_KEY'] = openai_key
    elif 'OPENAI_API_KEY' in creds:
        credentials['OPENAI_API_KEY'] = creds['OPENAI_API_KEY']
        print(f"    Using from n8n: {creds['OPENAI_API_KEY'][:20]}...")
    
    # Optional - Pinecone
    print("\n📌 OPTIONAL - Pinecone:")
    pinecone_key = input("  PINECONE_API_KEY [Enter to skip]: ").strip()
    if pinecone_key:
        credentials['PINECONE_API_KEY'] = pinecone_key
        credentials['PINECONE_ENVIRONMENT'] = input("  PINECONE_ENVIRONMENT (e.g., us-east-1): ").strip()
        credentials['PINECONE_INDEX'] = input("  PINECONE_INDEX (e.g., sweden-relocators): ").strip()
    
    print("\n" + "=" * 60)
    print("💾 Step 3: Generate .env file")
    print("=" * 60)
    
    # Read .env.example
    env_example_path = Path(__file__).parent / ".env.example"
    env_path = Path(__file__).parent / ".env"
    
    if not env_example_path.exists():
        print("❌ Error: .env.example not found!")
        return
    
    # Read template
    with open(env_example_path, 'r') as f:
        env_content = f.read()
    
    # Replace placeholders
    for key, value in credentials.items():
        # Replace the placeholder value
        pattern = f"{key}=.*"
        replacement = f"{key}={value}"
        env_content = re.sub(pattern, replacement, env_content)
    
    # Write .env file
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"✅ Created .env file at: {env_path}")
    print(f"   Configured {len(credentials)} credentials")
    
    print("\n" + "=" * 60)
    print("📊 Configuration Summary")
    print("=" * 60)
    
    for key in credentials:
        value = credentials[key]
        if 'KEY' in key or 'PASSWORD' in key:
            # Mask sensitive values
            masked = value[:10] + "..." + value[-5:] if len(value) > 15 else "***"
            print(f"  ✓ {key}: {masked}")
        else:
            print(f"  ✓ {key}: {value[:50]}...")
    
    print("\n" + "=" * 60)
    print("🎯 Next Steps")
    print("=" * 60)
    print("""
1. Review your .env file:
   code .env

2. Set up MySQL database:
   mysql -u root -p < ../database_schema.sql

3. Run tests:
   python test_workflow.py

4. Start the API server:
   uvicorn app:app --reload --port 5678

5. Test the API:
   curl -X POST http://localhost:5678/webhook/ai-agent \\
     -H "Content-Type: application/json" \\
     -d '{"message": "Hej! Hur får jag personnummer?", "user_id": "test123"}'

6. Check health:
   curl http://localhost:5678/health
""")
    
    print("\n✨ Setup complete! Your LangGraph agent is ready to run!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
