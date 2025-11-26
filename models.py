# Dans models.py
from datetime import datetime

from flask_login import (
    UserMixin,  # des fonctions interne à Flask pour la sécurisation des mots de passe (hasher les mots de passe)
)
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


class Website(db.Model):
    #    __table_args__ = (
    #        UniqueConstraint(
    #            "user_id",
    #            "url",
    #            "link_to_check",
    #            "anchor_text",
    #            "source_plateforme",
    #            name="uix_url_linktocheck",
    #        ),
    #    )

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(250), nullable=False)
    domains = db.Column(db.String(250), nullable=True)
    status_code = db.Column(db.Integer, nullable=True)
    tag = db.Column(db.String(50), nullable=True)
    source_plateforme = db.Column(db.String(100))
    link_to_check = db.Column(db.String(250), nullable=True)
    anchor_text = db.Column(db.String(250), nullable=True)
    link_status = db.Column(db.String(250), nullable=True)
    anchor_status = db.Column(db.String(250), nullable=True)
    first_checked = db.Column(db.DateTime, nullable=True)
    last_checked = db.Column(db.DateTime, nullable=True)

    # ✅ CORRECT : ForeignKey pointe vers user.id
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    page_value = db.Column(db.Integer)
    page_trust = db.Column(db.Integer)
    bas = db.Column(db.Integer)
    backlinks_external = db.Column(db.Integer)
    num_outlinks_ext = db.Column(db.Integer)
    link_follow_status = db.Column(db.String(50), nullable=True)
    google_index_status = db.Column(db.String(50))

    # ✅ Relation pour accéder facilement aux infos de l'utilisateur
    user = db.relationship("User", backref="websites", lazy=True)

    # ✅ BONUS : Property pour afficher prénom + nom
    @property
    def added_by(self):
        """Retourne le nom complet de l'utilisateur qui a ajouté le site"""
        if self.user:
            return f"{self.user.first_name} {self.user.last_name}"
        return "Inconnu"

    def __repr__(self):
        return f"<Website {self.url}>"


class WebsiteStats(db.Model):
    """Historique des KPIs calculés à un instant donné pour un utilisateur."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    total_backlinks = db.Column(db.Integer)
    total_domains = db.Column(db.Integer)
    follow_percentage = db.Column(db.Float)
    avg_quality = db.Column(db.Float)

    links_gained = db.Column(db.Integer)
    links_lost = db.Column(db.Integer)

    # Optionnel : tu peux aussi stocker les infos JSON
    raw_data = db.Column(db.JSON, nullable=True)

    user = db.relationship("User", backref="stats_history", lazy=True)

    def __repr__(self):
        return f"<WebsiteStats {self.user_id} {self.date.strftime('%Y-%m-%d')}>"


class TaskRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default="user")
    profile_picture = db.Column(
        db.String(255), nullable=True, default="default_avatar.png"
    )

    # Relations explicites
    shares_as_owner = db.relationship(
        "UserAccess",
        foreign_keys="[UserAccess.owner_id]",
        cascade="all, delete-orphan",
        back_populates="owner",
        overlaps="shared_with",
    )

    shares_as_grantee = db.relationship(
        "UserAccess",
        foreign_keys="[UserAccess.grantee_id]",
        cascade="all, delete-orphan",
        back_populates="grantee",
        overlaps="access_to",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"


class UserAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    grantee_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    granted_by = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relations explicites + suppression du backref
    owner = db.relationship(
        "User",
        foreign_keys=[owner_id],
        back_populates="shares_as_owner",
        overlaps="shared_with",
    )

    grantee = db.relationship(
        "User",
        foreign_keys=[grantee_id],
        back_populates="shares_as_grantee",
        overlaps="access_to",
    )

    admin = db.relationship("User", foreign_keys=[granted_by])

    __table_args__ = (
        UniqueConstraint("owner_id", "grantee_id", name="uix_owner_grantee"),
    )

    def __repr__(self):
        return f"<UserAccess owner={self.owner_id} → grantee={self.grantee_id}>"


# Nouvelle classe pour les tags
class Tag(db.Model):
    """Classe permettant de gérer les sources des plateformes (ex : Facebook, Twitter, LinkedIn, etc.),
    en principe catégoriser les sites selon leur source.
    Et une couleur d'étiquette y est associé.
    """

    id = db.Column(db.Integer, primary_key=True)
    valeur = db.Column(db.String(50), unique=True, nullable=False)  # max 50 caractères
    couleur = db.Column(
        db.String(7), nullable=True
    )  # Couleur hexadécimale (ex: #FF5733)

    def __repr__(self):
        """Fonction qui permet d'afficher facilement les tags dans la console et le terminal.

        Returns:
            str: le nom du tag en toute lettre
        """

        return f"<Tag {self.valeur}>"


# Nouvelle classe pour les sources
class Source(db.Model):
    """Classe pour la gestion des sources - des fournisseurs de netlinkings."""

    __tablename__ = "source"  # Nom de la table

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(255), unique=True, nullable=False)  # Nom de la source

    def __repr__(self):
        """Affichage facile des sources dans la console et le terminal.

        Returns:
            str: Nom de la source
        """

        return f"<Source {self.nom}>"


class Configuration(db.Model):
    """Cette classe permet de gérer des options globales, comme l’activation des notifications
    SMS et le numéro associé, pour personnaliser le comportement de l’application.
    """

    id = db.Column(db.Integer, primary_key=True)
    sms_enabled = db.Column(db.Boolean, default=False)
    phone_number = db.Column(db.String(20), nullable=True)
    babbar_api_key = db.Column(db.String(255), nullable=True)
    serpapi_key = db.Column(db.String(255), nullable=True)
    last_babbar_sync = db.Column(db.DateTime, nullable=True)
    last_serpapi_sync = db.Column(db.DateTime, nullable=True)
