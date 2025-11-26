from datetime import datetime
from functools import wraps

import requests
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from database import db
from models import Configuration, User, UserAccess
from routes.auth_routes import is_strong_password

config_bp = Blueprint("config_routes", __name__)


# ============================================================
# 🔧 DÉCORATEUR ADMIN
# ============================================================
def admin_required(f):
    """Vérifie que l'utilisateur est admin OU main_admin"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in [
            "admin",
            "main_admin",
        ]:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


# ============================================================
# 🧩 PAGE GÉNÉRALE DE CONFIGURATION
# ============================================================
@config_bp.route("/configuration", methods=["GET", "POST"])
@login_required
def configuration():
    """Page principale de configuration (tous les onglets inclus : profil, partages, intégrations, etc.)"""
    if request.method == "POST":
        sms_enabled = request.form.get("sms_enabled") == "on"
        phone_number = request.form.get("phone_number")

        config = Configuration.query.first()
        if not config:
            config = Configuration()
            db.session.add(config)

        config.sms_enabled = sms_enabled
        config.phone_number = phone_number
        db.session.commit()
        flash("Configuration sauvegardée avec succès.")
        return redirect(url_for("config_routes.configuration"))

    # ==============================
    # 🧩 Données de base
    # ==============================
    config = Configuration.query.first()
    users = User.query.all()
    total_users = len(users)
    total_admins = len([u for u in users if u.role == "admin"])

    # ==============================
    # 👥 Données de partage
    # ==============================

    if current_user.role in ["admin", "main_admin"]:
        # 🔥 Admin & super admin → voient tout
        shares = (
            UserAccess.query.options(
                joinedload(UserAccess.owner), joinedload(UserAccess.grantee)
            )
            .order_by(UserAccess.created_at.desc())
            .all()
        )
    else:
        # 🔒 User normal → voit seulement les partages qui le concernent
        shares = (
            UserAccess.query.options(
                joinedload(UserAccess.owner), joinedload(UserAccess.grantee)
            )
            .filter(
                or_(
                    UserAccess.owner_id == current_user.id,
                    UserAccess.grantee_id == current_user.id,
                )
            )
            .order_by(UserAccess.created_at.desc())
            .all()
        )

    # ==============================
    # 🧭 Rendu global
    # ==============================
    return render_template(
        "settings/index.html",
        config=config,
        total_users=total_users,
        total_admins=total_admins,
        users=users,
        shares=shares,  # 👈 inclus maintenant dans le rendu principal
    )


# ============================================================
# 👑 ROUTE ADMIN /configuration/administrateur
# ============================================================
@config_bp.route("/configuration/administrateur?tab=admin")
@login_required
@admin_required
def admin():
    """Affiche la page de configuration avec l’onglet admin actif"""
    users = User.query.all()
    total_users = len(users)
    total_admins = len([u for u in users if u.role == "admin"])

    # On rend le même template que la page principale
    return render_template(
        "settings/index.html",
        users=users,
        total_users=total_users,
        total_admins=total_admins,
    )


@config_bp.route("/configuration/administrateur/user/<int:user_id>")
@login_required
@admin_required
def get_user(user_id):
    """API pour récupérer les données d'un utilisateur (pour le modal d'édition)"""
    user = User.query.get_or_404(user_id)

    return jsonify(
        {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.email,
            "email": user.email,
            "role": user.role,
        }
    )


@config_bp.route("/configuration/administrateur/user/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    """Ajouter un nouvel utilisateur"""
    try:
        # Récupérer les données du formulaire
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        username = request.form.get("email")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "user")

        # Vérifier si username existe
        if User.query.filter_by(username=username).first():
            flash(f"Le nom d'utilisateur '{username}' existe déjà.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Vérifier si email existe
        if User.query.filter_by(email=email).first():
            flash(f"L'adresse email '{email}' est déjà utilisée.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Vérification de la robustesse du mot de passe
        if not is_strong_password(password):
            flash(
                "Le mot de passe doit contenir au moins 8 caractères, une majuscule, une minuscule, un chiffre et un symbole.",
                "error",
            )
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Créer le nouvel utilisateur
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            role=role,
        )

        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash(
            f"L'utilisateur {first_name} {last_name} a été créé avec succès.", "success"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la création de l'utilisateur : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="admin"))


@config_bp.route(
    "/configuration/administrateur/user/<int:user_id>/edit", methods=["POST"]
)
@login_required
@admin_required
def edit_user(user_id):
    """Modifier un utilisateur existant"""
    try:
        user = User.query.get_or_404(user_id)

        # Récupérer les données du formulaire
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        username = request.form.get("username")
        email = request.form.get("email")
        role = request.form.get("role")

        # Vérifier si l'username existe déjà (sauf pour l'utilisateur actuel)
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != user_id:
            flash(f"Le nom d'utilisateur '{username}' existe déjà.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Vérifier si l'email existe déjà (sauf pour l'utilisateur actuel)
        existing_email = User.query.filter_by(email=email).first()
        if existing_email and existing_email.id != user_id:
            flash(f"L'adresse email '{email}' est déjà utilisée.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Empêcher un admin de se retirer ses propres droits admin
        if user_id == current_user.id and role != "admin":
            flash(
                "Vous ne pouvez pas retirer vos propres droits d'administrateur.",
                "error",
            )
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Mettre à jour les données
        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        user.email = email
        user.role = role

        db.session.commit()

        flash(
            f"L'utilisateur {first_name} {last_name} a été modifié avec succès.",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la modification de l'utilisateur : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="admin"))


@config_bp.route("/configuration/update-profile-picture", methods=["POST"])
@login_required
def update_profile_picture():
    file = request.files.get("profile_picture")

    if not file:
        flash("Aucune image sélectionnée.", "error")
        return redirect(url_for("config_routes.configuration", tab="account"))

    # Vérification du type de fichier
    if not file.mimetype.startswith("image/"):
        flash("Le fichier doit être une image.", "error")
        return redirect(url_for("config_routes.configuration", tab="account"))

    import os

    upload_folder = "static/uploads/avatars/"
    os.makedirs(upload_folder, exist_ok=True)

    # Nom unique : user_XX.png
    filename = f"user_{current_user.id}.png"
    filepath = os.path.join(upload_folder, filename)

    # Sauvegarde sur le disque
    file.save(filepath)

    # Mise à jour DB
    current_user.profile_picture = filename
    db.session.commit()

    flash("Photo mise à jour !", "success")
    return redirect(url_for("config_routes.configuration", tab="account"))


@config_bp.route(
    "/configuration/administrateur/user/<int:user_id>/change-password", methods=["POST"]
)
@login_required
@admin_required
def change_user_password(user_id):
    """Changer le mot de passe d'un utilisateur"""
    try:
        user = User.query.get_or_404(user_id)

        new_password = request.form.get("new_password")

        # Vérification présence
        if not new_password:
            flash("Le mot de passe est requis.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Vérification complexité
        if not is_strong_password(new_password):
            flash(
                "Le mot de passe doit contenir au minimum 8 caractères, "
                "une majuscule, une minuscule, un chiffre et un symbole.",
                "error",
            )
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # Mise à jour du mot de passe
        user.set_password(new_password)
        db.session.commit()

        flash(
            f"Le mot de passe de {user.first_name} {user.last_name} a été modifié avec succès.",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors du changement de mot de passe : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="admin"))


