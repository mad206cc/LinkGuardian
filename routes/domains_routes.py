import json
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode, urlparse

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from models import Source, Tag, User, Website

domains_routes = Blueprint("domains_routes", __name__)


def get_filtered_domains_query():

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
    # 🔍 RECHERCHE TEXTUELLE
    # ============================

    q = request.args.get("q", "").strip().lower()
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            func.lower(Website.url).ilike(pattern) |
            func.lower(Website.anchor_text).ilike(pattern)
        )

    return query



@domains_routes.route("/domains")
@login_required
def domain_stats():
    """Page de statistiques sur les domaines référents"""

    # ----------------------
    #  Récupération du filtrage
    # ----------------------
    query = get_filtered_domains_query()
    websites = query.all()

    # ----------------------
    #  Pagination
    # ----------------------
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # ============================
    # RECONSTRUCTION DES FILTRES (pour le front)
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

    # ----------------------
    #  Build filters dict
    # ----------------------
    filters = {
        "q": request.args.get("q", ""),
        "follow": request.args.get("follow", "all"),
        "indexed": request.args.get("indexed", "all"),
        "sort": request.args.get("sort", "created"),
        "order": request.args.get("order", "desc"),
        # Multi-values
        "tag": filter_tags,
        "source": filter_sources,
        "user_id": filter_user_ids,
    }

    # ----------------------
    #  Si aucun site ne correspond
    # ----------------------
    if not websites:
        tags = Tag.query.all()
        sources = Source.query.all()
        users = User.query.all() if current_user.role == "main_admin" else []

        return render_template(
            "domains/list.html",
            domains=[],
            total_domains=0,
            domains_this_month=0,
            avg_quality_current=0,
            avg_quality_previous=0,
            quality_increase=0,
            quality_percent_change=0,
            avg_backlinks_per_domain=0,
            premium_domains=0,
            quality_distribution={"labels": [], "values": [], "colors": []},
            top_domains_chart={"labels": [], "values": [], "colors": []},
            quality_distribution_json="{}",
            top_domains_chart_json="{}",
            current_page=1,
            total_pages=0,
            tags=tags,
            sources=sources,
            users=users,
            filters=filters,
        )

    # ----------------------
    #  Construction domain_data
    # ----------------------
    domain_data = defaultdict(
        lambda: {
            "urls": [],
            "status": [],
            "follow": {"follow": 0, "nofollow": 0},
            "page_values": [],
            "page_trusts": [],
            "first_dates": [],
        }
    )

    for site in websites:
        parsed = urlparse(site.url)
        domain = parsed.netloc or site.url
        domain = domain.replace("www.", "")

        domain_data[domain]["urls"].append(site.url)
        if site.status_code:
            domain_data[domain]["status"].append(site.status_code)

        if site.link_follow_status and site.link_follow_status.lower() == "follow":
            domain_data[domain]["follow"]["follow"] += 1
        else:
            domain_data[domain]["follow"]["nofollow"] += 1

        if site.page_value is not None:
            domain_data[domain]["page_values"].append(site.page_value)
        if site.page_trust is not None:
            domain_data[domain]["page_trusts"].append(site.page_trust)
        if site.first_checked:
            domain_data[domain]["first_dates"].append(site.first_checked)

    # ----------------------
    #  Calculs statistiques
    # ----------------------
    now = datetime.now()
    current_year, current_month = now.year, now.month

    domains_this_month = 0
    all_qualities_current = []
    all_qualities_previous = []
    domain_list = []

    total_backlinks = 0
    premium_domains = 0

    nb_premium = nb_bon = nb_moyen = nb_faible = 0

    for domain, data in domain_data.items():
        count = len(data["urls"])
        total_backlinks += count

        first_link_date = min(data["first_dates"]) if data["first_dates"] else None
        days_since_first = (now - first_link_date).days if first_link_date else None

        avg_page_trust = (
            round(sum(data["page_trusts"]) / len(data["page_trusts"]), 1)
            if data["page_trusts"]
            else 0
        )
        avg_page_value = (
            round(sum(data["page_values"]) / len(data["page_values"]), 1)
            if data["page_values"]
            else 0
        )

        avg_quality = round((avg_page_trust * 0.6) + (avg_page_value * 0.4), 1)

        # Catégorisation
        if avg_quality >= 40:
            nb_premium += 1
        elif avg_quality >= 25:
            nb_bon += 1
        elif avg_quality >= 15:
            nb_moyen += 1
        else:
            nb_faible += 1

        if avg_quality > 40:
            premium_domains += 1

        if first_link_date:
            if (
                first_link_date.year == current_year
                and first_link_date.month == current_month
            ):
                domains_this_month += 1

            if first_link_date.year < current_year or (
                first_link_date.year == current_year
                and first_link_date.month < current_month
            ):
                all_qualities_previous.append(avg_quality)

            all_qualities_current.append(avg_quality)

        domain_list.append(
            {
                "name": domain,
                "category": None,
                "backlinks_count": count,
                "backlinks_change": 0,
                "follow_count": data["follow"]["follow"],
                "nofollow_count": data["follow"]["nofollow"],
                "avg_quality": avg_quality,
                "avg_page_value": avg_page_value,
                "avg_page_trust": avg_page_trust,
                "first_link_date": first_link_date,
                "days_since_first": days_since_first,
            }
        )

    # ----------------------
    #  Calculs finaux
    # ----------------------
    avg_quality_current = (
        round(sum(all_qualities_current) / len(all_qualities_current), 2)
        if all_qualities_current
        else 0
    )
    avg_quality_previous = (
        round(sum(all_qualities_previous) / len(all_qualities_previous), 2)
        if all_qualities_previous
        else 0
    )

    quality_increase = round(avg_quality_current - avg_quality_previous, 2)
    quality_percent_change = (
        round((quality_increase / avg_quality_previous) * 100, 2)
        if avg_quality_previous > 0
        else 0
    )

    avg_backlinks_per_domain = (
        round(total_backlinks / len(domain_data), 2) if domain_data else 0
    )

    quality_distribution = {
        "labels": ["Premium (> 40)", "Bon (25-40)", "Moyen (15-25)", "Faible (0-15)"],
        "values": [nb_premium, nb_bon, nb_moyen, nb_faible],
        "colors": ["#22c55e", "#38bdf8", "#f59e0b", "#ef4444"],
    }

    domain_list.sort(key=lambda d: d["backlinks_count"], reverse=True)

    # Pagination
    total_domains_count = len(domain_list)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_domains = domain_list[start_idx:end_idx]

    total_pages = (total_domains_count + per_page - 1) // per_page

    # Top 10
    top_domains = sorted(domain_list, key=lambda d: d["avg_quality"], reverse=True)[:10]

    top_domains_chart = {
        "labels": [d["name"] for d in top_domains],
        "values": [d["backlinks_count"] for d in top_domains],
        "colors": [
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
        ][: len(top_domains)],
    }

    tags = Tag.query.all()
    sources = Source.query.all()
    users = User.query.all() if current_user.role == "main_admin" else []

    # ----------------------
    #  Build pagination URL
    # ----------------------

    pagination_base_url = url_for(
    "domains_routes.domains_table_partial",
    q=filters["q"],
    tag=filter_tags,
    source=filter_sources,
    user_id=filter_user_ids,
    follow=filters["follow"],
    indexed=filters["indexed"],
    sort=filters["sort"],
    order=filters["order"],
    )

    # ----------------------
    #  Render final
    # ----------------------
    return render_template(
        "domains/list.html",
        domains=paginated_domains,
        total_domains=total_domains_count,
        domains_this_month=domains_this_month,
        avg_quality_current=avg_quality_current,
        avg_quality_previous=avg_quality_previous,
        quality_increase=quality_increase,
        quality_percent_change=quality_percent_change,
        avg_backlinks_per_domain=avg_backlinks_per_domain,
        premium_domains=premium_domains,
        quality_distribution=quality_distribution,
        top_domains_chart=top_domains_chart,
        quality_distribution_json=json.dumps(quality_distribution),
        top_domains_chart_json=json.dumps(top_domains_chart),
        current_page=page,
        total_pages=total_pages,
        filters=filters,
        tags=tags,
        sources=sources,
        users=users,
        pagination_base_url=pagination_base_url,
    )


