from datetime import datetime, timedelta
from urllib.parse import urlparse

# routes/dashboard_routes.py
from flask import Blueprint, render_template, request

# from streamlit import user
from flask_login import current_user, login_required
from sqlalchemy import func

from models import Source, Tag, User, Website, WebsiteStats

# Création du Blueprint
main_routes = Blueprint("main_routes", __name__)


def apply_filters(query, filter_tag=None, filter_source=None):
    if filter_tag:
        query = query.filter(func.lower(Website.tag) == filter_tag.lower())

    if filter_source:
        query = query.filter(
            func.lower(Website.source_plateforme) == filter_source.lower()
        )

    return query


def apply_multi_filters(query, tags=None, sources=None, user_ids=None):
    """
    Applique les filtres multiples : tags, sources, users
    """

    # ---- Multi utilisateurs (admin / main_admin uniquement) ----
    if user_ids:
        clean_ids = [int(uid) for uid in user_ids if str(uid).isdigit()]
        if clean_ids:
            query = query.filter(Website.user_id.in_(clean_ids))

    # ---- Multi TAGS ----
    if tags:
        clean_tags = [t.lower().strip() for t in tags if t.strip()]
        if clean_tags:
            query = query.filter(func.lower(Website.tag).in_(clean_tags))

    # ---- Multi SOURCES ----
    if sources:
        clean_src = [s.lower().strip() for s in sources if s.strip()]
        if clean_src:
            query = query.filter(func.lower(Website.source_plateforme).in_(clean_src))

    return query


def get_date_range(range_param="1m"):
    """Calcule la plage de dates selon (1m, 3m, 6m, 12m)"""
    now = datetime.now()

    if range_param == "3m":
        days = 90
        label = "3 derniers mois"
    elif range_param == "6m":
        days = 180
        label = "6 derniers mois"
    elif range_param == "12m":
        days = 365
        label = "12 derniers mois"
    else:  # par défaut : 1 mois
        days = 30
        label = "Dernier mois"

    start_date = now - timedelta(days=days)
    return start_date, now, days, label


def calculate_total_backlinks(user_ids, filter_tags=None, filter_sources=None):
    query = Website.query.filter(Website.user_id.in_(user_ids))
    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    return query.count()


def calculate_backlinks_added(
    user_ids, start_date, filter_tags=None, filter_sources=None
):
    query = Website.query.filter(
        Website.user_id.in_(user_ids), Website.first_checked >= start_date
    )

    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    return query.count()


def calculate_total_domains(user_ids, filter_tags=None, filter_sources=None):
    query = Website.query.with_entities(Website.domains).filter(
        Website.user_id.in_(user_ids)
    )

    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    return query.distinct().count()


def calculate_domains_added(
    user_ids, start_date, filter_tags=None, filter_sources=None
):
    query = Website.query.with_entities(Website.domains).filter(
        Website.user_id.in_(user_ids), Website.first_checked >= start_date
    )

    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    domains = {d for (d,) in query.all() if d}
    return len(domains)


def calculate_total_urls(user_ids, filter_tags=None, filter_sources=None):
    query = Website.query.with_entities(Website.link_to_check).filter(
        Website.user_id.in_(user_ids)
    )

    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    return query.distinct().count()


def calculate_urls_added(user_ids, start_date, filter_tags=None, filter_sources=None):
    query = Website.query.with_entities(Website.link_to_check).filter(
        Website.user_id.in_(user_ids), Website.first_checked >= start_date
    )

    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    return query.distinct().count()


