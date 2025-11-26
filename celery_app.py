"""Configuration Celery pour LinkGuardian - version Flask + RabbitMQ + Beat
Optimisé pour multi-workers et imports massifs
"""

import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

broker_user = os.getenv("RABBITMQ_DEFAULT_USER")
broker_pass = os.getenv("RABBITMQ_DEFAULT_PASS")

# ✅ Créer l'instance Celery STANDALONE (sans Flask au départ)
celery = Celery(
    "linkguardian",
    broker=f"amqp://{broker_user}:{broker_pass}@rabbitmq:5672//",
    backend="rpc://",
)

# ============================================
# 🎯 CONFIGURATION OPTIMISÉE MULTI-WORKERS
# ============================================
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Paris",
    enable_utc=True,
    imports=("tasks",),
    
    # ✅ Configuration pour multi-workers (IMPORTANT!)
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=4,  # ⬆️ Permet de précharger 4 tâches par worker
    result_expires=3600,
    task_ignore_result=False,
    
    # ✅ Retry configuration
    task_autoretry_for=(),
    task_retry_backoff=False,
    task_retry_backoff_max=0,
    task_retry_jitter=False,
    task_max_retries=0,
    
    # ✅ Rate limits plus souples pour parallélisme
    task_default_rate_limit="100/m",  # ⬆️ 100 tâches/minute au lieu de 10
    worker_disable_rate_limits=False,
    
    # ✅ Timeouts
    task_soft_time_limit=300,
    task_time_limit=360,
    
    # ✅ Priorités (pour gérer urgent vs standard)
    task_default_priority=5,
    task_inherit_parent_priority=True,
    
    broker_transport_options={
        "visibility_timeout": 3600,
        "confirm_publish": True,
        "priority_steps": [0, 3, 6, 9],  # 4 niveaux de priorité
    },
)

# ============================================
# 📋 CONFIGURATION DES QUEUES AVEC PRIORITÉS
# ============================================
celery.conf.task_queues = (
    # Queue URGENT : Vérifications manuelles/immédiates (priorité max)
    Queue('urgent', routing_key='urgent', priority=9),
    
    # Queue STANDARD : Vérifications auto et imports massifs (priorité normale)
    Queue('standard', routing_key='standard', priority=5),
    
    # Queue WEEKLY : Tâches hebdomadaires planifiées (priorité basse)
    Queue('weekly', routing_key='weekly', priority=1),
)

celery.conf.task_default_queue = 'standard'
celery.conf.task_default_exchange = 'tasks'
celery.conf.task_default_routing_key = 'standard'

# ✅ Routing automatique des tâches vers les bonnes queues
celery.conf.task_routes = {
    'tasks.check_single_site': {'queue': 'standard'},
    'tasks.check_all_user_sites': {'queue': 'standard'},
    'tasks.check_all_sites_weekly': {'queue': 'weekly'},
}

# ============================================
# ⏰ PLANIFICATEUR DE TÂCHES (BEAT)
# ============================================
celery.conf.beat_schedule = {
    "check-all-sites-weekly": {
        "task": "tasks.check_all_sites_weekly",
        "schedule": crontab(day_of_week="monday", hour=2, minute=0),
    },
}


def get_flask_app():
    """
    Crée et retourne l'instance Flask avec toute sa configuration.
    Cette fonction est appelée par les workers Celery.
    """
    from flask import Flask
    from flask_migrate import Migrate

    from database import db
    from routes.login_manager import login_manager
    
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dfsdfsdfdfsdfsdfsdfsdfsdfsdfsdffsd")
    
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_host = os.getenv("DB_HOST", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB")
    
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    )
    
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    
    return app


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


# 🔥 IMPORTANT : Créer flask_app pour les workers
flask_app = get_flask_app()
init_celery(flask_app)