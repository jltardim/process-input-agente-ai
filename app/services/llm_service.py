from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.config import settings
from app.models.agent import AgentConfig
from app.core.redis import get_redis
import logging
import json

logger = logging.getLogger("fvk.llm")
redis_client = get_redis()

class LLMService:
    def get_llm(self, agent: AgentConfig):
        api_key = agent.openai_api_key or settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError("API Key não configurada")
            
        model_name = agent.model_name
        if model_name == "gpt-4.1": model_name = "gpt-4o"

        return ChatOpenAI(model=model_name, temperature=agent.temperature, api_key=api_key)

    def get_history(self, conversation_id: int):
        """Recupera histórico do Redis"""
        key = f"history:{conversation_id}"
        data = redis_client.lrange(key, 0, -1)
        history = []
        for item in data:
            msg = json.loads(item)
            if msg["role"] == "user":
                history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                history.append(AIMessage(content=msg["content"]))
        return history

    def add_to_history(self, conversation_id: int, role: str, content: str):
        """Salva mensagem no Redis (Max 20 mensagens para não estourar token)"""
        key = f"history:{conversation_id}"
        msg = json.dumps({"role": role, "content": content})
        redis_client.rpush(key, msg)
        # Mantém apenas as últimas 20 mensagens
        if redis_client.llen(key) > 20:
            redis_client.lpop(key)
        redis_client.expire(key, 86400) # Expira em 24h

    def clear_history(self, conversation_id: int):
        redis_client.delete(f"history:{conversation_id}")

    async def generate_response(self, agent: AgentConfig, user_input: str, conversation_id: int) -> str:
        try:
            llm = self.get_llm(agent)
            history = self.get_history(conversation_id)
            
            # Prompt com Histórico
            prompt = ChatPromptTemplate.from_messages([
                ("system", "{system_prompt}"),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}")
            ])
            
            chain = prompt | llm | StrOutputParser()
            
            logger.info(f"🧠 Gerando resposta para conv {conversation_id}...")
            response = await chain.ainvoke({
                "system_prompt": agent.system_prompt,
                "history": history,
                "input": user_input
            })
            
            # Salva o turno atual na memória
            self.add_to_history(conversation_id, "user", user_input)
            self.add_to_history(conversation_id, "assistant", response)
            
            return response

        except Exception as e:
            logger.error(f"💥 Erro LLM: {str(e)}")
            return "Desculpe, tive um erro técnico."

llm_service = LLMService()