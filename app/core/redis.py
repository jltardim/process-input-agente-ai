import redis
from app.core.config import settings

# Pool de conexões do Redis
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    decode_responses=True # Retorna strings, não bytes
)

def get_redis():
    return redis_client