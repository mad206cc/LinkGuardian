import asyncio
from datetime import datetime

from aiohttp import ClientError, ClientSession

# Importer Celery depuis le fichier dédié
from celery_app import celery
from database import db
from models import TaskRecord, User, Website
from services.api_babbar import fetch_url_data

# 🔧 CONFIGURATION DES LIMITES D'API
API_RATE_LIMITS = {
    "babbar": {"calls_per_minute": 10, "retry_after": 60},
    "google": {"calls_per_minute": 20, "retry_after": 30},
    "default": {"calls_per_minute": 10, "retry_after": 60},
}


class APIRateLimitError(Exception):
    """Exception levée quand on atteint une limite d'API"""

    def __init__(self, api_name, retry_after=60):
        self.api_name = api_name
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit atteint pour {api_name}. Retry après {retry_after}s"
        )


async def process_site_async(site_id):

    from services.api_serpapi import check_google_indexation
    from services.check_service import check_link_presence_and_follow_status_async

    site = Website.query.get(site_id)

    async with ClientSession() as session:

        # 1) HTML + ancre
        try:
            link_present, anchor_present, follow_status, status_code = \
                await check_link_presence_and_follow_status_async(
                    session, site.url, site.link_to_check, site.anchor_text
                )
            site.status_code = status_code
            site.link_status = "Lien présent" if link_present else "URL non présente"
            site.link_follow_status = follow_status if link_present else None
            site.anchor_status = "Ancre présente" if anchor_present else "Ancre manquante"
        except Exception as e:
            print("❌ HTML ERROR :", repr(e))

        # 2) Google indexing
        try:
            index_status = await check_google_indexation(session, site.url)
            site.google_index_status = index_status
        except Exception as e:
            print("❌ GOOGLE ERROR :", repr(e))

        # 3) Babbar
        try:
            babbar_data = fetch_url_data(site.url, async_mode=False)

            if babbar_data:
                site.page_value = babbar_data.get("pageValue")
                site.page_trust = babbar_data.get("pageTrust")
                site.bas = babbar_data.get("babbarAuthorityScore")
                site.backlinks_external = babbar_data.get("backlinksExternal")
                site.num_outlinks_ext = babbar_data.get("numOutLinksExt")

        except Exception as e:
            err = str(e).lower()
            if "limit" in err or "429" in err:
                raise APIRateLimitError("babbar", retry_after=60)
            print("❌ BABBAR ERROR :", repr(e))

        # 4) Commit final
        try:
            now = datetime.now()
            site.last_checked = now
            site.first_checked = site.first_checked or now

            db.session.commit()
        except Exception as e:
            print("❌ COMMIT ERROR :", repr(e))
            db.session.rollback()
            return {"success": False, "error": str(e), "site_id": site_id}

        # ⬅️ IMPORTANT : RETURN FINAL
        return {"success": True, "site_id": site.id}


