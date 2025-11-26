from flask import Blueprint, jsonify, request
from sqlalchemy import func

from models import Tag, db
from services.utils_service import couleur_aleatoire_unique

tag_serv = Blueprint("tag_services", __name__)


@tag_serv.route("/add_tag", methods=["POST"])
def add_tag():
    data = request.get_json()
    valeur = data.get("valeur", "").strip().lower()

    if not valeur:
        return jsonify({"success": False, "error": "Valeur vide"}), 400

    existing = Tag.query.filter(func.lower(Tag.valeur) == valeur).first()
    if existing:
        return jsonify({"success": False, "error": "Ce tag existe déjà"}), 400

    try:
        nouvelle_couleur = couleur_aleatoire_unique()
        new_tag = Tag(valeur=valeur, couleur=nouvelle_couleur)
        db.session.add(new_tag)
        db.session.commit()

        # ✅ Vide le cache local SQLAlchemy (important)
        db.session.expire_all()

        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print("Erreur ajout tag :", e)
        return jsonify({"success": False, "error": str(e)}), 500


@tag_serv.route("/delete_tag", methods=["POST"])
def delete_tag():
    data = request.get_json()
    valeur = data.get("valeur", "").strip().lower()

    if not valeur:
        return jsonify({"success": False, "error": "Aucune valeur fournie"}), 400

    tag_to_delete = Tag.query.filter(func.lower(Tag.valeur) == valeur).first()

    if tag_to_delete:
        try:
            db.session.delete(tag_to_delete)
            db.session.commit()

            # ✅ Vide le cache après suppression aussi
            db.session.expire_all()

            return jsonify({"success": True})
        except Exception as e:
            db.session.rollback()
            print("Erreur suppression tag :", e)
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        return jsonify({"success": False, "error": "Tag non trouvé"}), 404


@tag_serv.route("/get_tags", methods=["GET"])
def get_tags():
    tags = Tag.query.order_by(Tag.valeur.asc()).all()
    return jsonify([{"valeur": t.valeur} for t in tags])
