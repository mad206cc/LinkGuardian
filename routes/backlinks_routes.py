# routes/backlinks_routes.py

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from models import Source, Tag, User, Website

backlinks_routes = Blueprint("backlinks_routes", __name__)


def get_filtered_query():
    """
    Construit la requête des backlinks avec tous les filtres :
    - multi-users
    - sources
    - multi-tags
    - texte (q)
    - follow/nofollow
    - indexation Google
    - tri
    """

    # ============================
    # BASE QUERY
    # ============================
    query = Website.query

    # ============================
    # 📌 1) FILTRE UTILISATEUR
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

    # ============================
    # 📌 2) FILTRE SOURCE (CHOIX UNIQUE)
    # ============================
    filter_source = request.args.get("source", "").strip()

    if filter_source and filter_source != "__all__":
        query = query.filter(
            func.lower(Website.source_plateforme) == filter_source.lower()
        )

    # ============================
    # 📌 3) FILTRE TAGS (MULTI-CHOIX)
    # ============================
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))

    # Normalisation du sélecteur ALL
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    if filter_tags != ["__all__"]:
        query = query.filter(func.lower(Website.tag).in_(filter_tags))

    # ============================
    # 📌 4) RECHERCHE TEXTUELLE
    # ============================
    q = request.args.get("q", "").strip()

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            Website.url.ilike(pattern) | Website.anchor_text.ilike(pattern)
        )

    # ============================
    # 📌 5) FOLLOW / NOFOLLOW
    # ============================
    follow = request.args.get("follow", "all")

    if follow == "true":
        query = query.filter(Website.link_follow_status == "follow")
    elif follow == "false":
        query = query.filter(
            (Website.link_follow_status != "follow")
            | (Website.link_follow_status.is_(None))
            | (Website.link_follow_status == "")
        )

    # ============================
    # 📌 6) INDEXATION GOOGLE
    # ============================
    indexed = request.args.get("indexed", "all")

    if indexed == "true":
        query = query.filter(Website.google_index_status == "Indexé !")
    elif indexed == "false":
        query = query.filter(Website.google_index_status != "Indexé !")

    # ============================
    # 📌 7) TRI
    # ============================
    order = request.args.get("order", "desc")

    query = query.order_by(Website.id.desc() if order == "desc" else Website.id.asc())

    return query


@backlinks_routes.route("/backlinks")
@login_required
def backlinks_list():
    """Page principale Backlinks (avec filtres, stats, pagination)."""

    # ============================
    # 1) REQUÊTE FILTRÉE
    # ============================
    query = get_filtered_query()

    # ============================
    # 2) PAGINATION
    # ============================
    page = request.args.get("page", 1, type=int)
    per_page = 10
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # ============================
    # 3) RECONSTRUCTION DES FILTRES (pour le front)
    # ============================
    # Users
    if current_user.role == "main_admin":
        filter_user_ids = request.args.getlist("user_id")
        if not filter_user_ids or "__all__" in filter_user_ids:
            filter_user_ids = ["__all__"]
        else:
            filter_user_ids = [uid for uid in filter_user_ids if uid.isdigit()]
            filter_user_ids = list(dict.fromkeys(filter_user_ids)) or ["__all__"]
    else:
        filter_user_ids = [str(current_user.id)]

    # Tags (multi)
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    # Sources (multi)
    filter_sources = list(dict.fromkeys(request.args.getlist("source")))
    if not filter_sources or filter_sources == ["__all__"]:
        filter_sources = ["__all__"]
    else:
        filter_sources = [t for t in filter_sources if t != "__all__"]

    # Follow / Indexed / Résultats
    filters = {
        "q": request.args.get("q", ""),
        "follow": request.args.get("follow", "all"),
        "indexed": request.args.get("indexed", "all"),
        "sort": request.args.get("sort", "created"),
        "order": request.args.get("order", "desc"),
        "tag": filter_tags,
        "source": filter_sources,
        "user_id": filter_user_ids,
    }

    # ============================
    # 4) CALCUL QUALITÉ
    # ============================
    for site in pagination.items:
        if site.page_trust and site.page_value:
            site.quality = round(site.page_trust * 0.6 + site.page_value * 0.4, 1)
        else:
            site.quality = 0

    # ============================
    # 5) STATS FILTRÉES
    # ============================
    stats_query = get_filtered_query().order_by(None)
    total = stats_query.count()

    if total > 0:
        follow_count = stats_query.filter(
            Website.link_follow_status == "follow"
        ).count()
        indexed_count = stats_query.filter(
            Website.google_index_status == "Indexé !"
        ).count()
        avg_value = (
            stats_query.with_entities(func.avg(Website.page_value)).scalar() or 0
        )
        avg_trust = (
            stats_query.with_entities(func.avg(Website.page_trust)).scalar() or 0
        )
        avg_quality = round(float(avg_trust) * 0.6 + float(avg_value) * 0.4, 1)
    else:
        follow_count = indexed_count = avg_value = avg_trust = avg_quality = 0

    stats = {
        "total": total,
        "follow": follow_count,
        "follow_percentage": f"{(follow_count / total * 100) if total else 0:.1f}",
        "indexed": indexed_count,
        "indexed_percentage": f"{(indexed_count / total * 100) if total else 0:.1f}",
        "avg_quality": f"{avg_quality:.1f}",
        "avg_value": f"{avg_value:.1f}",
        "avg_trust": f"{avg_trust:.1f}",
    }

    # ============================
    # 6) DONNÉES POUR LES DROPDOWNS
    # ============================
    tags = Tag.query.all()
    sources = Source.query.all()
    users = User.query.all() if current_user.role == "main_admin" else []

    # ============================
    # 7) URL BASE POUR HTMX PAGINATION
    # ============================
    pagination_base_url = url_for(
        "backlinks_routes.backlinks_table_partial",
        q=filters["q"],
        tag=filter_tags,
        source=filter_sources,
        user_id=filter_user_ids,
        follow=filters["follow"],
        indexed=filters["indexed"],
        sort=filters["sort"],
        order=filters["order"],
    )

    # ============================
    # 8) RENDER
    # ============================
    return render_template(
        "backlinks/list.html",
        backlinks=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages or 1,
        stats=stats,
        filters=filters,
        tags=tags,
        sources=sources,
        users=users,
        pagination_base_url=pagination_base_url,
    )


