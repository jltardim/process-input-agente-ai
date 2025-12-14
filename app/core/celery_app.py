from celery import Celery
from app.core.config import settings

# Monta a URL de conexão com senha (se houver)
# Formato: redis://:senha@host:porta/db
auth_part = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""

redis_url = f"redis://{auth_part}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

# Configura o Celery
celery_app = Celery(
    "fvk_worker",
    broker=redis_url,
    backend=redis_url
)

# Configurações para evitar travamentos e usar UTC
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_retry_delay=60,
    task_max_retries=3,
)

celery_app.autodiscover_tasks(["app.services.tasks"])