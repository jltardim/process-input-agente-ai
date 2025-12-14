import redis
import sys

print("⚡️ Testando conexão com Redis via Localhost:6381...")

try:
    # Tenta conectar com timeout curto (5s) para não travar
    r = redis.Redis(
        host="localhost", 
        port=6381, 
        password="SenhaForte123", # <--- CONFIRA SUA SENHA DO .ENV
        socket_timeout=5
    )
    
    print("1. Tentando PING...")
    response = r.ping()
    print(f"✅ Redis respondeu: {response}")
    
    print("2. Tentando escrever no banco...")
    r.set("teste_conexao", "funciona")
    print("✅ Escrita funcionou!")
    
except redis.exceptions.AuthenticationError:
    print("❌ ERRO DE SENHA: A conexão funcionou, mas a senha está errada.")
except redis.exceptions.ConnectionError as e:
    print(f"❌ ERRO DE CONEXÃO: Não foi possível alcançar o Redis.\nDetalhe: {e}")
    print("DICA: Verifique se o Túnel SSH está rodando e se a porta 6381 está correta.")
except redis.exceptions.TimeoutError:
    print("❌ TIMEOUT: O Redis aceitou a conexão mas parou de responder.")
except Exception as e:
    print(f"❌ ERRO DESCONHECIDO: {e}")