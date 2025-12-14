"""
Script rápido para validar se o token do Chatwoot consegue acessar a Account informada.
Uso:
    python test_chatwoot_token.py --account-id 20 [--conversation-id 9]
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()


def safe_request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    try:
        return client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        print(f"❌ Erro ao chamar {url}: {exc}")
        sys.exit(1)


def extract_account_ids(payload) -> list:
    data = []
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("accounts") or []
    elif isinstance(payload, list):
        data = payload

    ids = []
    for item in data:
        if isinstance(item, dict) and "id" in item:
            ids.append(item["id"])
    return ids


def main():
    parser = argparse.ArgumentParser(description="Valida o token do Chatwoot para uma Account específica.")
    parser.add_argument("--account-id", type=int, default=20, help="Account ID a ser testada (default: 20)")
    parser.add_argument("--conversation-id", type=int, help="Opcional: testa leitura de uma conversa específica.")
    parser.add_argument("--base-url", help="Opcional: sobrescreve CHATWOOT_BASE_URL do .env.")
    args = parser.parse_args()

    load_env()

    base_url = (args.base_url or os.getenv("CHATWOOT_BASE_URL", "")).rstrip("/")
    token = os.getenv("CHATWOOT_ACCESS_TOKEN", "")

    if not base_url or not token:
        print("❌ Defina CHATWOOT_BASE_URL e CHATWOOT_ACCESS_TOKEN no .env antes de rodar este teste.")
        sys.exit(1)

    clean_token = token.strip()
    if token and token != clean_token:
        print("⚠️ Token do .env tem espaços extras; usando versão sem whitespace para testar.")

    print(f"🔎 Testando token na base {base_url} | Account {args.account_id}")

    client = httpx.Client(timeout=10, headers={"api_access_token": clean_token})

    profile_url = f"{base_url}/api/v1/profile"
    profile_resp = safe_request(client, "GET", profile_url)
    if profile_resp.status_code != 200:
        print(f"❌ /profile retornou {profile_resp.status_code}: {profile_resp.text}")
        sys.exit(1)
    profile_data = profile_resp.json()
    profile_accounts = extract_account_ids(profile_data.get("accounts") or [])
    print(f"✅ Token aceito. Usuário: {profile_data.get('name')} (id {profile_data.get('id')})")
    if profile_accounts:
        print(f"👀 Accounts visíveis via /profile: {profile_accounts}")

    accounts_url = f"{base_url}/api/v1/accounts"
    accounts_resp = safe_request(client, "GET", accounts_url)
    account_ids = []

    if accounts_resp.status_code == 404:
        print("⚠️ /accounts retornou 404. Algumas versões/roles do Chatwoot não expõem essa rota para tokens de agente.")
        account_ids = profile_accounts
    elif accounts_resp.status_code != 200:
        print(f"⚠️ /accounts retornou {accounts_resp.status_code}: {accounts_resp.text}")
        account_ids = profile_accounts
    else:
        account_ids = extract_account_ids(accounts_resp.json())

    if account_ids:
        if args.account_id in account_ids:
            print(f"✅ Token enxerga a Account {args.account_id}.")
        else:
            print(f"❌ Token NÃO tem acesso à Account {args.account_id}. Contas visíveis: {account_ids}")
    else:
        print("⚠️ Não foi possível confirmar acesso via lista de contas; prosseguindo para testar endpoints específicos.")

    conv_list_url = f"{base_url}/api/v1/accounts/{args.account_id}/conversations"
    conv_list_resp = safe_request(client, "GET", conv_list_url, params={"page": 1})
    if conv_list_resp.status_code != 200:
        print(f"❌ Lista de conversas retornou {conv_list_resp.status_code}: {conv_list_resp.text}")
        sys.exit(1)
    conv_payload = conv_list_resp.json()
    conversations = []
    if isinstance(conv_payload, dict):
        conversations = conv_payload.get("data") or conv_payload.get("payload") or []
    print(f"✅ GET conversas OK ({len(conversations)} itens na primeira página).")

    if args.conversation_id:
        conv_url = f"{base_url}/api/v1/accounts/{args.account_id}/conversations/{args.conversation_id}"
        conv_resp = safe_request(client, "GET", conv_url)
        if conv_resp.status_code != 200:
            print(f"❌ Leitura da conversa {args.conversation_id} falhou ({conv_resp.status_code}): {conv_resp.text}")
            sys.exit(1)
        conv_data = conv_resp.json()
        labels = conv_data.get("labels") or []
        print(f"✅ Conversa {args.conversation_id} acessível. Labels atuais: {labels}")

    print("🎯 Token validado com sucesso.")


if __name__ == "__main__":
    main()