@domains_routes.route("/domains/partial/table")
@login_required
def domains_table_partial():
    """Retourne uniquement la table des domaines pour HTMX"""

    # Si ce n’est pas une requête HTMX → redirection page complète
    if not request.headers.get("HX-Request"):
        page = request.args.get("page", 1, type=int)
        return redirect(f"/domains?page={page}")

    # Récupération réelle filtrée
    query = get_filtered_domains_query()
    websites = query.all()

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 10

    if not websites:
        return render_template(
            "domains/_domains_table.html",
            domains=[],
            current_page=1,
            total_pages=0,
        )

    # --------------------------
    # Construction domain_data
    # --------------------------
    domain_data = defaultdict(
        lambda: {
            "urls": [],
            "status": [],
            "follow": {"follow": 0, "nofollow": 0},
            "page_values": [],
            "page_trusts": [],
            "first_dates": [],
        }
    )

    for site in websites:
        parsed = urlparse(site.url)
        domain = parsed.netloc or site.url
        domain = domain.replace("www.", "")

        domain_data[domain]["urls"].append(site.url)

        if site.status_code:
            domain_data[domain]["status"].append(site.status_code)

        if site.link_follow_status and site.link_follow_status.lower() == "follow":
            domain_data[domain]["follow"]["follow"] += 1
        else:
            domain_data[domain]["follow"]["nofollow"] += 1

        if site.page_value is not None:
            domain_data[domain]["page_values"].append(site.page_value)

        if site.page_trust is not None:
            domain_data[domain]["page_trusts"].append(site.page_trust)

        if site.first_checked:
            domain_data[domain]["first_dates"].append(site.first_checked)

    # --------------------------
    # Construction domain_list
    # --------------------------
    now = datetime.now()
    domain_list = []

    for domain, data in domain_data.items():
        count = len(data["urls"])
        first_link_date = min(data["first_dates"]) if data["first_dates"] else None
        days_since_first = (now - first_link_date).days if first_link_date else None

        avg_page_trust = (
            round(sum(data["page_trusts"]) / len(data["page_trusts"]), 1)
            if data["page_trusts"]
            else 0
        )
        avg_page_value = (
            round(sum(data["page_values"]) / len(data["page_values"]), 1)
            if data["page_values"]
            else 0
        )

        avg_quality = round((avg_page_trust * 0.6) + (avg_page_value * 0.4), 1)

        domain_list.append(
            {
                "name": domain,
                "category": None,
                "backlinks_count": count,
                "backlinks_change": 0,
                "follow_count": data["follow"]["follow"],
                "nofollow_count": data["follow"]["nofollow"],
                "avg_quality": avg_quality,
                "avg_page_value": avg_page_value,
                "avg_page_trust": avg_page_trust,
                "first_link_date": first_link_date,
                "days_since_first": days_since_first,
            }
        )

    # Tri
    domain_list.sort(key=lambda d: d["backlinks_count"], reverse=True)

    # --------------------------
    # Pagination
    # --------------------------
    total_domains_count = len(domain_list)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_domains = domain_list[start_idx:end_idx]

    total_pages = (total_domains_count + per_page - 1) // per_page

    # ============================
    # Reconstruction des filtres (pour la pagination HTMX)
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

    # ============================
    # 6) Base URL pour HTMX pagination (TRÈS IMPORTANT)
    # ============================
    base_url = url_for(
        "domains_routes.domains_table_partial",
        q=request.args.get("q", ""),
        tag=filter_tags,               # LISTE
        source=filter_sources,         # LISTE
        user_id=filter_user_ids,       # LISTE
    )

    # --------------------------
    # Render HTML partial
    # --------------------------
    return render_template(
        "domains/_domains_table.html",
        domains=paginated_domains,
        current_page=page,
        total_pages=total_pages,
        pagination_base_url=base_url,
    )