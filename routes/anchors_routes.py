from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from database import db
from models import Source, Tag, User, Website

anchors_routes = Blueprint("anchors_routes", __name__)


# --------------------------------------------------------
#  UTILITAIRES DE FILTRES
# --------------------------------------------------------
def get_filtered_anchors_query():
    query = (
        db.session.query(
            Website.anchor_text, func.count(Website.anchor_text).label("count")
        )
        .filter(Website.anchor_text.isnot(None), Website.anchor_text != "")
        .group_by(Website.anchor_text)
    )

    # ============================
    # 📌  FILTRE UTILISATEUR
    # ============================
    filter_user_ids = request.args.getlist("user_id")

    if current_user.role == "main_admin":
        # EX: ["3","8"]
        if filter_user_ids and "__all__" not in filter_user_ids:
            valid_ids = []
            for uid in filter_user_ids:
                try:
                    valid_ids.append(int(uid))
                except ValueError:
                    pass

            if valid_ids:
                query = query.filter(Website.user_id.in_(valid_ids))
        # sinon "__all__" → aucun filtre user
    else:
        # utilisateur normal : accès limité à ses propres sites
        query = query.filter(Website.user_id == current_user.id)

    # ========== TAGS ==========
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))

    # Normalisation du sélecteur ALL
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    if filter_tags != ["__all__"]:
        query = query.filter(func.lower(Website.tag).in_(filter_tags))

    # ========== SOURCES ==========
    filter_source = request.args.get("source", "").strip()

    if filter_source and filter_source != "__all__":
        query = query.filter(
            func.lower(Website.source_plateforme) == filter_source.lower()
        )

    # ========== AUTRES ==========
    anchor_type = request.args.get("type", "all")
    sort = request.args.get("sort", "count")
    order = request.args.get("order", "desc")

    q = request.args.get("q", "").strip()
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            Website.url.ilike(pattern) | Website.anchor_text.ilike(pattern)
        )

    return query, anchor_type, sort, order


def classify_anchor_type(text):
    """Classifie une ancre selon son type."""
    text_lower = text.lower()

    if "http" in text_lower:
        return "naked_url"
    if any(k in text_lower for k in ["marque", "officiel", "nom"]):
        return "branded"
    if any(k in text_lower for k in ["ici", "plus", "page", "voir", "cliquez"]):
        return "generic"
    if len(text_lower.split()) == 1:
        return "exact_match"
    return "partial_match"


def process_anchors(rows, total_occurrences, anchor_type_filter):
    """Transforme les lignes SQL en objets ancres avec ratio, type, etc."""
    anchors = []

    for row in rows:
        text = row.anchor_text.strip()
        count = row.count
        type_ = classify_anchor_type(text)
        ratio = round((count / total_occurrences) * 100, 1) if total_occurrences else 0

        # Filtre type
        if anchor_type_filter != "all" and type_ != anchor_type_filter:
            continue

        anchors.append(
            {
                "text": text,
                "count": count,
                "ratio": ratio,
                "length": len(text),
                "type": type_,
                "trend": 0,
                "over_optimized": ratio > 15,
            }
        )

    return anchors