def calculate_follow_percentage(user_ids, filter_tags=None, filter_sources=None):
    # Toujours faire une liste d'IDs
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    # -------- TOTAL ==========
    total_q = Website.query.filter(Website.user_id.in_(user_ids))
    total_q = apply_multi_filters(
        total_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    total = total_q.count()

    if total == 0:
        return 0.0

    # -------- FOLLOW ==========
    follow_q = Website.query.filter(
        Website.user_id.in_(user_ids), Website.link_follow_status == "follow"
    )
    follow_q = apply_multi_filters(
        follow_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    follow = follow_q.count()

    return round((follow / total) * 100, 1)


def calculate_follow_percentage_change(
    user_ids, start_date, filter_tags=None, filter_sources=None
):
    # Toujours liste d'IDs
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    # ---- Pourcentage ACTUEL ----
    current_percentage = calculate_follow_percentage(
        user_ids, filter_tags, filter_sources
    )

    # ---- TOTAL AVANT période ----
    total_before_q = Website.query.filter(
        Website.user_id.in_(user_ids), Website.first_checked < start_date
    )
    total_before_q = apply_multi_filters(
        total_before_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    total_before = total_before_q.count()

    if total_before == 0:
        return 0.0

    # ---- FOLLOW AVANT période ----
    follow_before_q = Website.query.filter(
        Website.user_id.in_(user_ids),
        Website.first_checked < start_date,
        Website.link_follow_status == "follow",
    )
    follow_before_q = apply_multi_filters(
        follow_before_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )
    follow_before = follow_before_q.count()

    percentage_before = round((follow_before / total_before) * 100, 1)

    # ---- DIFFÉRENCE ----
    return round(current_percentage - percentage_before, 1)


def calculate_average_quality(user_ids, filter_tags=None, filter_sources=None):
    # Toujours convertir en liste
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    q = Website.query.filter(
        Website.user_id.in_(user_ids),
        Website.page_trust.isnot(None),
        Website.page_value.isnot(None),
    )

    q = apply_multi_filters(
        q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    sites = q.all()

    if not sites:
        return 0

    total_quality = sum((s.page_trust * 0.6 + s.page_value * 0.4) for s in sites)
    return round(total_quality / len(sites), 1)


def calculate_quality_change(
    user_ids, start_date, filter_tags=None, filter_sources=None
):
    # Toujours convertir en liste
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    # ---- QUALITÉ ACTUELLE ----
    current_quality = calculate_average_quality(user_ids, filter_tags, filter_sources)

    # ---- QUALITÉ AVANT LA PÉRIODE ----
    q = Website.query.filter(
        Website.user_id.in_(user_ids),
        Website.first_checked < start_date,
        Website.page_trust.isnot(None),
        Website.page_value.isnot(None),
    )

    q = apply_multi_filters(
        q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    sites_before = q.all()

    if not sites_before:
        return 0

    total_quality = sum((s.page_trust * 0.6 + s.page_value * 0.4) for s in sites_before)
    avg_quality_before = total_quality / len(sites_before)

    return round(current_quality - avg_quality_before, 1)


def get_evolution_data(
    user_ids, start_date, days, filter_tags=None, filter_sources=None
):
    """
    Génère l'évolution des backlinks et domaines sur une période,
    compatible multi-utilisateurs, multi-tags, multi-sources.
    """

    # ⚠ Toujours convertir en liste
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    intervals = []
    backlinks_counts = []
    domains_counts = []

    # diviser la période en 10 segments
    interval_days = days / 10

    for i in range(11):
        date = start_date + timedelta(days=interval_days * i)
        intervals.append(date.strftime("%Y-%m-%d"))

        # --------------------------------------
        # 📌 Backlinks cumulés jusqu'à cette date
        # --------------------------------------
        q = Website.query.filter(
            Website.user_id.in_(user_ids), Website.first_checked <= date
        )

        q = apply_multi_filters(
            q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
        )

        backlinks_counts.append(q.count())

        # --------------------------------------
        # 📌 Domaines uniques jusqu'à cette date
        # --------------------------------------
        q_dom = Website.query.filter(
            Website.user_id.in_(user_ids), Website.first_checked <= date
        )

        q_dom = apply_multi_filters(
            q_dom, tags=filter_tags, sources=filter_sources, user_ids=user_ids
        )

        domains = {
            urlparse(s.url).netloc.replace("www.", "") for s in q_dom.all() if s.url
        }

        domains_counts.append(len(domains))

    return [
        {"name": "Backlinks", "x": intervals, "y": backlinks_counts},
        {"name": "Domaines", "x": intervals, "y": domains_counts},
    ]


def get_follow_distribution(user_ids, filter_tags=None, filter_sources=None):
    """
    Retourne la distribution Follow / NoFollow,
    compatible multi-users, multi-tags, multi-sources.
    """

    # Toujours convertir en liste propre
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    # ---- TOTAL ----
    q_total = Website.query.filter(Website.user_id.in_(user_ids))

    q_total = apply_multi_filters(
        q_total, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    total = q_total.count()

    # ---- FOLLOW ----
    q_follow = Website.query.filter(
        Website.user_id.in_(user_ids), Website.link_follow_status == "follow"
    )

    q_follow = apply_multi_filters(
        q_follow, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    follow = q_follow.count()

    return {
        "labels": ["Follow", "NoFollow"],
        "values": [follow, total - follow],
        "colors": ["#22c55e", "#f59e0b"],
    }


def get_http_status_distribution(user_ids, filter_tags=None, filter_sources=None):
    """Génère la répartition des statuts HTTP compatible multi-users et multi-filtres"""

    # Toujours convertir en liste propre
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    status_counts = {}

    # ---- Construire la query de base ----
    query = Website.query.filter(Website.user_id.in_(user_ids))

    # ---- Appliquer tous les filtres multiples ----
    query = apply_multi_filters(
        query, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    # ---- Exécuter la query après filtres ----
    sites = query.all()

    for site in sites:
        status = site.status_code or "Inconnu"
        status_str = str(status)

        # Normalisation des groupes HTTP
        if status_str.startswith("2"):
            key = "200"
        elif status_str.startswith("301"):
            key = "301"
        elif status_str.startswith("302"):
            key = "302"
        elif status_str.startswith("4"):
            key = "404"
        elif status_str.startswith("5"):
            key = "500"
        else:
            key = "Autres"

        status_counts[key] = status_counts.get(key, 0) + 1

    labels = ["200", "301", "302", "404", "500", "Autres"]
    values = [status_counts.get(label, 0) for label in labels]
    colors = ["#22c55e", "#f59e0b", "#f59e0b", "#ef4444", "#ef4444", "#6b7280"]

    return {"labels": labels, "values": values, "colors": colors}


def get_top_anchors(user_ids, limit=10, filter_tags=None, filter_sources=None):
    """Top ancres (multi utilisateurs + multi filtres)"""

    # user_ids peut être int, liste, ou vide → on normalise
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    q = Website.query.filter(
        Website.user_id.in_(user_ids),
        Website.anchor_text.isnot(None),
        Website.anchor_text != "",
    )

    # Appliquer tags + sources + utilisateurs
    q = apply_multi_filters(
        q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    anchors = (
        q.with_entities(
            Website.anchor_text, func.count(Website.anchor_text).label("count")
        )
        .group_by(Website.anchor_text)
        .order_by(func.count(Website.anchor_text).desc())
        .limit(limit)
        .all()
    )

    # --- Mise en forme du texte pour l'affichage ---
    def wrap_text(text, max_length=35):
        if not text:
            return text
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) <= max_length:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)
        if current_line:
            lines.append(" ".join(current_line))

        return "<br>".join(lines)

    labels = [wrap_text(a.anchor_text) for a in anchors]
    values = [a.count for a in anchors]
    colors = [
        "#38bdf8",
        "#22c55e",
        "#f59e0b",
        "#ef4444",
        "#8b5cf6",
        "#06b6d4",
        "#84cc16",
        "#f97316",
        "#ec4899",
        "#64748b",
    ]

    return {"labels": labels, "values": values, "colors": colors[: len(labels)]}


def get_pv_pt_scatter(
    user_ids, start_date, end_date, limit=50, filter_tags=None, filter_sources=None
):
    """Scatter PV/PT (multi utilisateurs + multi filtres)"""

    if isinstance(user_ids, int):
        user_ids = [user_ids]

    q = Website.query.filter(
        Website.user_id.in_(user_ids),
        Website.page_value.isnot(None),
        Website.page_trust.isnot(None),
        Website.last_checked >= start_date,
        Website.last_checked <= end_date,
    )

    q = apply_multi_filters(
        q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
    )

    sites = (
        q.order_by((Website.page_value + Website.page_trust).desc()).limit(limit).all()
    )

    x_values = [site.page_value for site in sites]
    y_values = [site.page_trust for site in sites]
    labels = [urlparse(site.url).netloc for site in sites]
    sizes = [int(site.backlinks_external or 5) for site in sites]

    return {"x": x_values, "y": y_values, "labels": labels, "sizes": sizes}


def calculate_links_diff_period(
    user_ids, period="1m", filter_tags=None, filter_sources=None
):
    """
    Calcule les liens gagnés/perdus sur une période.

    ● Mode filtré (tags / sources / multi-users) → calcul direct Website
    ● Mode non filtré → WebsiteStats (rapide)
    """

    # Normalisation user_ids
    if isinstance(user_ids, int):
        user_ids = [user_ids]

    # Déterminer la durée
    if period == "12m":
        days = 365
    elif period == "6m":
        days = 180
    elif period == "3m":
        days = 90
    else:
        days = 30

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # ───────────────────────────────────────────────
    # 🔥 MODE FILTRÉ : tags / sources / multi-users
    # ───────────────────────────────────────────────
    filters_active = filter_tags or filter_sources or len(user_ids) > 1

    if filters_active:
        # Avant la période
        previous_q = Website.query.filter(
            Website.user_id.in_(user_ids), Website.first_checked < start_date
        )
        previous_q = apply_multi_filters(
            previous_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
        )
        previous_total = previous_q.count()

        # Actuellement
        current_q = Website.query.filter(
            Website.user_id.in_(user_ids), Website.first_checked <= end_date
        )
        current_q = apply_multi_filters(
            current_q, tags=filter_tags, sources=filter_sources, user_ids=user_ids
        )
        current_total = current_q.count()

        diff = current_total - previous_total
        gained = diff if diff > 0 else 0
        lost = abs(diff) if diff < 0 else 0

        return {
            "period": period,
            "lost": lost,
            "gained": gained,
            "previous_total": previous_total,
            "current_total": current_total,
            "date_start": start_date.strftime("%Y-%m-%d"),
            "date_end": end_date.strftime("%Y-%m-%d"),
            "filtered": True,
        }

    # ───────────────────────────────────────────────
    # 🚀 MODE NON FILTRÉ → WebsiteStats
    # (uniquement valable si un seul user)
    # ───────────────────────────────────────────────
    user_id = user_ids[0]

    latest = (
        WebsiteStats.query.filter(
            WebsiteStats.user_id == user_id, WebsiteStats.date <= end_date
        )
        .order_by(WebsiteStats.date.desc())
        .first()
    )

    previous = (
        WebsiteStats.query.filter(
            WebsiteStats.user_id == user_id, WebsiteStats.date <= start_date
        )
        .order_by(WebsiteStats.date.desc())
        .first()
    )

    if not latest or not previous:
        return {
            "period": period,
            "lost": 0,
            "gained": 0,
            "previous_total": previous.total_backlinks if previous else 0,
            "current_total": latest.total_backlinks if latest else 0,
            "filtered": False,
        }

    diff = latest.total_backlinks - previous.total_backlinks
    gained = diff if diff > 0 else 0
    lost = abs(diff) if diff < 0 else 0

    return {
        "period": period,
        "lost": lost,
        "gained": gained,
        "previous_total": previous.total_backlinks,
        "current_total": latest.total_backlinks,
        "date_start": previous.date.strftime("%Y-%m-%d"),
        "date_end": latest.date.strftime("%Y-%m-%d"),
        "filtered": False,
    }


@main_routes.route("/")
@login_required
def index():
    # === RANGE ===
    range_param = request.args.get("range", "1m")

    # === FILTRES MULTIPLES ===
    filter_tags = request.args.getlist("tag")
    filter_sources = request.args.getlist("source")

    # Pour les utilisateurs (main_admin seulement)
    if current_user.role == "main_admin":
        filter_users = request.args.getlist("user_id")
        filter_users = [int(u) for u in filter_users if u.isdigit()]

        # 🟩 FIX : si aucun user sélectionné → tous les users
        if not filter_users:
            filter_users = [u.id for u in User.query.all()]
    else:
        filter_users = [current_user.id]

    # === DATES ===
    start_date, end_date, days, range_label = get_date_range(range_param)

    # ==================================================
    #                     KPIs
    # ==================================================

    # 1 • TOTAL BACKLINKS
    total_backlinks = calculate_total_backlinks(
        filter_users, filter_tags, filter_sources
    )

    backlinks_added = calculate_backlinks_added(
        filter_users, start_date, filter_tags, filter_sources
    )

    backlinks_change = (
        f"+{backlinks_added}" if backlinks_added > 0 else str(backlinks_added)
    )
    backlinks_change_type = "positive" if backlinks_added >= 0 else "negative"

    # 2 • DOMAINES TOTAUX
    total_domains = calculate_total_domains(filter_users, filter_tags, filter_sources)

    domains_added = calculate_domains_added(
        filter_users, start_date, filter_tags, filter_sources
    )

    domains_change = f"+{domains_added}" if domains_added > 0 else str(domains_added)
    domains_change_type = "positive" if domains_added >= 0 else "negative"

    # 3 • LIENS GAGNÉS/PERDUS
    links_diff = calculate_links_diff_period(
        filter_users,
        period=range_param,
        filter_tags=filter_tags,
        filter_sources=filter_sources,
    )
    links_lost = links_diff["lost"]
    links_gained = links_diff["gained"]

    # 4 • % FOLLOW
    follow_percentage = calculate_follow_percentage(
        filter_users, filter_tags, filter_sources
    )

    follow_change = calculate_follow_percentage_change(
        filter_users, start_date, filter_tags, filter_sources
    )

    follow_change_str = (
        f"+{follow_change}%" if follow_change >= 0 else f"{follow_change}%"
    )
    follow_change_type = "positive" if follow_change >= 0 else "negative"

    # 5 • QUALITÉ MOYENNE
    avg_quality = calculate_average_quality(filter_users, filter_tags, filter_sources)

    quality_change = calculate_quality_change(
        filter_users, start_date, filter_tags, filter_sources
    )

    quality_change_str = (
        f"+{quality_change}" if quality_change >= 0 else str(quality_change)
    )
    quality_change_type = "positive" if quality_change >= 0 else "negative"

    # PACK KPIs
    kpis = {
        "total_backlinks": total_backlinks,
        "backlinks_change": backlinks_change,
        "backlinks_change_type": backlinks_change_type,
        "total_domains": total_domains,
        "domains_change": domains_change,
        "domains_change_type": domains_change_type,
        "links_gained": links_gained,
        "links_lost": links_lost,
        "follow_percentage": follow_percentage,
        "follow_change": follow_change_str,
        "follow_change_type": follow_change_type,
        "avg_quality": avg_quality,
        "quality_change": quality_change_str,
        "quality_change_type": quality_change_type,
    }

    # ==================================================
    #                     GRAPHES
    # ==================================================

    charts_data = {
        "evolution": get_evolution_data(
            filter_users, start_date, days, filter_tags, filter_sources
        ),
        "follow_distribution": get_follow_distribution(
            filter_users, filter_tags, filter_sources
        ),
        "http_status": get_http_status_distribution(
            filter_users, filter_tags, filter_sources
        ),
        "top_anchors": get_top_anchors(
            filter_users,
            limit=10,
            filter_tags=filter_tags,
            filter_sources=filter_sources,
        ),
        "pv_pt_scatter": get_pv_pt_scatter(
            filter_users,
            start_date,
            end_date,
            limit=50,
            filter_tags=filter_tags,
            filter_sources=filter_sources,
        ),
    }

    timestamp = int(datetime.now().timestamp())

    return render_template(
        "dashboard/index.html",
        kpis=kpis,
        charts_data=charts_data,
        range_label=range_label,
        range_param=range_param,
        timestamp=timestamp,
        tags=Tag.query.all(),
        sources=Source.query.all(),
        filter_tags=filter_tags,
        filter_sources=filter_sources,
        filter_users=filter_users,
        users=User.query.all(),
    )


@main_routes.route("/dashboard/content")
@login_required
def dashboard_content():
    """Route partielle HTMX pour recharger uniquement le contenu du dashboard"""

    # === RANGE ===
    range_param = request.args.get("range", "1m")

    # === FILTRES MULTIPLES ===
    filter_tags = request.args.getlist("tag")
    filter_sources = request.args.getlist("source")

    # Filtres utilisateurs (main_admin)
    if current_user.role == "main_admin":
        # Récupère les valeurs envoyées par le formulaire
        raw_users = request.args.getlist("user_id")

        # --- CAS 1 : "Tous les utilisateurs" est sélectionné ---
        if "__all__" in raw_users:
            # On remplace par la liste complète des IDs utilisateurs
            filter_users = [u.id for u in User.query.all()]

        # --- CAS 2 : Rien de sélectionné → afficher MES données uniquement ---
        elif not raw_users:
            filter_users = [current_user.id]

        # --- CAS 3 : Liste spécifique sélectionnée ---
        else:
            # Ne prendre que les IDs valides
            filter_users = [int(u) for u in raw_users if u.isdigit()]

    else:
        # Pour un utilisateur normal : seulement lui-même
        filter_users = [current_user.id]

    # === DATES ===
    start_date, end_date, days, range_label = get_date_range(range_param)

    # ==================================================
    #                     KPIs
    # ==================================================

    # 1 • BACKLINKS
    total_backlinks = calculate_total_backlinks(
        filter_users, filter_tags, filter_sources
    )

    backlinks_added = calculate_backlinks_added(
        filter_users, start_date, filter_tags, filter_sources
    )

    backlinks_change = (
        f"+{backlinks_added}" if backlinks_added > 0 else str(backlinks_added)
    )
    backlinks_change_type = "positive" if backlinks_added >= 0 else "negative"

    # 2 • DOMAINES
    total_domains = calculate_total_domains(filter_users, filter_tags, filter_sources)

    domains_added = calculate_domains_added(
        filter_users, start_date, filter_tags, filter_sources
    )

    domains_change = f"+{domains_added}" if domains_added > 0 else str(domains_added)
    domains_change_type = "positive" if domains_added >= 0 else "negative"

    # 3 • LINKS GAINED / LOST
    links_diff = calculate_links_diff_period(
        filter_users,
        period=range_param,
        filter_tags=filter_tags,
        filter_sources=filter_sources,
    )

    links_lost = links_diff["lost"]
    links_gained = links_diff["gained"]

    # 4 • FOLLOW %
    follow_percentage = calculate_follow_percentage(
        filter_users, filter_tags, filter_sources
    )

    follow_change = calculate_follow_percentage_change(
        filter_users, start_date, filter_tags, filter_sources
    )

    follow_change_str = (
        f"+{follow_change}%" if follow_change >= 0 else f"{follow_change}%"
    )
    follow_change_type = "positive" if follow_change >= 0 else "negative"

    # 5 • QUALITÉ MOYENNE
    avg_quality = calculate_average_quality(filter_users, filter_tags, filter_sources)

    quality_change = calculate_quality_change(
        filter_users, start_date, filter_tags, filter_sources
    )

    quality_change_str = (
        f"+{quality_change}" if quality_change >= 0 else str(quality_change)
    )
    quality_change_type = "positive" if quality_change >= 0 else "negative"

    # PACK KPIs
    kpis = {
        "total_backlinks": total_backlinks,
        "backlinks_change": backlinks_change,
        "backlinks_change_type": backlinks_change_type,
        "total_domains": total_domains,
        "domains_change": domains_change,
        "domains_change_type": domains_change_type,
        "links_gained": links_gained,
        "links_lost": links_lost,
        "follow_percentage": follow_percentage,
        "follow_change": follow_change_str,
        "follow_change_type": follow_change_type,
        "avg_quality": avg_quality,
        "quality_change": quality_change_str,
        "quality_change_type": quality_change_type,
    }

    # ==================================================
    #                     GRAPHES
    # ==================================================

    charts_data = {
        "evolution": get_evolution_data(
            filter_users, start_date, days, filter_tags, filter_sources
        ),
        "follow_distribution": get_follow_distribution(
            filter_users, filter_tags, filter_sources
        ),
        "http_status": get_http_status_distribution(
            filter_users, filter_tags, filter_sources
        ),
        "top_anchors": get_top_anchors(
            filter_users,
            limit=10,
            filter_tags=filter_tags,
            filter_sources=filter_sources,
        ),
        "pv_pt_scatter": get_pv_pt_scatter(
            filter_users,
            start_date,
            end_date,
            limit=50,
            filter_tags=filter_tags,
            filter_sources=filter_sources,
        ),
    }

    timestamp = int(datetime.now().timestamp())

    # === Renvoi du contenu partiel (HTMX) ===
    return render_template(
        "dashboard/_dashboard_content.html",
        kpis=kpis,
        charts_data=charts_data,
        range_label=range_label,
        timestamp=timestamp,
        range_param=range_param,
        tags=Tag.query.all(),
        sources=Source.query.all(),
        users=User.query.all(),
        filter_tags=filter_tags,
        filter_sources=filter_sources,
        filter_users=filter_users,
    )
