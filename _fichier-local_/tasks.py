import asyncio
from datetime import datetime

from aiohttp import ClientError, ClientSession

# Importer Celery depuis le fichier dédié
from celery_app import celery
from models import User, Website, db
from services.api_babbar import fetch_url_data

# 🔧 CONFIGURATION DES LIMITES D'API
API_RATE_LIMITS = {
    "babbar": {"calls_per_minute": 30, "retry_after": 60},
    "google": {"calls_per_minute": 30, "retry_after": 60},
    "default": {"calls_per_minute": 30, "retry_after": 60},
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
    """Traite la vérification d'un site de manière asynchrone
    
    ⚠️ Cette fonction doit être appelée depuis un contexte Flask (tâche Celery)
    pour avoir accès à db.session
    """
    # Importer ici pour éviter les imports circulaires
    from services.api_serpapi import check_google_indexation
    from services.check_service import check_link_presence_and_follow_status_async

    # Récupérer le site depuis la DB (dans le contexte Flask de la tâche)
    site = Website.query.get(site_id)
    if not site:
        return {"success": False, "site_id": site_id, "error": "Site non trouvé"}

    async with ClientSession() as session:
        try:
            # Vérifications
            link_data = await check_link_presence_and_follow_status_async(
                session, site.url, site.link_to_check, site.anchor_text
            )
            index_status = await check_google_indexation(session, site.url)

            link_present, anchor_present, follow_status, status_code = link_data
            site.status_code = status_code

            # Sauvegarde de l'historique (ancien état)
            old_site = Website(
                url=site.url,
                link_to_check=site.link_to_check,
                anchor_text=site.anchor_text,
                link_status=site.link_status,
                link_follow_status=site.link_follow_status,
                anchor_status=site.anchor_status,
                google_index_status=site.google_index_status,
                source_plateforme=site.source_plateforme,
                last_checked=site.last_checked,
                user_id=site.user_id,
                page_value=site.page_value,
                page_trust=site.page_trust,
                bas=site.bas,
                backlinks_external=site.backlinks_external,
                num_outlinks_ext=site.num_outlinks_ext,
                status_code=site.status_code,
                tag=site.tag,
            )

            # Mise à jour du site
            site.link_status = "Lien présent" if link_present else "URL non présente"
            site.link_follow_status = follow_status if link_present else None
            site.anchor_status = (
                "Ancre présente" if anchor_present else "Ancre manquante"
            )
            site.google_index_status = index_status

            if site.first_checked is None:
                site.first_checked = datetime.now()

            site.last_checked = datetime.now()

            # Données Babbar avec gestion des erreurs API
            try:
                fetch_url_data(site.url, async_mode=False)
            except Exception as e:
                error_msg = str(e).lower()
                # Détecter les erreurs de rate limit
                if (
                    "rate limit" in error_msg
                    or "429" in error_msg
                    or "too many" in error_msg
                ):
                    print(f"⚠️ Rate limit Babbar pour {site.url}")
                    raise APIRateLimitError("babbar", retry_after=60)
                else:
                    print(f"⚠️ Erreur Babbar pour {site.url}: {e}")

            # Sauvegarde en base
            db.session.commit()
            db.session.add(old_site)
            db.session.commit()

            return {
                "success": True,
                "site_id": site.id,
                "url": site.url,
                "link_status": site.link_status,
                "index_status": site.google_index_status,
            }

        except APIRateLimitError:
            # Propager l'erreur pour le retry
            raise
        except Exception as e:
            print(f"❌ Erreur traitement de {site.url}: {e}")
            db.session.rollback()
            raise


@celery.task(
    name="tasks.check_single_site",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    rate_limit="15/m",
    autoretry_for=(APIRateLimitError, ClientError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def check_single_site(self, site_id):
    """Vérifie un seul site avec gestion intelligente des retries"""
    try:
        print(f"🔍 Vérification du site ID: {site_id}")

        site = Website.query.get(site_id)
        if not site:
            # 🚫 Site supprimé : on stoppe immédiatement sans retry
            print(f"⏭️  Site {site_id} ignoré (supprimé) — tâche annulée.")
            self.request.callbacks = None
            self.request.errbacks = None
            return {"success": True, "skipped": True, "site_id": site_id}

        # Exécuter la vérification
        result = asyncio.run(process_site_async(site_id))
        print(f"✅ Site {site_id} vérifié avec succès")
        return result

    except APIRateLimitError as exc:
        retry_after = exc.retry_after
        print(f"⏳ Rate limit atteint pour site {site_id}. Retry dans {retry_after}s.")
        raise self.retry(exc=exc, countdown=retry_after)

    except ClientError as exc:
        print(f"🔄 Erreur réseau pour site {site_id}. Retry automatique...")
        raise self.retry(exc=exc)

    except Exception as exc:
        # ⚙️ Seulement retry si le site existe encore
        site = Website.query.get(site_id)
        if site and self.request.retries < self.max_retries:
            print(f"⚠️ Erreur pour site {site_id}: {exc}. Retry...")
            raise self.retry(exc=exc)
        else:
            print(f"❌ Tâche arrêtée définitivement pour site {site_id}.")
            return {
                "success": False,
                "site_id": site_id,
                "error": str(exc),
                "stopped": True,
            }


@celery.task(
    name="tasks.check_all_user_sites",
    rate_limit="2/m",  # Max 2 vérifications complètes par minute
)
def check_all_user_sites(user_id):
    """Vérifie tous les sites d'un utilisateur avec espacement intelligent"""
    print(f"🔄 Début vérification pour l'utilisateur {user_id}")

    sites = Website.query.filter_by(user_id=user_id).all()
    total_sites = len(sites)
    print(f"📊 {total_sites} sites à vérifier")

    task_ids = []
    skipped = 0

    for i, site in enumerate(sites):
        # 🧹 Vérifie que le site est encore valide
        if not site or not site.url:
            skipped += 1
            continue

        countdown = i * 4  # Délai progressif
        task = check_single_site.apply_async(args=[site.id], countdown=countdown)
        task_ids.append(task.id)

        if (i + 1) % 10 == 0:
            print(f"  ⏳ {i + 1}/{total_sites} tâches planifiées...")

    print(
        f"✅ {len(task_ids)} tâches planifiées avec délai progressif ({skipped} sites ignorés)."
    )

    from services.stats_service import save_stats_snapshot

    save_stats_snapshot(user_id)

    return {
        "user_id": user_id,
        "total_sites": total_sites,
        "planned_tasks": len(task_ids),
        "skipped_sites": skipped,
        "task_ids": task_ids,
        "estimated_duration_minutes": (total_sites * 6) / 60,
    }


@celery.task(name="tasks.check_all_sites_weekly")
def check_all_sites_weekly():
    """Vérification hebdomadaire automatique avec espacement entre utilisateurs"""
    print("⏰ Début vérification hebdomadaire")

    users = User.query.all()
    total_users = len(users)

    print(f"👥 {total_users} utilisateurs trouvés")

    # Lancer les vérifications avec 30 minutes d'écart entre chaque utilisateur
    for i, user in enumerate(users):
        countdown = i * 1800  # 1800s = 30 minutes

        print(
            f"📅 Vérification user {user.id} planifiée dans {countdown / 60:.0f} minutes"
        )

        check_all_user_sites.apply_async(
            args=[user.id],
            countdown=countdown,
        )

    total_duration_hours = (total_users * 30) / 60
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
