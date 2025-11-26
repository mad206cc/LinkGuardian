from datetime import datetime, timedelta
from urllib.parse import urlparse

# routes/dashboard_routes.py
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from models import Website, WebsiteStats, Tag, Source

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


def calculate_total_backlinks(user_id, filter_tag=None, filter_source=None):
    query = Website.query.filter(Website.user_id == user_id)
    query = apply_filters(query, filter_tag, filter_source)
    return query.count()



def calculate_backlinks_added(user_id, start_date, filter_tag=None, filter_source=None):
    """Calcule le nombre de backlinks ajoutés dans la période"""

    query = Website.query.filter(
        Website.user_id == user_id,
        Website.first_checked >= start_date
    )

    # 🔥 Appliquer filtres Tag + Source
    query = apply_filters(query, filter_tag, filter_source)

    return query.count()


def calculate_total_domains(user_id, filter_tag=None, filter_source=None):
    query = Website.query.with_entities(Website.domains).filter(
        Website.user_id == user_id
    )
    query = apply_filters(query, filter_tag, filter_source)
    return query.distinct().count()



def calculate_domains_added(user_id, start_date, filter_tag=None, filter_source=None):
    query = Website.query.with_entities(Website.domains).filter(
        Website.user_id == user_id,
        Website.first_checked >= start_date
    )

    # 🔥 Appliquer filtres Tag + Source
    query = apply_filters(query, filter_tag, filter_source)

    domains = {d for (d,) in query.all() if d}

    return len(domains)



def calculate_total_urls(user_id, filter_tag=None, filter_source=None):
    query = Website.query.with_entities(Website.link_to_check).filter(
        Website.user_id == user_id
    )
    query = apply_filters(query, filter_tag, filter_source)
    return query.distinct().count()


def calculate_urls_added(user_id, start_date, filter_tag=None, filter_source=None):
    query = Website.query.with_entities(Website.link_to_check).filter(
        Website.user_id == user_id,
        Website.first_checked >= start_date
    )
    query = apply_filters(query, filter_tag, filter_source)
    return query.distinct().count()



def calculate_follow_percentage(user_id, filter_tag=None, filter_source=None):
    total_q = Website.query.filter(Website.user_id == user_id)
    total_q = apply_filters(total_q, filter_tag, filter_source)
    total = total_q.count()

    if total == 0:
        return 0.0

    follow_q = Website.query.filter(
        Website.user_id == user_id,
        Website.link_follow_status == "follow"
    )
    follow_q = apply_filters(follow_q, filter_tag, filter_source)
    follow = follow_q.count()

    return round((follow / total) * 100, 1)



def calculate_follow_percentage_change(user_id, start_date, filter_tag=None, filter_source=None):
    current_percentage = calculate_follow_percentage(user_id, filter_tag, filter_source)

    total_before_q = Website.query.filter(
        Website.user_id == user_id,
        Website.first_checked < start_date
    )
    total_before_q = apply_filters(total_before_q, filter_tag, filter_source)
    total_before = total_before_q.count()

    if total_before == 0:
        return 0.0

    follow_before_q = Website.query.filter(
        Website.user_id == user_id,
        Website.first_checked < start_date,
        Website.link_follow_status == "follow"
    )
    follow_before_q = apply_filters(follow_before_q, filter_tag, filter_source)
    follow_before = follow_before_q.count()

    percentage_before = round((follow_before / total_before) * 100, 1)
    return round(current_percentage - percentage_before, 1)



def calculate_average_quality(user_id, filter_tag=None, filter_source=None):
    q = Website.query.filter(
        Website.user_id == user_id,
        Website.page_trust.isnot(None),
        Website.page_value.isnot(None),
    )
    q = apply_filters(q, filter_tag, filter_source)
    sites = q.all()

    if not sites:
        return 0

    total_quality = sum((site.page_trust * 0.6 + site.page_value * 0.4) for site in sites)
    return round(total_quality / len(sites), 1)


