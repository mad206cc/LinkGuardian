# librairie Flask
import asyncio
from asyncio import Semaphore
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
import requests
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from serpapi import GoogleSearch

# librairie SQLAlchemy
# à partir du fichier python database.py
from database import db
from models import Website, Configuration
from services.api_babbar import fetch_url_data
from services.utils_service import check_anchor_presence


SEMAPHORE_BABBAR = Semaphore(
    10
)  # Limiter le nombre de requêtes simultanées à l'API Babbar
MAX_CONCURRENT_REQUESTS = 10  # Nombre maximum de requêtes avant d'attendre
SEMAPHORE_YOURTEXTGURU = Semaphore(
    2
)  # Limiter le nombre de requêtes simultanées à l'API YourTextGuru
request_counter = 0  # Compteur de requêtes effectuées
AIOHTTP_TIMEOUT = ClientTimeout(total=30)  # Timeout total pour les requêtes aiohttp

def get_babbar_key():
    config = Configuration.query.first()
    return config.babbar_api_key if config else None

def get_serpapi_key():
    config = Configuration.query.first()
    return config.serpapi_key if config else None


async def fetch_status(session, url):
    """C'est une fonction asynchrone (pour éviter de blocker le thread principal) pour la vérification des URLs des sites web,
    pour savoir si le site est joignable ou pas. Elle effectue de manière asynchrone une requête HTTP GET vers une URL donnée, gère
    les différents scénarios de réussite, d'expiration du délai et d'erreur de client, et retourne un tuple contenant l'URL et un
    statut ou un message d'erreur approprié.

    Returns:
        tuple(str, str): Retourne l'URL du lien, et le statut de la réponse ou un message d'erreur.
    """

    try:
        async with (
            session.get(url, timeout=10) as response
        ):  # Effectue une requête GET asynchrone avec un délai d'attente de 10 secondes
            return url, response.status
    except asyncio.TimeoutError:  # Gère le cas où la requête dépasse le délai d'attente
        return url, "Timeout"
    except aiohttp.ClientError as e:  # Gère les erreurs liées au client HTTP
        return url, f"Erreur Client: {e}"
    except Exception as e:
        return url, f"Erreur Générale: {e}"  # Gère toute autre exception générale


async def check_websites(websites, max_concurrent_tasks=50):
    """Cette fonction permet de vérifier de manière asynchrone le statut des URLs des sites web spécifiés en utilisant
    aiohttp avec une gestion du nombre de requêtes simultanées.

    Args:
        websites (list): Liste de sites web à vérifier

    Returns:
        list: Les résultats sont renvoyés sous la forme d'une liste de tuples contenant l'URL et le statut ou le
        message d'erreur.
    """

    semaphore = Semaphore(max_concurrent_tasks)
    timeout = aiohttp.ClientTimeout(total=30)

    async def fetch_with_limit(url):
        async with semaphore:
            return await fetch_status(session, url)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [fetch_with_limit(site.url) for site in websites]
        print("URLs à vérifier:", [site.url for site in websites])
        results = await asyncio.gather(*tasks)
        return results


# permet d'effectuer de manière asynchrone des requêtes HTTP GET vers une URL avec une gestion des tentatives de réessai en cas d'erreur de type asyncio.TimeoutError ou aiohttp.ClientError. Si la requête réussit,
# l'URL et le statut de la réponse sont renvoyés. Si toutes les tentatives échouent, l'URL et un message d'échec spécifique sont renvoyés.
async def fetch_with_retry(session, url, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=10) as response:
                return url, response.status
        except (asyncio.TimeoutError, aiohttp.ClientError):
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            else:
                return url, "Échec après plusieurs tentatives"