# --------------------------------------------------------
#  ROUTE PRINCIPALE (PAGE COMPLÈTE)
# --------------------------------------------------------
@anchors_routes.route("/anchors")
@login_required
def anchors_list():
    # 🔎 Obtenir la requête filtrée
    query, anchor_type_filter, sort, order = get_filtered_anchors_query()

    # 📌 On récupère TOUTES les ancres filtrées
    rows = query.all()

    # ---------- USER ---------------
    if current_user.role == "main_admin":
        filter_user_ids = request.args.getlist("user_id")
        if not filter_user_ids or "__all__" in filter_user_ids:
            filter_user_ids = ["__all__"]
        else:
            filter_user_ids = [uid for uid in filter_user_ids if uid.isdigit()]
            filter_user_ids = list(dict.fromkeys(filter_user_ids)) or ["__all__"]
    else:
        filter_user_ids = [str(current_user.id)]

    # ---------- TAG ---------------
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    # ---------- SOURCE ---------------
    filter_sources = list(dict.fromkeys(request.args.getlist("source")))
    if not filter_sources or filter_sources == ["__all__"]:
        filter_sources = ["__all__"]
    else:
        filter_sources = [t for t in filter_sources if t != "__all__"]

    if not rows:
        return render_template(
            "anchors/list.html",
            anchors=[],
            current_page=1,
            total_pages=1,
            stats={},
            over_optimized_anchors=[],
            pie_data={},
            top_data={},
            filters={
                "q": "",
                "type": "all",
                "sort": "count",
                "order": "desc",
            },
        )

    # Calcul occurrences totales pour les ratios
    total_occurrences = sum(r.count for r in rows)

    # Construire la liste d’ancres
    anchors = process_anchors(rows, total_occurrences, anchor_type_filter)

    # --------------------------------------------------------
    # TRI
    # --------------------------------------------------------
    sort_map = {
        "count": lambda a: a["count"],
        "ratio": lambda a: a["ratio"],
        "length": lambda a: a["length"],
        "text": lambda a: a["text"].lower(),
    }
    anchors.sort(key=sort_map.get(sort, sort_map["count"]), reverse=(order == "desc"))

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------
    page = request.args.get("page", 1, type=int)
    per_page = 10
    total_pages = (len(anchors) + per_page - 1) // per_page

    start = (page - 1) * per_page
    paginated = anchors[start : start + per_page]

    # --------------------------------------------------------
    # STATS GLOBALES
    # --------------------------------------------------------
    stats = {
        "total_anchors": len(anchors),
        "total_occurrences": total_occurrences,
        "branded_percentage": round(
            sum(1 for a in anchors if a["type"] == "branded") / len(anchors) * 100, 1
        ),
        "exact_match_percentage": round(
            sum(1 for a in anchors if a["type"] == "exact_match") / len(anchors) * 100,
            1,
        ),
        "generic_percentage": round(
            sum(1 for a in anchors if a["type"] == "generic") / len(anchors) * 100, 1
        ),
        "over_optimized_count": sum(1 for a in anchors if a["over_optimized"]),
    }

    # --------------------------------------------------------
    # GRAPHIQUES
    # --------------------------------------------------------
    pie_data = {
        "labels": ["Marque", "Exacte", "Partielle", "Génériques", "URLs nues"],
        "values": [
            sum(1 for a in anchors if a["type"] == "branded"),
            sum(1 for a in anchors if a["type"] == "exact_match"),
            sum(1 for a in anchors if a["type"] == "partial_match"),
            sum(1 for a in anchors if a["type"] == "generic"),
            sum(1 for a in anchors if a["type"] == "naked_url"),
        ],
        "colors": ["#22c55e", "#38bdf8", "#f59e0b", "#8b5cf6", "#6b7280"],
    }

    # Top 15 pour le graphe barres
    def wrap(text, max_length=34):
        words = text.split()
        out, line = [], []
        length = 0
        for w in words:
            if length + len(w) <= max_length:
                line.append(w)
                length += len(w) + 1
            else:
                out.append(" ".join(line))
                line = [w]
                length = len(w)
        if line:
            out.append(" ".join(line))
        return "<br>".join(out)

    top_sorted = anchors[:10]
    top_data = {
        "labels": [wrap(a["text"]) for a in top_sorted],
        "values": [a["count"] for a in top_sorted],
        "colors": ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6"] * 3,
    }

    filters = {
        "q": request.args.get("q", ""),
        "type": anchor_type_filter,
        "tag": filter_tags,
        "source": filter_sources,
        "user_id": filter_user_ids,
        "sort": sort,
        "order": order,
    }

    tags = Tag.query.all()
    sources = Source.query.all()
    users = User.query.all() if current_user.role == "main_admin" else []

    pagination_base_url = url_for(
        "anchors_routes.anchors_table_partial",
        q=request.args.get("q", ""),
        tag=filter_tags,
        source=filter_sources,
        user_id=filter_user_ids,
        sort=request.args.get("sort", "created"),
        order=request.args.get("order", "desc"),
    )

    return render_template(
        "anchors/list.html",
        anchors=paginated,
        current_page=page,
        total_pages=total_pages,
        stats=stats,
        over_optimized_anchors=[a for a in anchors if a["over_optimized"]],
        pie_data=pie_data,
        top_data=top_data,
        filters=filters,
        tags=tags,
        sources=sources,
        users=users,
        pagination_base_url=pagination_base_url,
    )


# --------------------------------------------------------
#  PARTIAL HTMX - TABLE
# --------------------------------------------------------
@anchors_routes.route("/anchors/partial/table")
@login_required
def anchors_table_partial():
    # Si ce n’est pas HTMX → redirection classique
    if not request.headers.get("HX-Request"):
        page = request.args.get("page", 1, type=int)
        return redirect(url_for("anchors_routes.anchors_list", page=page))

    # Même logique que la page complète
    query, anchor_type_filter, sort, order = get_filtered_anchors_query()

    rows = query.all()
    if not rows:
        return render_template(
            "anchors/_anchors_table.html", anchors=[], current_page=1, total_pages=1
        )

    total_occurrences = sum(r.count for r in rows)
    anchors = process_anchors(rows, total_occurrences, anchor_type_filter)

    # Tri uniforme
    sort_map = {
        "count": lambda a: a["count"],
        "ratio": lambda a: a["ratio"],
        "length": lambda a: a["length"],
        "text": lambda a: a["text"].lower(),
    }
    anchors.sort(key=sort_map.get(sort, sort_map["count"]), reverse=(order == "desc"))

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 10
    total_pages = (len(anchors) + per_page - 1) // per_page

    start = (page - 1) * per_page
    paginated = anchors[start : start + per_page]

    # ---------- USER ---------------
    if current_user.role == "main_admin":
        filter_user_ids = request.args.getlist("user_id")
        if not filter_user_ids or "__all__" in filter_user_ids:
            filter_user_ids = ["__all__"]
        else:
            filter_user_ids = [uid for uid in filter_user_ids if uid.isdigit()]
            filter_user_ids = list(dict.fromkeys(filter_user_ids)) or ["__all__"]
    else:
        filter_user_ids = [str(current_user.id)]

    # ---------- TAG ---------------
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    # ---------- SOURCE ---------------
    filter_sources = list(dict.fromkeys(request.args.getlist("source")))
    if not filter_sources or filter_sources == ["__all__"]:
        filter_sources = ["__all__"]
    else:
        filter_sources = [t for t in filter_sources if t != "__all__"]

    base_url = url_for(
        "anchors_routes.anchors_table_partial",
        q=request.args.get("q", ""),
        tag=filter_tags,
        source=filter_sources,
        user_id=filter_user_ids,
        sort=request.args.get("sort", "created"),
        order=request.args.get("order", "desc"),
    )

    return render_template(
        "anchors/_anchors_table.html",
        anchors=paginated,
        current_page=page,
        total_pages=total_pages,
        pagination_base_url=base_url,
    )
