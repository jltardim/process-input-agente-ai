# app/services/agent_factory.py
from app.core.database import get_supabase
from app.models.agent import AgentConfig, AgentToolSchema, AgentRAGSchema
import logging

# Configura logs para vermos o que está acontecendo
logger = logging.getLogger("fvk.agent_factory")

class AgentFactory:
    def __init__(self):
        self.db = get_supabase()

    def get_agent_by_chatwoot(self, account_id: int, inbox_name: str) -> AgentConfig:
        """
        Busca o agente filtrando pelas configurações do Chatwoot no JSONB.
        Ex: chatwoot_config->account_id E chatwoot_config->inbox_name
        """
        try:
            print(f"🔍 Buscando agente: Account {account_id} | Inbox {inbox_name}")
            
            # 1. Busca o Agente na tabela 'agents'
            # Usamos a sintaxe de seta (->>) para filtrar dentro do JSONB no Postgres
            response = self.db.table("agents")\
                .select("*")\
                .eq("chatwoot_config->>account_id", str(account_id))\
                .eq("chatwoot_config->>inbox_name", inbox_name)\
                .eq("is_active", True)\
                .execute()

            if not response.data:
                logger.warning(f"❌ Nenhum agente encontrado para {inbox_name}")
                return None

            agent_data = response.data[0]
            agent_id = agent_data["id"]
            print(f"✅ Agente encontrado: {agent_data['name']} (ID: {agent_id})")

            # 2. Busca Tools (JOIN manual para garantir performance e controle)
            # Pegamos a tool configurada (agent_tools) e os detalhes dela (tools_library)
            tools_response = self.db.table("agent_tools")\
                .select("tool_config, tools_library(name, python_handler)")\
                .eq("agent_id", agent_id)\
                .eq("is_enabled", True)\
                .execute()
            
            tools_list = []
            for item in tools_response.data:
                lib = item.get("tools_library")
                if lib:
                    tools_list.append(AgentToolSchema(
                        tool_name=lib["name"],
                        python_handler=lib["python_handler"],
                        tool_config=item["tool_config"]
                    ))

            # 3. Busca RAG (Conhecimento)
            rag_response = self.db.table("agent_rag")\
                .select("*")\
                .eq("agent_id", agent_id)\
                .eq("is_enabled", True)\
                .limit(1)\
                .execute()
            
            rag_config = None
            if rag_response.data:
                r = rag_response.data[0]
                rag_config = AgentRAGSchema(
                    collection_name=r["collection_name"],
                    provider=r["provider"],
                    retrieval_config=r["retrieval_config"]
                )

            # 4. Monta e Retorna o Objeto
            return AgentConfig(
                **agent_data,
                tools=tools_list,
                rag_config=rag_config
            )

        except Exception as e:
            logger.error(f"💥 Erro crítico na Factory: {str(e)}")
            raise e

# Singleton (Instância Global)
agent_factory = AgentFactory()