def calculate_quality_change(user_id, start_date, filter_tag=None, filter_source=None):
    current_quality = calculate_average_quality(user_id, filter_tag, filter_source)

    q = Website.query.filter(
        Website.user_id == user_id,
        Website.first_checked < start_date,
        Website.page_trust.isnot(None),
        Website.page_value.isnot(None),
    )
    q = apply_filters(q, filter_tag, filter_source)
    sites_before = q.all()

    if not sites_before:
        return 0

    total_quality = sum((s.page_trust * 0.6 + s.page_value * 0.4) for s in sites_before)
    avg_quality_before = total_quality / len(sites_before)

    return round(current_quality - avg_quality_before, 1)



def get_evolution_data(user_id, start_date, days, filter_tag=None, filter_source=None):
    intervals = []
    backlinks_counts = []
    domains_counts = []
    interval_days = days / 10

    for i in range(11):
        date = start_date + timedelta(days=interval_days * i)
        intervals.append(date.strftime("%Y-%m-%d"))

        # Backlinks
        q = Website.query.filter(
            Website.user_id == user_id,
            Website.first_checked <= date,
        )
        q = apply_filters(q, filter_tag, filter_source)
        backlinks_counts.append(q.count())

        # Domains
        q_dom = Website.query.filter(
            Website.user_id == user_id,
            Website.first_checked <= date,
        )
        q_dom = apply_filters(q_dom, filter_tag, filter_source)
        domains = {urlparse(s.url).netloc.replace("www.", "") for s in q_dom.all() if s.url}
        domains_counts.append(len(domains))

    return [
        {"name": "Backlinks", "x": intervals, "y": backlinks_counts},
        {"name": "Domaines", "x": intervals, "y": domains_counts},
    ]



def get_follow_distribution(user_id, filter_tag=None, filter_source=None):
    q_total = Website.query.filter(Website.user_id == user_id)
    q_total = apply_filters(q_total, filter_tag, filter_source)
    total = q_total.count()

    q_follow = Website.query.filter(
        Website.user_id == user_id,
        Website.link_follow_status == "follow"
    )
    q_follow = apply_filters(q_follow, filter_tag, filter_source)
    follow = q_follow.count()

    return {
        "labels": ["Follow", "NoFollow"],
        "values": [follow, total - follow],
        "colors": ["#22c55e", "#f59e0b"],
    }


def get_http_status_distribution(user_id, filter_tag=None, filter_source=None):
    """Génère les données de répartition des statuts HTTP"""
    status_counts = {}

    # 🔥 Construire la QUERY
    query = Website.query.filter(Website.user_id == user_id)

    # 🔥 Appliquer les filtres Tag / Source correctement
    query = apply_filters(query, filter_tag, filter_source)

    # 🔥 Exécuter la query SEULEMENT après les filtres
    sites = query.all()

    for site in sites:
        status = site.status_code or "Inconnu"
        status_str = str(status)

        # Regrouper les codes similaires
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

def get_top_anchors(user_id, limit=10, filter_tag=None, filter_source=None):
    q = Website.query.filter(
        Website.user_id == user_id,
        Website.anchor_text.isnot(None),
        Website.anchor_text != "",
    )
    q = apply_filters(q, filter_tag, filter_source)

    anchors = (
        q.with_entities(
            Website.anchor_text, func.count(Website.anchor_text).label("count")
        )
        .group_by(Website.anchor_text)
        .order_by(func.count(Website.anchor_text).desc())
        .limit(limit)
        .all()
    )

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
                current_length += len(word) + 1  # +1 pour l'espace
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
        "#38bdf8", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
        "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#64748b"
    ]
    return {"labels": labels, "values": values, "colors": colors[:len(labels)]}



def get_pv_pt_scatter(user_id, start_date, end_date, limit=50, filter_tag=None, filter_source=None):
    q = Website.query.filter(
        Website.user_id == user_id,
        Website.page_value.isnot(None),
        Website.page_trust.isnot(None),
        Website.last_checked >= start_date,
        Website.last_checked <= end_date,
    )
    q = apply_filters(q, filter_tag, filter_source)
    sites = q.order_by((Website.page_value + Website.page_trust).desc()).limit(limit).all()

    x_values = [site.page_value for site in sites]
    y_values = [site.page_trust for site in sites]
    labels = [urlparse(site.url).netloc for site in sites]
    sizes = [int(site.backlinks_external or 5) for site in sites]

    return {"x": x_values, "y": y_values, "labels": labels, "sizes": sizes}