@celery.task(
    name="tasks.check_single_site",
    bind=True,
    max_retries=7,
    default_retry_delay=60,
    rate_limit="8/m",
    autoretry_for=(APIRateLimitError, ClientError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def check_single_site(self, site_id):
    print(f"🔍 Vérification site ID: {site_id}")

    site = Website.query.get(site_id)
    if not site:
        print(f"⏭️ Site {site_id} supprimé — tâche terminée")
        return {"success": True, "skipped": True}

    try:
        result = asyncio.run(process_site_async(site_id))
        print(f"✅ Vérification OK pour {site_id}")
        return result

    except APIRateLimitError as exc:
        print(f"⏳ Rate limit pour site {site_id}, retry dans {exc.retry_after}s")
        raise self.retry(exc=exc, countdown=exc.retry_after)

    except Exception as exc:
        print(f"🔥 ERREUR NON-APIRATE POUR {site_id}: {exc}")

        # Retry uniquement si on n’a pas atteint le maximum
        if self.request.retries < self.max_retries:
            print(f"🔄 Retry pour {site_id} ({self.request.retries+1}/5)")
            raise self.retry(exc=exc, countdown=60)

        print(f"❌ Max retries atteints pour {site_id}, échec final.")
        return {"success": False, "error": str(exc), "site_id": site_id}


@celery.task(
    name="tasks.check_all_user_sites",
    rate_limit="10/m",  # ⬆️ Augmenté de 2/m à 10/m
)
def check_all_user_sites(user_id):
    """Vérifie tous les sites d'un utilisateur

    🚀 OPTIMISATION: Les tâches sont lancées sans countdown.
    Les workers multiples se répartissent automatiquement la charge.

    Args:
        user_id: ID de l'utilisateur
        urgent: Si True, les vérifications seront prioritaires
    """
    print(f"📄 Début vérification pour l'utilisateur {user_id}")

    sites = Website.query.filter_by(user_id=user_id).all()
    total_sites = len(sites)
    print(f"📊 {total_sites} sites à vérifier")

    if total_sites == 0:
        return {
            "user_id": user_id,
            "total_sites": 0,
            "planned_tasks": 0,
            "skipped_sites": 0,
            "task_ids": [],
        }

    task_ids = []
    skipped = 0

    # 🚀 STRATÉGIE: Lancer toutes les tâches immédiatement
    # Les workers multiples vont se répartir le travail automatiquement
    for i, site in enumerate(sites):
        # 🧹 Vérifie que le site est encore valide
        if not site or not site.url:
            skipped += 1
            continue

        # ✅ Lancer la tâche SANS countdown
        # Le système de queues et les multiples workers géreront la distribution
        task = check_single_site.apply_async(
            args=[site.id],
            queue="standard",
            priority=5,
        )

        task_ids.append(task.id)

        db.session.add(TaskRecord(task_id=task.id, user_id=user_id))

        # Log tous les 25 sites
        if (i + 1) % 25 == 0:
            print(f"  ⏳ {i + 1}/{total_sites} tâches planifiées...")

    db.session.commit()

    print(f"✅ {len(task_ids)} tâches lancées ({skipped} sites ignorés).")
    print(f"🔥 Mode: {'STANDARD'}")

    # Snapshot des stats
    from services.stats_service import save_stats_snapshot

    save_stats_snapshot(user_id)
    

    return {
        "user_id": user_id,
        "total_sites": total_sites,
        "planned_tasks": len(task_ids),
        "skipped_sites": skipped,
        "task_ids": task_ids,
        "mode": "standard",
    }


@celery.task(name="tasks.check_all_sites_weekly")
def check_all_sites_weekly():
    """Vérification hebdomadaire automatique

    🎯 OPTIMISATION: Espacement entre utilisateurs réduit de 30min à 5min
    Les workers multiples peuvent gérer plusieurs utilisateurs simultanément
    """
    print("⏰ Début vérification hebdomadaire")

    users = User.query.all()
    total_users = len(users)

    print(f"👥 {total_users} utilisateurs trouvés")

    # 🚀 Espacement réduit : 5 minutes entre chaque utilisateur
    # Avec 3+ workers, plusieurs utilisateurs seront traités en parallèle
    for i, user in enumerate(users):
        countdown = i * 300  # 300s = 5 minutes (au lieu de 30)

        print(
            f"📅 Vérification user {user.id} planifiée dans {countdown / 60:.0f} minutes"
        )

        check_all_user_sites.apply_async(
            args=[user.id],
            countdown=countdown,
            queue="weekly",  # Queue dédiée basse priorité
        )

    total_duration_hours = (total_users * 5) / 60
    print(f"✅ Vérifications lancées pour {total_users} utilisateurs")
    print(f"⏱️ Durée estimée totale: {total_duration_hours:.1f} heures")

    return {
        "total_users": total_users,
        "message": "Vérification hebdomadaire lancée",
        "estimated_duration_hours": total_duration_hours,
    }


@celery.task(name="tasks.check_task_status")
def check_task_status(task_id):
    """Vérifie le statut d'une tâche"""
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery)

    return {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.ready() else None,
        "traceback": result.traceback if result.failed() else None,
    }
