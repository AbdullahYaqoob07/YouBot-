"""Test Pinecone and embeddings directly"""
import asyncio
from config import settings

async def test_pinecone():
    print("Testing Pinecone and Embeddings...")
    print(f"Pinecone Index: {settings.PINECONE_INDEX}")
    print(f"Pinecone Environment: {settings.PINECONE_ENVIRONMENT}")
    print(f"Embedding Model: {settings.EMBEDDING_MODEL_NAME}")
    print("-" * 60)
    
    try:
        # Test 1: Import libraries
        print("\n1. Importing libraries...")
        from langchain_pinecone import PineconeVectorStore
        from langchain_huggingface import HuggingFaceEmbeddings
        from pinecone import Pinecone
        print("✅ Imports successful")
        
        # Test 2: Initialize Pinecone
        print("\n2. Initializing Pinecone...")
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX)
        print(f"✅ Connected to index: {settings.PINECONE_INDEX}")
        print(f"   Index stats: {index.describe_index_stats()}")
        
        # Test 3: Initialize embeddings
        print("\n3. Initializing embeddings...")
        embeddings = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL_NAME,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        print(f"✅ Embeddings model loaded: {settings.EMBEDDING_MODEL_NAME}")
        
        # Test 4: Test embedding
        print("\n4. Testing embedding generation...")
        test_text = "Hello, this is a test"
        test_embedding = embeddings.embed_query(test_text)
        print(f"✅ Generated embedding vector of length: {len(test_embedding)}")
        
        # Test 5: Create vector store
        print("\n5. Creating vector store...")
        vector_store = PineconeVectorStore(
            index=index,
            embedding=embeddings,
            text_key="text"
        )
        print("✅ Vector store created")
        
        # Test 6: Test similarity search
        print("\n6. Testing similarity search...")
        query = "visa requirements for Sweden"
        results = vector_store.similarity_search(query, k=3)
        print(f"✅ Found {len(results)} results for query: '{query}'")
        for i, doc in enumerate(results, 1):
            print(f"\n   Result {i}:")
            print(f"   Content preview: {doc.page_content[:200]}...")
            print(f"   Metadata: {doc.metadata}")
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Pinecone and embeddings are working.")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_pinecone())