@config_bp.route(
    "/configuration/administrateur/user/<int:user_id>/delete", methods=["POST"]
)
@login_required
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)

        # Empêcher un admin de se supprimer lui-même
        if user_id == current_user.id:
            flash("Vous ne pouvez pas supprimer votre propre compte.", "error")
            return redirect(url_for("config_routes.configuration", tab="admin"))

        # 1️⃣ Supprimer tous les partages liés à cet utilisateur
        UserAccess.query.filter(
            (UserAccess.owner_id == user_id)
            | (UserAccess.grantee_id == user_id)
            | (UserAccess.granted_by == user_id)
        ).delete(synchronize_session=False)

        # 2️⃣ Supprimer l'utilisateur
        db.session.delete(user)
        db.session.commit()

        flash(
            f"L'utilisateur {user.first_name} {user.last_name} a été supprimé avec succès.",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la suppression de l'utilisateur : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="admin"))


@config_bp.route("/configuration/change-password", methods=["POST"])
@login_required
def change_own_password():
    """Permet à l'utilisateur connecté de changer son propre mot de passe"""
    try:
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        # Validation : vérifier que tous les champs sont remplis
        if not current_password or not new_password or not confirm_password:
            flash("Tous les champs sont requis.", "error")
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Verification : mots de passe identiques
        if new_password != confirm_password:
            flash(
                "Le nouveau mot de passe et la confirmation ne correspondent pas.",
                "error",
            )
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Vérification complexité
        if not is_strong_password(new_password):
            flash(
                "Le nouveau mot de passe doit contenir au minimum 8 caractères, "
                "une majuscule, une minuscule, un chiffre et un symbole.",
                "error",
            )
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Vérifier que le mot de passe actuel est correct
        if not current_user.check_password(current_password):
            flash("Le mot de passe actuel est incorrect.", "error")
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Empêcher l'utilisateur de réutiliser le même mot de passe
        if current_user.check_password(new_password):
            flash("Le nouveau mot de passe doit être différent de l'ancien.", "error")
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Changer le mot de passe
        current_user.set_password(new_password)
        db.session.commit()

        flash("Votre mot de passe a été modifié avec succès.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors du changement de mot de passe : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="account"))


@config_bp.route("/configuration/edit-information", methods=["POST"])
@login_required
def edit_own_information():
    """Permet à l'utilisateur connecté de modifier ses propres informations"""
    try:
        # Récupérer les données du formulaire
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")

        # Vérification des champs requis
        if not first_name or not last_name or not email:
            flash("Tous les champs sont requis.", "error")
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Vérifier si l'email est déjà utilisé par un autre utilisateur
        existing_email = User.query.filter_by(email=email).first()
        if existing_email and existing_email.id != current_user.id:
            flash("Cette adresse email est déjà utilisée par un autre compte.", "error")
            return redirect(url_for("config_routes.configuration", tab="account"))

        # Mettre à jour les informations
        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.email = email

        db.session.commit()

        flash("Vos informations ont été mises à jour avec succès.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la mise à jour de vos informations : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="account"))


# ============================================================
# 🔗 TESTER LA CLÉ BABBAR
# ============================================================
@config_bp.route("/configuration/integrations/test-babbar", methods=["POST"])
@login_required
def test_babbar_api():
    """Tester la validité de la clé API Babbar"""
    api_key = request.form.get("babbar_api_key")

    if not api_key:
        return jsonify({"success": False, "message": "Aucune clé API fournie."}), 400

    # Exemple d'URL à tester
    api_url = "https://www.babbar.tech/api/url/overview/main"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {"url": "https://www.example.com/"}

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            return jsonify({"success": True, "message": "Connexion réussie à Babbar."})
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"Erreur {response.status_code} : {response.text}",
                }
            )

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# 💾 SAUVEGARDER LA CLÉ BABBAR
# ============================================================
@config_bp.route("/configuration/integrations/save-babbar", methods=["POST"])
@login_required
def save_babbar_api_key():
    """Sauvegarde la clé API Babbar dans la base"""
    api_key = request.form.get("babbar_api_key")

    if not api_key:
        flash("Veuillez entrer une clé API valide.", "error")
        return redirect(url_for("config_routes.configuration", tab="integrations"))

    try:
        config = Configuration.query.first()
        # Valeurs par défaut si la table Configuration est vide
        if not config:
            config = Configuration(
                babbar_api_key="lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv",
                serpapi_key="2d616e924f3b0d90bdcecdae5de3ab32605022360f9598b9c6d25e5a0ed80db5",
                last_babbar_sync=None,
                last_serpapi_sync=None,
            )
            db.session.add(config)
            db.session.commit()

        config.babbar_api_key = api_key
        config.last_babbar_sync = datetime.now()

        db.session.commit()
        flash("Clé API Babbar enregistrée avec succès.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la sauvegarde de la clé API Babbar : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="integrations"))


# ============================================================
# 🔍 TESTER LA CLÉ SERPAPI
# ============================================================
@config_bp.route("/configuration/integrations/test-serpapi", methods=["POST"])
@login_required
def test_serpapi_api():
    """Tester la validité de la clé API SerpApi"""
    api_key = request.form.get("serpapi_key")

    if not api_key:
        return jsonify({"success": False, "message": "Aucune clé API fournie."}), 400

    # Exemple de requête simple à SerpApi
    test_url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": "site:example.com",
        "api_key": api_key,
    }

    try:
        response = requests.get(test_url, params=params, timeout=10)

        if response.status_code == 200:
            return jsonify({"success": True, "message": "Connexion réussie à SerpApi."})
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"Erreur {response.status_code} : {response.text}",
                }
            )

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# 💾 SAUVEGARDER LA CLÉ SERPAPI
# ============================================================
@config_bp.route("/configuration/integrations/save-serpapi", methods=["POST"])
@login_required
def save_serpapi_api_key():
    """Sauvegarde la clé API SerpApi dans la base"""
    api_key = request.form.get("serpapi_key")

    if not api_key:
        flash("Veuillez entrer une clé API valide.", "error")
        return redirect(url_for("config_routes.configuration", tab="integrations"))

    try:
        config = Configuration.query.first()
        if not config:
            config = Configuration()
            db.session.add(config)

        config.serpapi_key = api_key
        config.last_serpapi_sync = datetime.now()

        db.session.commit()
        flash("Clé API SerpApi enregistrée avec succès.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la sauvegarde de la clé API SerpApi : {str(e)}", "error")

    return redirect(url_for("config_routes.configuration", tab="integrations"))