@backlinks_routes.route("/backlinks/partial/table")
@login_required
def backlinks_table_partial():
    """Partial HTMX – seulement le tableau (backlinks)."""

    # ============================
    # 1) Vérification HTMX
    # ============================
    if not request.headers.get("HX-Request"):
        page = request.args.get("page", 1, type=int)
        return redirect(url_for("backlinks_routes.backlinks_list", page=page))

    # ============================
    # 2) Requête filtrée
    # ============================
    query = get_filtered_query()

    # ============================
    # 3) Pagination
    # ============================
    page = request.args.get("page", 1, type=int)
    per_page = 10
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # ============================
    # 4) Calcul qualité des backlinks
    # ============================
    for site in pagination.items:
        if site.page_trust and site.page_value:
            site.quality = round(site.page_trust * 0.6 + site.page_value * 0.4, 1)
        else:
            site.quality = 0

    # ============================
    # 5) Reconstruction des filtres (pour la pagination HTMX)
    # ============================

    # TAGS (multi)
    filter_tags = list(dict.fromkeys(request.args.getlist("tag")))
    if not filter_tags or filter_tags == ["__all__"]:
        filter_tags = ["__all__"]
    else:
        filter_tags = [t for t in filter_tags if t != "__all__"]

    # SOURCES (multi)
    filter_sources = list(dict.fromkeys(request.args.getlist("source")))
    if not filter_sources or filter_sources == ["__all__"]:
        filter_sources = ["__all__"]
    else:
        filter_sources = [t for t in filter_sources if t != "__all__"]

    # USERS (multi)
    if current_user.role == "main_admin":
        filter_user_ids = request.args.getlist("user_id")
        if not filter_user_ids or "__all__" in filter_user_ids:
            filter_user_ids = ["__all__"]
        else:
            filter_user_ids = [uid for uid in filter_user_ids if uid.isdigit()]
            filter_user_ids = list(dict.fromkeys(filter_user_ids)) or ["__all__"]
    else:
        filter_user_ids = [str(current_user.id)]

    # follow / index / sort / order
    follow = request.args.get("follow", "all")
    indexed = request.args.get("indexed", "all")
    sort = request.args.get("sort", "created")
    order = request.args.get("order", "desc")

    # ============================
    # 6) Base URL pour HTMX pagination (TRÈS IMPORTANT)
    # ============================
    base_url = url_for(
        "backlinks_routes.backlinks_table_partial",
        q=request.args.get("q", ""),
        tag=filter_tags,  # LISTE
        source=filter_sources,  # LISTE
        user_id=filter_user_ids,  # LISTE
        follow=follow,
        indexed=indexed,
        sort=sort,
        order=order,
    )

    # ============================
    # 7) Render
    # ============================
    return render_template(
        "backlinks/_table.html",
        backlinks=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages or 1,
        pagination_base_url=base_url,
    )
