# ===============================
# 📦 Librairies & dépendances Flask
# ===============================
from asyncio import Semaphore

from aiohttp import ClientTimeout
from flask import Flask
from flask_executor import Executor
from flask_login import current_user
from flask_migrate import Migrate

# ===============================
# ⚙️ Import interne - Base et Celery
# ===============================
from database import db

# ===============================
# 📚 Imports modèles et vues admin
# ===============================
from models import (
    User,  # Importé ici, après le login_manager
)

# ===============================
# 🧩 Imports des Blueprints
# ===============================
from routes.anchors_routes import anchors_routes
from routes.auth_routes import authentification
from routes.backlinks_routes import backlinks_routes
from routes.config_routes import config_bp
from routes.domains_routes import domains_routes
from routes.login_manager import login_manager  # ⚠️ Doit venir avant Admin
from routes.main_routes import main_routes
from routes.site_routes import sites_routes
from routes.source_routes import source_routes
from services.tag_services import tag_serv
from services.utils_service import tag_color

# ===============================
# ⚙️ Constantes globales
# ===============================
SECONDS_BETWEEN_REQUESTS = 150
SEMAPHORE_BABBAR = Semaphore(10)
MAX_CONCURRENT_REQUESTS = 10
SEMAPHORE_YOURTEXTGURU = Semaphore(2)
request_counter = 0
AIOHTTP_TIMEOUT = ClientTimeout(total=30)

# ===============================
# 🚀 Création de l'application Flask
# ===============================
app = Flask(__name__)
app.secret_key = "dfsdfsdfdfsdfsdfsdfsdfsdfsdfsdffsd"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"

# ===============================
# 🧱 Initialisation des extensions
# ===============================
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)  # ⚠️ Obligatoire avant Admin
executor = Executor(app)

# ===============================
# 🔐 Configuration Flask-Login
# ===============================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


# ===============================
# 🧩 Filtres et Blueprints
# ===============================
app.add_template_filter(tag_color, "tag_color")

app.register_blueprint(authentification)
app.register_blueprint(config_bp)
app.register_blueprint(main_routes)
app.register_blueprint(sites_routes)
app.register_blueprint(source_routes)
app.register_blueprint(backlinks_routes)
app.register_blueprint(anchors_routes)
app.register_blueprint(domains_routes)
app.register_blueprint(tag_serv)

print("\n=== ROUTES DISPONIBLES ===")
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint}: {rule.rule}")
print("========================\n")


# ===============================
# 📊 Variables globales pour templates
# ===============================
@app.context_processor
def inject_global_stats():
    """Injecte des statistiques globales dans tous les templates"""
    if current_user.is_authenticated:
        from urllib.parse import urlparse

        from sqlalchemy import func

        from models import Website

        # Nombre total de backlinks
        total_backlinks = Website.query.filter_by(user_id=current_user.id).count()

        # Nombre d'ancres uniques
        total_unique_anchors = (
            db.session.query(func.count(func.distinct(Website.anchor_text)))
            .filter(
                Website.user_id == current_user.id,
                Website.anchor_text.isnot(None),
                Website.anchor_text != "",
            )
            .scalar()
            or 0
        )

        # Nombre de domaines uniques
        sites = (
            Website.query.filter_by(user_id=current_user.id)
            .with_entities(Website.url)
            .all()
        )
        unique_domains = len(
            set(
                urlparse(site.url).netloc.replace("www.", "")
                for site in sites
                if site.url
            )
        )

        return dict(
            total_backlinks=total_backlinks,
            total_unique_anchors=total_unique_anchors,
            total_unique_domains=unique_domains,
        )

    return dict(total_backlinks=0, total_unique_anchors=0, total_unique_domains=0)


# ===============================
# 🏁 Lancement de l'application
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
