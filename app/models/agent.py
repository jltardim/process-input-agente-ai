# app/models/agent.py
from pydantic import BaseModel, UUID4, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

# --- Parte 1: Tools (Ferramentas) ---
class AgentToolSchema(BaseModel):
    tool_name: str         # Nome único (ex: google_calendar)
    python_handler: str    # Classe Python (ex: GoogleCalendarTool)
    tool_config: Dict[str, Any] = {} # Config específica (ex: calendar_id)

# --- Parte 2: RAG (Conhecimento) ---
class AgentRAGSchema(BaseModel):
    collection_name: str
    provider: str = "qdrant"
    retrieval_config: Dict[str, Any] = {"score_threshold": 0.7, "top_k": 3}

# --- Parte 3: O Agente Completo ---
class AgentConfig(BaseModel):
    id: UUID4
    name: str
    
    # Cérebro
    system_prompt: str
    model_name: str = "gpt-4.1-2025-04-14"
    openai_api_key: Optional[str] = None
    temperature: float = 0.7
    
    # Comportamento
    debounce_seconds: int = 10
    
    # Integrações (JSON do banco)
    chatwoot_config: Dict[str, Any] = {}
    whatsapp_config: Dict[str, Any] = {}
    
    # Listas Dinâmicas (Preenchidas pela Factory)
    tools: List[AgentToolSchema] = []
    rag_config: Optional[AgentRAGSchema] = None
    
    class Config:
        from_attributes = True