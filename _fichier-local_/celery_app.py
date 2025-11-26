"""Configuration Celery pour LinkGuardian - version Flask + RabbitMQ + Beat"""

from celery import Celery
from celery.schedules import crontab

# ✅ Créer l'instance Celery STANDALONE (sans Flask au départ)
celery = Celery(
    "linkguardian",
    broker="amqp://guest:guest@localhost:5672//",   # RabbitMQ
    backend="rpc://",             # Redis pour les résultats
)

# Configuration commune
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Paris",
    enable_utc=True,

    # 🔥 IMPORTANT : Dire à Celery où trouver les tâches
    imports=("tasks",),

    # Gestion des tâches
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,

    # Expiration et résultats
    result_expires=3600,
    task_ignore_result=False,

    # Retry automatique
    task_autoretry_for=(Exception,),
    task_retry_backoff=True,
    task_retry_backoff_max=3600,
    task_max_retries=3,
    task_retry_jitter=True,

    # Limitation du débit
    task_default_rate_limit="10/m",
    worker_disable_rate_limits=False,

    # Timeout
    task_soft_time_limit=300,
    task_time_limit=360,

    # Options RabbitMQ
    broker_transport_options={
        "visibility_timeout": 3600,
        "confirm_publish": True,
    },
)

# ✅ Planificateur de tâches (beat)
celery.conf.beat_schedule = {
    "check-all-sites-weekly": {
        "task": "tasks.check_all_sites_weekly",
        "schedule": crontab(day_of_week="monday", hour=2, minute=0),
    },
}


def init_celery(app):
    """
    Initialise Celery avec le contexte Flask après la création de l'app.
    À appeler depuis app.py après la création de l'instance Flask.
    """
    class ContextTask(celery.Task):
        """Exécute chaque tâche dans un contexte Flask"""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

print("ℹ️ Celery chargé (à initialiser via init_celery(app) depuis app.py)")


# ===============================
# ⚙️ Configuration Celery
# ===============================
from app import app

init_celery(app)  # Initialise Celery avec le contexte Flask