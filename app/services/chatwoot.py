import httpx
import logging
from app.core.config import settings

logger = logging.getLogger("fvk.chatwoot")

class ChatwootService:
    def __init__(self):
        self.base_url = settings.CHATWOOT_BASE_URL.rstrip("/")
        raw_token = settings.CHATWOOT_ACCESS_TOKEN or ""
        clean_token = raw_token.strip()
        if raw_token and raw_token != clean_token:
            logger.warning("CHATWOOT_ACCESS_TOKEN tem espaços extras; usando valor sem whitespace.")
        self.headers = {"api_access_token": clean_token}

    async def _request(self, method, url, json=None):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, json=json, headers=self.headers)
                # Retorna None se der 404, para não quebrar o fluxo
                if resp.status_code == 404:
                    logger.warning(f"⚠️ 404 Not Found: {url}")
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"❌ Erro Chatwoot API ({method} {url}): {e}")
            return None

    async def get_conversation(self, account_id: int, conversation_id: int):
        """Lê os dados da conversa para pegar as etiquetas atuais."""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}"
        return await self._request("GET", url)

    async def send_text_message(self, account_id: int, conversation_id: int, message: str):
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
        return await self._request("POST", url, json={"content": message, "message_type": "outgoing"})

    async def toggle_status(self, account_id: int, conversation_id: int, status: str):
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_status"
        await self._request("POST", url, json={"status": status})

    async def add_labels(self, account_id: int, conversation_id: int, labels: list):
        # Para adicionar, a gente apenas manda a lista nova. O Chatwoot une ou sobrescreve.
        # Por segurança, vamos ler as atuais e somar com as novas para garantir que não vamos perder nada.
        conv = await self.get_conversation(account_id, conversation_id)
        if not conv: return

        current_labels = conv.get("labels", [])
        # Junta as listas sem duplicar
        new_labels_list = list(set(current_labels + labels))
        
        await self.set_labels(account_id, conversation_id, new_labels_list)

    async def remove_label(self, account_id: int, conversation_id: int, label_to_remove: str):
        """
        Estratégia: LER -> FILTRAR -> GRAVAR
        Remove a etiqueta lendo todas, tirando a indesejada e salvando a lista de novo.
        """
        # 1. Busca etiquetas atuais
        conv = await self.get_conversation(account_id, conversation_id)
        if not conv: 
            logger.error("Não foi possível ler a conversa para remover a tag.")
            return

        current_labels = conv.get("labels", [])
        
        # 2. Verifica se a tag existe na lista
        if label_to_remove in current_labels:
            # 3. Cria nova lista SEM a tag proibida
            updated_labels = [l for l in current_labels if l != label_to_remove]
            
            logger.info(f"🔄 Atualizando labels: De {current_labels} para {updated_labels}")
            
            # 4. Grava a nova lista
            await self.set_labels(account_id, conversation_id, updated_labels)
        else:
            logger.info(f"ℹ️ A etiqueta '{label_to_remove}' já não estava na conversa.")

    async def set_labels(self, account_id: int, conversation_id: int, labels: list):
        """Envia a lista definitiva de labels para a conversa."""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels"
        await self._request("POST", url, json={"labels": labels})

chatwoot_service = ChatwootService()
