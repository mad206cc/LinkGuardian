from datetime import datetime
from models import db, Website, WebsiteStats

def save_stats_snapshot(user_id):
    """Sauvegarde un snapshot complet des KPIs pour l'utilisateur."""
    total_backlinks = Website.query.filter_by(user_id=user_id).count()

    total_domains = (
        Website.query.filter(Website.user_id == user_id)
        .with_entities(Website.domains)
        .distinct()
        .count()
    ) or 0

    follow_count = Website.query.filter_by(
        user_id=user_id, link_follow_status="follow"
    ).count()
    follow_percentage = round((follow_count / total_backlinks * 100), 1) if total_backlinks > 0 else 0

    sites = Website.query.filter(
        Website.user_id == user_id,
        Website.page_trust.isnot(None),
        Website.page_value.isnot(None),
    ).all()
    avg_quality = (
        round(sum((s.page_trust * 0.6 + s.page_value * 0.4) for s in sites) / len(sites), 1)
        if sites else 0
    )

    snapshot = WebsiteStats(
        user_id=user_id,
        date=datetime.now(),
        total_backlinks=total_backlinks,
        total_domains=total_domains,
        follow_percentage=follow_percentage,
        avg_quality=avg_quality,
        raw_data={
            "total_backlinks": total_backlinks,
            "total_domains": total_domains,
            "follow_percentage": follow_percentage,
            "avg_quality": avg_quality,
        },
    )

    db.session.add(snapshot)
    db.session.commit()

    print(f"📊 Snapshot enregistré pour user {user_id} ({snapshot.date})")