# ============================================================
# 👥 GESTION DES DROITS DE PARTAGE ENTRE UTILISATEURS
# ============================================================


@config_bp.route("/configuration/partage/add", methods=["POST"])
@login_required
def add_share():
    """
    Ajoute un droit de partage :
    - Admin → peut définir n’importe quel owner_id et grantee_id
    - Utilisateur → ne peut partager que ses propres données
    """
    owner_id = request.form.get("owner_id")
    grantee_id = request.form.get("grantee_id")

    # Validation des champs
    if not owner_id or not grantee_id:
        flash("Veuillez sélectionner les deux utilisateurs.", "error")
        return redirect(url_for("config_routes.configuration", tab="sharing"))

    # Vérifier les droits
    if current_user.role not in ["admin", "main_admin"]:
        # Un utilisateur normal ne peut partager que ses propres données
        owner_id = current_user.id

    if int(owner_id) == int(grantee_id):
        flash("Un utilisateur ne peut pas se partager ses propres données.", "error")
        return redirect(url_for("config_routes.configuration", tab="sharing"))

    # Vérifier si ce partage existe déjà
    existing = UserAccess.query.filter_by(
        owner_id=owner_id, grantee_id=grantee_id
    ).first()
    if existing:
        flash("Ce partage existe déjà.", "info")
        return redirect(url_for("config_routes.configuration", tab="sharing"))

    # Créer le partage
    new_share = UserAccess(
        owner_id=owner_id, grantee_id=grantee_id, granted_by=current_user.id
    )
    db.session.add(new_share)
    db.session.commit()

    flash("Droit de partage ajouté avec succès ✅", "success")
    return redirect(url_for("config_routes.configuration", tab="sharing"))


@config_bp.route("/configuration/partage/delete/<int:share_id>", methods=["POST"])
@login_required
def delete_share(share_id):
    """
    Supprimer un droit de partage :
    - Super-admin (id=1) → peut tout supprimer
    - Admin → peut supprimer les partages des utilisateurs simples
    - Utilisateur → ne peut supprimer que ses propres partages
    """
    share = UserAccess.query.get_or_404(share_id)

    # Super-admin peut tout supprimer
    if current_user.role == "main_admin":
        pass  # Autorisé
    # Admin peut supprimer les partages des users simples
    elif current_user.role == "admin":
        owner = User.query.get(share.owner_id)
        if owner and owner.role == "admin" and owner.id != current_user.id:
            # Un admin ne peut pas supprimer le partage d'un autre admin
            abort(403)
    # Utilisateur simple ne peut supprimer que ses propres partages
    elif share.owner_id != current_user.id:
        abort(403)

    db.session.delete(share)
    db.session.commit()

    flash("Droit de partage supprimé ✅", "success")
    return redirect(url_for("config_routes.configuration", tab="sharing"))
