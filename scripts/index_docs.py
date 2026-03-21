import os
import sys
from typing import List
from langchain_core.documents import Document

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rag_engine import GraphRAGEngine

def load_md_file(file_path: str) -> List[Document]:
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return [Document(page_content=content, metadata={"source": os.path.basename(file_path)})]

def main():
    # Ensure environment variables are loaded if running manually
    from dotenv import load_dotenv
    load_dotenv()
    
    # return

    print("Initializing GraphRAG Engine...")
    engine = GraphRAGEngine()

    docs = []
    print("Loading documentation...")
    docs.extend(load_md_file("USER_MANUAL.md"))

    if not docs:
        print("No documents found to index.")
        return

    print(f"Indexing {len(docs)} documents...")
    engine.index_documents(docs)
    print("Indexing complete! Vector DB and Knowledge Graph updated.")

if __name__ == "__main__":
    main()