def calculate_links_diff_period(
    user_id,
    period="1m",
    filter_tag=None,
    filter_source=None
):
    """
    Calcule les liens gagnés/perdus sur une période.
    
    - SANS filtre : utilise WebsiteStats (rapide, snapshots)
    - AVEC filtres Tag / Source : calcule en direct depuis Website (précis)
    """

    # Déterminer la durée en jours
    if period == "12m":
        days = 365
    elif period == "6m":
        days = 180
    elif period == "3m":
        days = 90
    else:
        days = 30  # par défaut : 1 mois

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # ───────────────────────────────────────────────
    # 🚨 MODE 1 : FILTRÉ → Website (pas WebsiteStats)
    # ───────────────────────────────────────────────
    if filter_tag or filter_source:
        # Backlinks avant la période
        previous_query = Website.query.filter(
            Website.user_id == user_id,
            Website.first_checked < start_date
        )
        previous_query = apply_filters(previous_query, filter_tag, filter_source)
        previous_total = previous_query.count()

        # Backlinks jusqu'à maintenant
        current_query = Website.query.filter(
            Website.user_id == user_id,
            Website.first_checked <= end_date
        )
        current_query = apply_filters(current_query, filter_tag, filter_source)
        current_total = current_query.count()

        diff = current_total - previous_total
        lost = abs(diff) if diff < 0 else 0
        gained = diff if diff > 0 else 0

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
    # 🚀 MODE 2 : NON FILTRÉ → WebsiteStats (défaut)
    # ───────────────────────────────────────────────

    latest = (
        WebsiteStats.query.filter(
            WebsiteStats.user_id == user_id,
            WebsiteStats.date <= end_date
        )
        .order_by(WebsiteStats.date.desc())
        .first()
    )

    previous = (
        WebsiteStats.query.filter(
            WebsiteStats.user_id == user_id,
            WebsiteStats.date <= start_date
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
    lost = abs(diff) if diff < 0 else 0
    gained = diff if diff > 0 else 0

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
    """Route principale du dashboard"""

    # Récupérer la plage de dates
    range_param = request.args.get("range", "1m")
    filter_tag = request.args.get("tag")
    filter_source = request.args.get("source")
    start_date, end_date, days, range_label = get_date_range(range_param )

    # === KPIs ===

    # 1. Backlinks totaux
    total_backlinks = calculate_total_backlinks(current_user.id , filter_tag, filter_source)
    backlinks_added = calculate_backlinks_added(current_user.id, start_date , filter_tag, filter_source)
    backlinks_change = (
        f"+{backlinks_added}" if backlinks_added > 0 else str(backlinks_added)
    )
    backlinks_change_type = "positive" if backlinks_added >= 0 else "negative"

    # 2. Domaines référents
    total_domains = calculate_total_domains(current_user.id , filter_tag, filter_source)
    domains_added = calculate_domains_added(current_user.id, start_date , filter_tag, filter_source)
    domains_change = f"+{domains_added}" if domains_added > 0 else str(domains_added)
    domains_change_type = "positive" if domains_added >= 0 else "negative"

    links_diff = calculate_links_diff_period(current_user.id, period=range_param , filter_tag=filter_tag, filter_source=filter_source)
    links_lost = links_diff["lost"]
    links_gained = links_diff["gained"]

    # 5. % Follow
    follow_percentage = calculate_follow_percentage(current_user.id , filter_tag, filter_source)
    follow_change = calculate_follow_percentage_change(current_user.id, start_date , filter_tag, filter_source)
    follow_change_str = (
        f"+{follow_change}%" if follow_change >= 0 else f"{follow_change}%"
    )
    follow_change_type = "positive" if follow_change >= 0 else "negative"

    # 6. Qualité moyenne
    avg_quality = calculate_average_quality(current_user.id , filter_tag, filter_source)
    quality_change = calculate_quality_change(current_user.id, start_date , filter_tag, filter_source)
    quality_change_str = (
        f"+{quality_change}" if quality_change >= 0 else str(quality_change)
    )
    quality_change_type = "positive" if quality_change >= 0 else "negative"

    # Grouper les KPIs
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

    # === GRAPHIQUES ===

    charts_data = {
        "evolution": get_evolution_data(current_user.id, start_date, days , filter_tag, filter_source), 
        "follow_distribution": get_follow_distribution(current_user.id , filter_tag, filter_source),
        "http_status": get_http_status_distribution(current_user.id , filter_tag, filter_source),
        "top_anchors": get_top_anchors(current_user.id, limit=10 , filter_tag = filter_tag, filter_source = filter_source),
        "pv_pt_scatter": get_pv_pt_scatter(
            current_user.id, start_date, end_date, limit=50, filter_tag = filter_tag, filter_source = filter_source
        ),
    }

    # Timestamp pour éviter le cache des graphiques
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
        filter_tag=filter_tag,
        filter_source=filter_source,
    )


@main_routes.route("/dashboard/content")
@login_required
def dashboard_content():
    """Route partielle HTMX pour recharger uniquement le contenu du dashboard"""

    # Récupérer la plage de dates
    range_param = request.args.get("range", "1m")

    filter_tag = request.args.get("tag")
    filter_source = request.args.get("source")

    start_date, end_date, days, range_label = get_date_range(range_param)

    # === KPIs ===
    total_backlinks = calculate_total_backlinks(current_user.id, filter_tag, filter_source)
    backlinks_added = calculate_backlinks_added(current_user.id, start_date, filter_tag, filter_source)
    backlinks_change = (
        f"+{backlinks_added}" if backlinks_added > 0 else str(backlinks_added)
    )
    backlinks_change_type = "positive" if backlinks_added >= 0 else "negative"

    total_domains = calculate_total_domains(current_user.id, filter_tag, filter_source)
    domains_added = calculate_domains_added(current_user.id, start_date, filter_tag, filter_source)
    domains_change = f"+{domains_added}" if domains_added > 0 else str(domains_added)
    domains_change_type = "positive" if domains_added >= 0 else "negative"

    links_diff = calculate_links_diff_period(current_user.id, period=range_param, filter_tag = filter_tag, filter_source = filter_source)
    links_lost = links_diff["lost"]
    links_gained = links_diff["gained"]

    follow_percentage = calculate_follow_percentage(current_user.id, filter_tag, filter_source)
    follow_change = calculate_follow_percentage_change(current_user.id, start_date, filter_tag, filter_source)
    follow_change_str = (
        f"+{follow_change}%" if follow_change >= 0 else f"{follow_change}%"
    )
    follow_change_type = "positive" if follow_change >= 0 else "negative"

    avg_quality = calculate_average_quality(current_user.id, filter_tag, filter_source)
    quality_change = calculate_quality_change(current_user.id, start_date, filter_tag, filter_source)
    quality_change_str = (
        f"+{quality_change}" if quality_change >= 0 else str(quality_change)
    )
    quality_change_type = "positive" if quality_change >= 0 else "negative"

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

    # === GRAPHIQUES ===
    charts_data = {
        "evolution": get_evolution_data(current_user.id, start_date, days, filter_tag, filter_source),
        "follow_distribution": get_follow_distribution(current_user.id, filter_tag, filter_source),
        "http_status": get_http_status_distribution(current_user.id, filter_tag, filter_source),
        "top_anchors": get_top_anchors(current_user.id, limit=10, filter_tag = filter_tag, filter_source = filter_source),
        "pv_pt_scatter": get_pv_pt_scatter(
            current_user.id, start_date, end_date, limit=50, filter_tag = filter_tag, filter_source = filter_source
        ),
    }

    timestamp = int(datetime.now().timestamp())

    # ✅ Renvoie SEULEMENT le template partiel, pas la page complète
    return render_template(
        "dashboard/_dashboard_content.html",
        kpis=kpis,
        charts_data=charts_data,
        range_label=range_label,
        timestamp=timestamp,
        range_param=range_param,
        tags=Tag.query.all(),
        sources=Source.query.all(),
        filter_tag=filter_tag,
        filter_source=filter_source,
    )
