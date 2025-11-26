# librairie Flask
import asyncio
import time
from asyncio import Semaphore

import aiohttp
import requests
from aiohttp import ClientTimeout

# librairie SQLAlchemy
# à partir du fichier python database.py
from database import db
from models import Website

# Configuration des API
SECONDS_BETWEEN_REQUESTS = 150  # temps d'attente entre les requêtes

SEMAPHORE_BABBAR = Semaphore(
    10
)  # Limiter le nombre de requêtes simultanées à l'API Babbar
MAX_CONCURRENT_REQUESTS = 10  # Nombre maximum de requêtes avant d'attendre
SEMAPHORE_YOURTEXTGURU = Semaphore(
    2
)  # Limiter le nombre de requêtes simultanées à l'API YourTextGuru
request_counter = 0  # Compteur de requêtes effectuées
AIOHTTP_TIMEOUT = ClientTimeout(total=30)  # Timeout total pour les requêtes aiohttp


# cherche un site dans la base de données avec une URL spécifiée, met à jour ses données avec les informations fournies, sauvegarde les changements dans la base de données,
# rafraîchit l'instance du site, et affiche un message indiquant le succès ou l'échec de la mise à jour.
def update_website_data(url_to_check, data):
    site = Website.query.filter_by(url=url_to_check).first()
    if site:
        site.page_value = data.get("pageValue", 0)
        site.page_trust = data.get("pageTrust", 0)
        site.bas = data.get("babbarAuthorityScore", 0)
        site.backlinks_external = data.get("backlinksExternal", 0)
        site.num_outlinks_ext = data.get("numOutLinksExt", 0)

        db.session.commit()
        db.session.refresh(site)
        print(f"Données mises à jour avec succès pour {url_to_check}")
    else:
        print(f"Aucun site trouvé pour l'URL {url_to_check}")


# Api babbar.tech
# envoie une requête POST à l'API Babbar pour récupérer des données pour une URL spécifiée. Elle gère les différentes situations de réponse (réussie, échec)
# et les exceptions liées à la requête. Si elle est en mode asynchrone, elle attend une période définie avant de se terminer.
# La fonction imprime également divers messages dans la console pour suivre le processus.


def fetch_url_data(url_to_check, async_mode=True):
    global request_counter

    payload = {"url": url_to_check}
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv",
    }

    try:
        response = requests.post(
            "https://www.babbar.tech/api/url/overview/main",
            json=payload,
            headers=headers,
        )
        print(f"Statut de la réponse de l'API : {response.status_code}")

        if response.status_code == 200:
            print("Raw response content:", response.text)
            try:
                data = response.json()
                print(f"Données reçues de l'API pour {url_to_check}: {data}")

                #update_website_data(url_to_check, data)
                #db.session.commit()
                #site = Website.query.filter_by(url=url_to_check).first()
                #db.session.refresh(site)
                return data

            except ValueError:
                print(f"La réponse ne contient pas de JSON valide: {response.text}")
        else:
            print(
                f"Échec de la récupération des données pour {url_to_check} : {response.status_code}"
            )
            print("Response text:", response.text)

        request_counter += 1

        if not async_mode and request_counter >= MAX_CONCURRENT_REQUESTS:
            time.sleep(SECONDS_BETWEEN_REQUESTS)
            request_counter = 0

    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête pour {url_to_check} : {e}")


# cette fonction asynchrone est utilisée pour récupérer des données sur une URL depuis l'API de Babbar Tech de manière asynchrone,
# mettre à jour les informations du site dans la base de données, et committer les changements
async def fetch_url_data_async(urls_to_check):
    payload_list = [{"url": url} for url in urls_to_check]
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv",
    }

    batch_size = 5
    for i in range(0, len(payload_list), batch_size):
        batch_payload = payload_list[i : i + batch_size]
        async with aiohttp.ClientSession() as session:
            for payload in batch_payload:
                async with session.post(
                    "https://www.babbar.tech/api/url/overview/main",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        update_website_data(payload["url"], data)
                        db.session.commit()
                    else:
                        print(
                            f"Échec de la récupération des données pour {payload['url']} : {response.status}"
                        )
            await asyncio.sleep(150)  # Attendre 1 minute entre les lots


# 3) Récupération Babbar AVANT commit
"""try:
    babbar_data = fetch_url_data(site.url, async_mode=False)
    print(f"🔥 Données Babbar reçues pour {site.url}: {babbar_data}")

    # 📌 Mettre à jour le site avec les données Babbar
    if babbar_data:
        site.page_value = babbar_data.get("pageValue")
        site.page_trust = babbar_data.get("pageTrust")
        site.bas = babbar_data.get("babbarAuthorityScore")
        site.backlinks_external = babbar_data.get("backlinksExternal")
        site.num_outlinks_ext = babbar_data.get("numOutLinksExt")"""