# Function pour récupérer les liens si follow ou nofollow
# En résumé, la fonction permet de vérifier si un lien spécifié est présent dans le contenu HTML d'une page
# et fournit également le statut de suivi de ce lien (suivi ou non-suivi).
def check_link_presence_and_follow_status(html_content, link_to_check):
    soup = BeautifulSoup(html_content, "html.parser")
    parsed_url = urlparse(link_to_check)
    slug = parsed_url.path

    for link in soup.find_all("a", href=True):
        href = link["href"]
        parsed_href = urlparse(href)
        href_slug = parsed_href.path

        if href == link_to_check or href_slug == slug:
            follow_status = (
                "follow"
                if "rel" not in link.attrs or "nofollow" not in link["rel"]
                else "nofollow"
            )
            return True, follow_status

    return False, None


# la fonction permet de vérifier de manière asynchrone si un lien spécifié est présent dans le contenu HTML d'une page
# et fournit également le statut de suivi de ce lien (suivi ou non-suivi).
async def check_link_presence_and_follow_status_async(
    session, url, link_to_check, anchor_text
):
    try:
        async with session.get(url, allow_redirects=True) as response:
            status_code = response.status  # ✅ Ajout ici
            if status_code == 200:
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")
                parsed_url = urlparse(link_to_check)
                slug = parsed_url.path

                link_present = False
                follow_status = None
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    parsed_href = urlparse(href)
                    href_slug = parsed_href.path

                    if href == link_to_check or href_slug == slug:
                        link_present = True
                        follow_status = (
                            "follow"
                            if "rel" not in link.attrs or "nofollow" not in link["rel"]
                            else "nofollow"
                        )
                        break

                anchor_present = any(
                    anchor_text in link.text for link in soup.find_all("a")
                )

                # ✅ Retourne maintenant 4 valeurs
                return link_present, anchor_present, follow_status, status_code
            else:
                # Même en cas de 404, on retourne le code
                return False, False, None, status_code
    except Exception:
        return False, False, None, None  # Code HTTP inconnu


# cette fonction asynchrone permet de vérifier la présence d'un lien et d'un texte d'ancre spécifiés dans le contenu HTML d'une page,
# ainsi que de récupérer le statut de suivi du lien.
async def check_link_and_anchor(session, url, link_to_check, anchor_text):
    try:
        async with session.get(url, allow_redirects=True) as response:
            print(f"Réponse obtenue pour {url}: {response.status}")
            if response.status == 200:
                content = await response.text()
                print(f"Contenu récupéré pour {url}")
                print(f"Recherche du lien {link_to_check} et de l'ancre {anchor_text}")

                print(f"Contenu récupéré pour {url}")
                soup = BeautifulSoup(content, "html.parser")

                link_present, follow_status = check_link_presence_and_follow_status(
                    soup, link_to_check
                )
                print(
                    f"Statut du lien pour {url}: {link_present}, Follow: {follow_status}"
                )
                anchor_present = any(
                    anchor_text in link.text for link in soup.find_all("a")
                )

                return link_present, anchor_present, follow_status
            else:
                print(f"Échec de la réponse HTTP pour {url}: {response.status}")
    except Exception as e:
        print(f"Erreur lors de la récupération de {url}: {e}")
        return False, False, None


#  effectue plusieurs vérifications sur un site web, notamment la récupération du code de statut HTTP, la vérification de la présence d'un lien et d'une ancre
# dans le contenu HTML, la vérification de l'indexation Google via SERPAPI, et la mise à jour des données dans la base de données. Elle gère également les erreurs
# potentielles liées à la requête et met à jour les données Babbar de manière synchrone si la fonction n'est pas en mode asynchrone
def perform_check_status(site_id):
    site = Website.query.get(site_id)
    if site:
        try:
            response = requests.get(site.url, allow_redirects=True)
            site.status_code = response.status_code

            html_content = response.content
            link_present, follow_status = check_link_presence_and_follow_status(
                html_content, site.link_to_check
            )
            anchor_present = check_anchor_presence(response.content, site.anchor_text)

            site.link_status = "Lien présent" if link_present else "Lien absent"
            site.anchor_status = "Ancre présente" if anchor_present else "Ancre absente"
            site.link_follow_status = follow_status if link_present else None
            site.last_checked = datetime.now()
            params = {
                "engine": "google",
                "q": f"site:{site.url}",
                "location": "France",
                "api_key": get_serpapi_key,
            }
            search = GoogleSearch(params)
            results = search.get_dict()
            organic_results = results.get("organic_results", [])
            site.google_index_status = (
                "Indexé !"
                if any(site.url in result.get("link", "") for result in organic_results)
                else "Non indexé"
            )
            db.session.commit()

            site = Website.query.get(site.id)
            
            return response
        
        except RequestException:
            site.status_code = None
            site.link_status = "Erreur de vérification"
            site.anchor_status = "Erreur de vérification"
            site.last_checked = datetime.now()
            fetch_url_data(site.url, async_mode=False)
            db.session.commit()


