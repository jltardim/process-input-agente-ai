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
    """Divide em blocos legíveis, simulando envio humano."""
    if "\n\n" in text:
        parts = text.split("\n\n")
        return [p.strip() for p in parts if p.strip()]

    abbrev = {"dr", "dra", "sr", "sra", "srta", "srs", "prof", "profa"}
    sentences = []
    buf = []
    n = len(text)

    for idx, ch in enumerate(text):
        buf.append(ch)
        if ch not in ".!?":
            continue

        # Evita quebrar números com ponto (ex: 4.000)
        prev_c = text[idx - 1] if idx - 1 >= 0 else ""
        next_c = text[idx + 1] if idx + 1 < n else ""
        if prev_c.isdigit() and next_c.isdigit():
            continue

        prev_text = "".join(buf[:-1])
        match = re.search(r"([A-Za-zÀ-ÿ]+)\s*$", prev_text)
        prev_word = match.group(1).lower().strip(".") if match else ""
        if prev_word in abbrev:
            continue

        if next_c and not next_c.isspace():
            continue

        sentences.append("".join(buf).strip())
        buf = []

    remainder = "".join(buf).strip()
    if remainder:
        sentences.append(remainder)

    if not sentences:
        return [text.strip()]

    # Agrupa sentenças em blocos com tamanho alvo (~130) para parecer humano
    max_len = 130
    chunks = []
    current = ""

    for sent in sentences:
        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sent

    if current:
        chunks.append(current.strip())

    return chunks or [text.strip()]

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
