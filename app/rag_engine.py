import os
import json
import networkx as nx
from typing import List, Dict, Any
from langchain_openai import OpenAIEmbeddings, ChatOpenAI, AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import re

class GraphRAGEngine:
    def __init__(self, persist_directory: str = "chroma_db_v2", graph_path: str = "knowledge_graph_v2.json"):
        self.persist_directory = persist_directory
        self.graph_path = graph_path
        
        provider = os.getenv("AI_PROVIDER", "openai").lower()
        if provider == "azure":
            self.embeddings = AzureOpenAIEmbeddings(
                azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY")
            )
        elif provider == "gemini":
            self.embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",
                google_api_key=os.getenv("GOOGLE_API_KEY")
            )
        else:
            self.embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))

        self.vector_db = Chroma(persist_directory=self.persist_directory, embedding_function=self.embeddings)
        self.graph = nx.Graph()
        self._load_graph()

    def _load_graph(self):
        if os.path.exists(self.graph_path):
            with open(self.graph_path, 'r') as f:
                data = json.load(f)
                self.graph = nx.node_link_graph(data)
        else:
            self.graph = nx.Graph()

    def _save_graph(self):
        data = nx.node_link_data(self.graph)
        with open(self.graph_path, 'w') as f:
            json.dump(data, f)

    def index_documents(self, documents: List[Document]):
        """Indexes documents into Vector DB and builds the relationship graph."""
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_documents(documents)

        # 1. Add to Vector DB
        self.vector_db.add_documents(chunks)
        
        # 2. Extract entities and build graph
        for i, chunk in enumerate(chunks):
            chunk_id = f"chunk_{i}_{hash(chunk.page_content[:50])}"
            self.graph.add_node(chunk_id, type="chunk", content=chunk.page_content, metadata=chunk.metadata)
            
            # Simple entity extraction (can be improved with LLM)
            entities = self._extract_entities(chunk.page_content)
            for entity in entities:
                entity = entity.lower().strip()
                if not self.graph.has_node(entity):
                    self.graph.add_node(entity, type="entity")
                self.graph.add_edge(chunk_id, entity)
                
                # Link entities in the same chunk
                for other_entity in entities:
                    other_entity = other_entity.lower().strip()
                    if entity != other_entity:
                        self.graph.add_edge(entity, other_entity)

        self._save_graph()

    def _extract_entities(self, text: str) -> List[str]:
        """Simple regex-based entity extraction for product terminology."""
        # Focus on capitalized words, quoted terms, and product-specific keywords
        keywords = ["WhatsApp", "Excel", "MFA", "OAuth", "API", "QR Code", "Session", "Campaign", "WaSender", "Dashboard", "Personalization", "Variables"]
        found = set()
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text, re.I):
                found.add(kw)
        
        # Also extract terms in [backticks] or **bold**
        found.update(re.findall(r'`([^`]+)`', text))
        found.update(re.findall(r'\*\*([^*]+)\*\*', text))
        
        return list(found)

    def retrieve(self, query: str, k: int = 4) -> str:
        """Advanced retrieval using vector search and graph expansion."""
        provider = os.getenv("AI_PROVIDER", "openai").lower()
        if provider == "azure":
            if not os.getenv("AZURE_OPENAI_API_KEY"):
                return "ERROR: Azure OpenAI API Key missing."
        elif provider == "gemini":
            if not os.getenv("GOOGLE_API_KEY"):
                return "ERROR: Gemini API Key missing."
        elif not os.getenv("OPENAI_API_KEY"):
            return "ERROR: OpenAI API Key missing."

        # 1. Vector Search for base context
        base_docs = self.vector_db.similarity_search(query, k=k)
        
        # 2. Graph Expansion: Find entities in the query and their related chunks
        query_entities = self._extract_entities(query)
        expanded_chunks = set()
        
        for entity in query_entities:
            entity = entity.lower().strip()
            if self.graph.has_node(entity):
                # Find direct neighbors (chunks and other entities)
                neighbors = list(self.graph.neighbors(entity))
                for neighbor in neighbors:
                    node_data = self.graph.nodes[neighbor]
                    if node_data.get("type") == "chunk":
                        expanded_chunks.add(node_data["content"])
                    elif node_data.get("type") == "entity":
                        # If neighbor is another entity, find chunks for THAT entity (1-hop)
                        sub_neighbors = self.graph.neighbors(neighbor)
                        for sn in sub_neighbors:
                            if self.graph.nodes[sn].get("type") == "chunk":
                                expanded_chunks.add(self.graph.nodes[sn]["content"])

        # 3. Combine results
        all_context = [doc.page_content for doc in base_docs]
        # Dedup and add expanded context (prioritize vector search results)
        existing_content = set(all_context)
        for content in expanded_chunks:
            if content not in existing_content:
                all_context.append(content)
                if len(all_context) >= k * 2: # Don't overwhelm with context
                    break

        return "\n\n---\n\n".join(all_context) if all_context else "LOW_CONFIDENCE"

def get_rag_engine():
    # Helper to initialize engine with env key
    return GraphRAGEngine()