# Fonction pour vérifier les sites et mettre à jour les résultats dans la base de données depuis le fichier excel
# vérifier les sites web de manière asynchrone, obtenir leurs statuts et mettre à jour les informations dans la base de données en fonction des résultats de la vérification
async def check_and_update_sites(sites):
    results = await check_websites(sites)
    for url, status in results:
        site = next((site for site in sites if site.url == url), None)
        if site:
            site.status_code = status
            if status == 200:
                link_present, anchor_present = await check_link_and_anchor(
                    site.url, site.link_to_check, site.anchor_text
                )
                site.link_status = "Lien présent" if link_present else "Lien absent"
                site.anchor_status = (
                    "Ancre présente" if anchor_present else "Ancre manquante"
                )
            else:
                site.link_status = "Erreur de vérification"
                site.anchor_status = "Erreur de vérification"
            site.last_checked = datetime.now()
            db.session.commit()


# effectue des appels asynchrones à l'API Babbar, vérifie la présence d'un lien et d'une ancre de manière asynchrone, et commet les changements dans la base de données de manière
# asynchrone. Elle utilise la gestion des exceptions pour gérer les erreurs potentielles lors des appels asynchrones.
async def check_and_update_website_data(session, website):
    print("test NOONE TESTTTTT")
    async with SEMAPHORE_BABBAR:
        try:
            response = await session.post(
                "https://www.babbar.tech/api/url/overview/main",
                json={"url": website.url},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + get_babbar_key(),
                },
            )

            if response.status == 200:
                data = await response.json()
                website.page_value = data.get("pageValue", 0)
                website.page_trust = data.get("pageTrust", 0)
                website.bas = data.get("babbarAuthorityScore", 0)
                website.backlinks_external = data.get("backlinksExternal", 0)
                website.num_outlinks_ext = data.get("numOutLinksExt", 0)

                print("j'affiche la réponse status", response.status)
                print(
                    "***",
                    website.page_value,
                    website.page_trust,
                    website.bas,
                    website.backlinks_external,
                    website.num_outlinks_ext + "*****************",
                )
            else:
                print(
                    f"Erreur avec l'API Babbar pour le site {website.url}: {response.status}"
                )
        except Exception as e:
            print(
                f"Erreur lors de l'appel à l'API Babbar pour le site {website.url}: {e}"
            )

    # Ici, vous vérifiez la présence du lien et de l'ancre
    # Cette partie du code serait similaire à ce que vous avez déjà pour les fonctions synchrones
    # mais adaptée pour utiliser aiohttp et asynchrone
    try:
        response = await session.get(website.url)
        if response.status == 200:
            content = await response.text()
            soup = BeautifulSoup(content, "html.parser")
            link_present = any(
                link["href"] == website.link_to_check
                for link in soup.find_all("a", href=True)
            )
            anchor_present = any(
                website.anchor_text in link.text for link in soup.find_all("a")
            )
            website.link_status = "Lien présent" if link_present else "Lien absent"
            website.anchor_status = (
                "Ancre présente" if anchor_present else "Ancre absente"
            )
        else:
            print(
                f"Erreur de réponse HTTP pour le site {website.url}: {response.status}"
            )
    except Exception as e:
        print(f"Erreur lors de la récupération du site {website.url}: {e}")

    asyncio.get_event_loop().run_in_executor(None, db.session.commit)
