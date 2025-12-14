from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.agent_factory import agent_factory
from app.core.redis import get_redis
from app.services.tasks import process_message_buffer
from app.services.chatwoot import chatwoot_service
from app.services.llm_service import llm_service
import logging
import json

router = APIRouter()
logger = logging.getLogger("fvk.webhook")
redis_client = get_redis()

@router.post("/chatwoot")
async def chatwoot_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
        event_type = payload.get("event")
        
        if event_type != "message_created":
            return {"status": "ignored"}
        
        msg_type = payload.get("message_type")
        is_private = payload.get("private", False)
        conversation = payload.get("conversation", {})
        account = payload.get("account", {})
        sender = payload.get("sender", {})
        
        conversation_id = conversation.get("id")
        account_id = account.get("id")
        inbox_name = payload.get("inbox", {}).get("name")
        content = payload.get("content", "").strip()
        labels = conversation.get("labels", [])

        # =====================================================================
        # 1. COMANDOS DE PRIORIDADE MÁXIMA (Executa antes de tudo)
        # =====================================================================
        
        # COMANDO: /delme (Limpar memória)
        if content == "/delme":
            logger.info(f"🧹 Limpando memória da conversa {conversation_id}")
            redis_client.delete(f"buffer:{conversation_id}")
            llm_service.clear_history(conversation_id)

            # Marca como bot para não disparar pausa automática quando enviar a resposta.
            redis_client.setex(f"bot_sent:{conversation_id}", 10, "1")
            background_tasks.add_task(chatwoot_service.send_text_message, account_id, conversation_id, "♻️ Memória reiniciada!")
            # Se estava pausado, aproveita e despausa (opcional, mas faz sentido)
            if "pausar_atendimento" in labels:
                 background_tasks.add_task(chatwoot_service.remove_label, account_id, conversation_id, "pausar_atendimento")
            return {"status": "processed", "action": "memory_cleared"}

        # COMANDO: # ou /play (Despausar)
        if content in ["#", "/play"]:
            # Só faz algo se realmente estiver pausado ou se quiser garantir
            logger.info(f"▶️ Comando de desbloqueio (#) recebido para {conversation_id}")
            
            # Remove a etiqueta
            background_tasks.add_task(chatwoot_service.remove_label, account_id, conversation_id, "pausar_atendimento")
            
            # Não envia mensagem "Estou de volta", apenas libera silenciosamente.
            return {"status": "processed", "action": "resumed_silent"}

        # =====================================================================
        # 2. DETECÇÃO DE INTERVENÇÃO HUMANA (PAUSA AUTOMÁTICA)
        # =====================================================================
        
        # Se for SAÍDA (outgoing), não importa se é privada ou pública
        if msg_type == "outgoing":
            # Verifica se foi o bot que acabou de enviar (marca no Redis tasks.py)
            if redis_client.get(f"bot_sent:{conversation_id}"):
                return {"status": "ignored", "reason": "bot_echo"}
            
            # Se não foi o bot e NÃO foi comando # (já verificado acima), então é humano falando.
            logger.info(f"🛑 Intervenção humana detectada na conversa {conversation_id}. Pausando.")
            background_tasks.add_task(chatwoot_service.add_labels, account_id, conversation_id, ["pausar_atendimento"])
            background_tasks.add_task(chatwoot_service.toggle_status, account_id, conversation_id, "open")
            return {"status": "processed", "action": "auto_paused"}

        # =====================================================================
        # 3. FILTROS PADRÃO
        # =====================================================================
        
        # Ignora mensagens que não sejam de entrada (incoming) ou que sejam privadas
        if msg_type != "incoming" or is_private:
            return {"status": "ignored"}

        # Verifica se o agente existe
        agent = agent_factory.get_agent_by_chatwoot(account_id, inbox_name)
        if not agent:
            return {"status": "ignored", "reason": "no_agent"}

        # Se estiver pausado, o robô fica em silêncio absoluto
        if "pausar_atendimento" in labels:
            print(f"⛔ Conversa {conversation_id} pausada. Ignorando usuário.")
            return {"status": "ignored", "reason": "paused"}

        # =====================================================================
        # 4. BUFFER E PROCESSAMENTO
        # =====================================================================
        
        background_tasks.add_task(chatwoot_service.toggle_status, account_id, conversation_id, "pending")

        buffer_key = f"buffer:{conversation_id}"
        msg_data = {"content": content, "role": "user", "name": sender.get("name", "User")}
        redis_client.rpush(buffer_key, json.dumps(msg_data))
        redis_client.expire(buffer_key, 3600) 

        debounce_time = agent.debounce_seconds if agent.debounce_seconds > 0 else 10
        
        task = process_message_buffer.apply_async(
            args=[conversation_id, account_id, inbox_name],
            countdown=debounce_time
        )
        
        return {"status": "buffered", "task_id": task.id}

    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
