import re
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from app.rag_engine import get_rag_engine
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import os

router = APIRouter(prefix="/support", tags=["support"])

SYSTEM_PROMPT = """You are the CBMS Pro Support Bot. You help users with questions about using the Bulk WhatsApp Message sender.
You must answer ONLY using the provided knowledge base context. 
IMPORTANT: Focus EXCLUSIVELY on user-facing dashboard features (sending messages, Excel formatting, profile/security settings). 
STRICT RULE: NEVER provide technical setup instructions (e.g., git, pip, venv, .env, uvicorn installation). 
If a user asks about installation or technical setup, say: "I am designed to help with the dashboard features. For technical setup or installation, please refer to the Developer Documentation in the project root or contact your system administrator."
If the answer is not in the context, say: "I'm sorry, I don't have information about that. Please contact human support."
Be professional, concise, and helpful."""

def markdown_to_html(text: str) -> str:
    """Converts basic markdown to HTML for the chat UI."""
    if not text:
        return ""
    
    # 1. Strip dangerous tags FIRST
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # 2. Links: [text](url)
    link_pattern = r'\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)'
    text = re.sub(
        link_pattern,
        r'<a href="\2" target="_blank" rel="noopener noreferrer" style="color:#3b82f6;text-decoration:underline;cursor:pointer;">\1</a>',
        text
    )
    
    # 3. Bold + Italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'___(.+?)___', r'<b><i>\1</i></b>', text)
    
    # 4. Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 5. Italic
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    
    # 6. Replace newlines with <br>
    text = text.replace("\n", "<br>")
    
    return text

@router.post("/chat")
async def support_chat(request: Request):
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()
        if not user_message:
            return JSONResponse({"reply": "Please enter a message."})

        # Session-based history (FastAPI SessionMiddleware is already in main.py)
        session = request.session
        history = session.get("support_chat_history", [])
        
        if not history:
            history.append({"role": "system", "content": SYSTEM_PROMPT})

        # 1. Retrieve Context
        engine = get_rag_engine()
        context = engine.retrieve(user_message)

        if context == "LOW_CONFIDENCE":
            return JSONResponse({"reply": "I'm sorry, I don't have enough information to answer that accurately. Try asking about WhatsApp sessions, Excel formats, or campaign types."})

        # 2. Construct Prompt
        # We only inject context for the CURRENT user message to keep history clean
        rag_prompt = f"Relevant Knowledge Base:\n{context}\n\nUser Question: {user_message}"
        
        # 3. LLM Call
        provider = os.getenv("AI_PROVIDER", "openai").lower()
        if provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            if not api_key:
                return JSONResponse({"reply": "Error: Support bot is currently unavailable (Azure API Key missing)."})
            llm = AzureChatOpenAI(
                azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=api_key,
                temperature=0.5
            )
        elif provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return JSONResponse({"reply": "Error: Support bot is currently unavailable (Gemini API Key missing)."})
            llm = ChatGoogleGenerativeAI(model="models/gemini-flash-latest", google_api_key=api_key, temperature=0.5)
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return JSONResponse({"reply": "Error: Support bot is currently unavailable (OpenAI API Key missing)."})
            llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.5)
        
        # Prepare messages for LangChain
        chat_messages = []
        for msg in history:
            if msg["role"] == "system":
                chat_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                chat_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                # Note: History in session might be HTML, but we want raw for LLM? 
                # Actually, standard RAG keeps raw history.
                chat_messages.append(AIMessage(content=msg["content"]))
        
        # Add the RAG-augmented current message
        chat_messages.append(HumanMessage(content=rag_prompt))

        response = llm.invoke(chat_messages)
        
        # Handle response content which might be a list for Gemini
        bot_reply_raw = response.content
        if isinstance(bot_reply_raw, list):
            parts = []
            for p in bot_reply_raw:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    parts.append(p.get("text", str(p)))
                else:
                    # Check if it has a 'text' attribute (for some LangChain objects)
                    parts.append(getattr(p, "text", str(p)))
            bot_reply_raw = "".join(parts)
        
        if not isinstance(bot_reply_raw, str):
            bot_reply_raw = str(bot_reply_raw)
            
        bot_reply_raw = bot_reply_raw.strip()
        
        # 4. Format and Store
        bot_reply_html = markdown_to_html(bot_reply_raw)
        
        # Append to history (store raw user message but HTML bot reply for frontend)
        # Wait, if we store HTML bot reply, next time LLM gets HTML. Let's store raw in history too.
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply_raw}) # Store raw
        
        # Limit history size
        if len(history) > 11: # System + 5 rounds
            history = [history[0]] + history[-10:]
            
        session["support_chat_history"] = history

        return JSONResponse({"reply": bot_reply_html})

    except Exception as e:
        print(f"Support bot error: {e}")
        return JSONResponse({"reply": "Oops! Something went wrong. Please try again later."})
