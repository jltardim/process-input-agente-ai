from app.core.celery_app import celery_app
from app.core.redis import get_redis
from app.services.agent_factory import agent_factory
from app.services.llm_service import llm_service
from app.services.chatwoot import chatwoot_service
from asgiref.sync import async_to_sync
import logging
import json
import time
import re

logger = logging.getLogger("fvk.worker")
redis_client = get_redis()

def split_message(text: str):
    """Quebra mensagens grandes em blocos naturais"""
    # Se tiver quebra de linha dupla, usa ela (parágrafos naturais)
    if "\n\n" in text:
        parts = text.split("\n\n")
        return [p.strip() for p in parts if p.strip()]

    # Não quebrar textos curtos para evitar cortes em abreviações como "Dra."
    if len(text) <= 400:
        return [text.strip()]

    # Split manual evitando abreviações comuns e juntando pedaços muito curtos
    abbrev = {"dr", "dra", "sr", "sra", "srta", "srs", "prof", "profa"}

    def is_abbrev(segment: str) -> bool:
        match = re.search(r"([A-Za-zÀ-ÿ]+)\s*$", segment)
        if not match:
            return False
        return match.group(1).lower().strip(".") in abbrev

    parts = []
    buffer = []

    for idx, ch in enumerate(text):
        buffer.append(ch)
        if ch in ".!?":
            prev_text = "".join(buffer[:-1])
            if is_abbrev(prev_text):
                continue

            next_char = text[idx + 1] if idx + 1 < len(text) else ""
            if next_char and not next_char.isspace():
                continue

            segment = "".join(buffer).strip()
            if segment:
                parts.append(segment)
            buffer = []

    remainder = "".join(buffer).strip()
    if remainder:
        parts.append(remainder)

    # Junta pedaços muito curtos para não ficar frase quebrada
    merged = []
    for part in parts:
        if merged and (len(part) < 80 or len(merged[-1]) < 80):
            merged[-1] = (merged[-1] + " " + part).strip()
        else:
            merged.append(part)

    return merged or [text.strip()]

@celery_app.task(bind=True, name="process_message_buffer")
def process_message_buffer(self, conversation_id: int, account_id: int, inbox_name: str):
    lock_key = f"lock:processing:{conversation_id}"
    buffer_key = f"buffer:{conversation_id}"
    
    # Lock para evitar processamento duplicado
    if not redis_client.set(lock_key, "locked", ex=60, nx=True):
        return

    try:
        # Lê Buffer
        messages = redis_client.lrange(buffer_key, 0, -1)
        if not messages:
            return
        
        redis_client.delete(buffer_key)
        
        # Junta mensagens do usuário
        full_text = " ".join([json.loads(m)["content"] for m in messages])
        logger.info(f"🔥 PROCESSANDO {conversation_id}: {full_text}")

        agent = agent_factory.get_agent_by_chatwoot(account_id, inbox_name)
        if not agent:
            return

        # Gera resposta (AGORA COM MEMÓRIA PASSANDO O ID)
        response_text = async_to_sync(llm_service.generate_response)(agent, full_text, conversation_id)
        
        # Quebra a resposta (Humanização)
        message_parts = split_message(response_text)

        for part in message_parts:
            # 1. Marca que o bot está enviando (para o webhook não pausar)
            # Define validade de 10s, suficiente para o webhook receber o evento 'message_created'
            redis_client.setex(f"bot_sent:{conversation_id}", 10, "1")
            
            # 2. Envia a parte
            async_to_sync(chatwoot_service.send_text_message)(
                account_id=account_id, 
                conversation_id=conversation_id, 
                message=part
            )
            
            # 3. Delay humano entre mensagens (proporcional ao tamanho, min 1s, max 4s)
            delay = min(max(len(part) * 0.05, 1), 4)
            time.sleep(delay)

    except Exception as e:
        logger.error(f"Erro worker: {e}")
    finally:
        redis_client.delete(lock_key)
