"""
Setup and Installation Script
Run this to initialize the LangGraph AI Agent
"""
import os
import sys
import subprocess
from pathlib import Path


def print_step(step_number, message):
    """Print formatted step message"""
    print(f"\n{'='*60}")
    print(f"STEP {step_number}: {message}")
    print(f"{'='*60}\n")


def run_command(command, description):
    """Run shell command with error handling"""
    print(f"Running: {description}")
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {description} failed")
        print(f"Error details: {str(e)}")
        return False


def main():
    """Main setup function"""
    print("\n" + "="*60)
    print("🚀 LANGGRAPH AI AGENT SETUP")
    print("="*60)
    
    # Step 1: Check Python version
    print_step(1, "Checking Python Version")
    if sys.version_info < (3, 9):
        print("❌ Python 3.9+ required")
        sys.exit(1)
    print(f"✅ Python {sys.version} detected")
    
    # Step 2: Create directories
    print_step(2, "Creating Directories")
    directories = ["logs", "data", "data/chroma_db"]
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {directory}")
    
    # Step 3: Create .env file
    print_step(3, "Creating Environment File")
    if not Path(".env").exists():
        if Path(".env.example").exists():
            import shutil
            shutil.copy(".env.example", ".env")
            print("✅ Created .env from .env.example")
            print("⚠️  IMPORTANT: Edit .env and add your API keys!")
        else:
            print("❌ .env.example not found")
    else:
        print("✅ .env file already exists")
    
    # Step 4: Create virtual environment
    print_step(4, "Creating Virtual Environment")
    if not Path("venv").exists():
        if run_command("python -m venv venv", "Creating virtual environment"):
            print("✅ Virtual environment created")
            print("\n⚠️  To activate:")
            print("   Windows: venv\\Scripts\\activate")
            print("   Linux/Mac: source venv/bin/activate")
        else:
            print("❌ Failed to create virtual environment")
            sys.exit(1)
    else:
        print("✅ Virtual environment already exists")
    
    # Step 5: Install dependencies
    print_step(5, "Installing Dependencies")
    activate_cmd = "venv\\Scripts\\activate" if os.name == 'nt' else "source venv/bin/activate"
    print(f"\n⚠️  Please run the following commands manually:")
    print(f"   1. {activate_cmd}")
    print(f"   2. pip install --upgrade pip")
    print(f"   3. pip install -r requirements.txt")
    
    # Step 6: Database setup
    print_step(6, "Database Setup Instructions")
    print("""
The system uses MySQL for main data and SQLite for checkpointing.

1. Create MySQL database:
   CREATE DATABASE sweden_relocators_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

2. Run the schema file:
   mysql -u root -p sweden_relocators_ai < ../database_schema.sql

3. Update DATABASE_URL in .env file

4. Test connection:
   python -c "from database.models import engine; import asyncio; asyncio.run(engine.connect())"
""")
    
    # Step 7: Vector store setup
    print_step(7, "Vector Store Setup")
    print("""
The system supports multiple vector stores:

1. **Chroma (Local - Default)**:
   - No additional setup needed
   - Data stored in: ./data/chroma_db
   - Set VECTOR_STORE_TYPE=chroma in .env

2. **Pinecone (Cloud)**:
   - Sign up at: https://www.pinecone.io/
   - Create index: "sweden-relocators"
   - Add PINECONE_API_KEY to .env
   - Set VECTOR_STORE_TYPE=pinecone

3. **Qdrant (Local or Cloud)**:
   - Install: docker run -p 6333:6333 qdrant/qdrant
   - Set VECTOR_STORE_TYPE=qdrant in .env

To populate vector store with knowledge base:
   python scripts/ingest_knowledge_base.py
""")
    
    # Step 8: Testing
    print_step(8, "Testing the System")
    print("""
1. Start the server:
    uvicorn app:app --reload --port 8000

2. Test health endpoint:
    curl http://localhost:8000/health

3. Send test message:
    curl -X POST http://localhost:8000/webhook/ai-agent \\
     -H "Content-Type: application/json" \\
     -d '{"message": "I want to move to Sweden", "userId": "test_001"}'

4. Run tests:
   pytest tests/
""")
    
    # Step 9: Production deployment
    print_step(9, "Production Deployment")
    print("""
For production deployment:

1. Set DEBUG=False in .env

2. Use production server:
    gunicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

3. Use reverse proxy (nginx):
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }

4. Use supervisor/systemd for process management

5. Set up monitoring (Prometheus, Grafana)
""")
    
    # Final message
    print("\n" + "="*60)
    print("✅ SETUP COMPLETE!")
    print("="*60)
    print("""
Next steps:
1. Activate virtual environment
2. Install dependencies: pip install -r requirements.txt
3. Edit .env with your API keys
4. Set up MySQL database
5. Test the system
6. Deploy to production

For help, see README.md
""")


if __name__ == "__main__":
    main()
