# librairie Flask
from asyncio import Semaphore

from aiohttp import ClientTimeout

# librairie SQLAlchemy

# à partir du fichier python database.py

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


# cette fonction est utilisée pour vérifier si une URL donnée est indexée sur Google en utilisant l'API SERPAPI.
async def check_google_indexation(session, url):
    query = f"site:{url}"
    params = {
        "engine": "google",
        "q": query,
        "location": "France",
        "api_key": "2d616e924f3b0d90bdcecdae5de3ab32605022360f9598b9c6d25e5a0ed80db5",
    }
    print(f"Envoi de la requête SERPAPI pour l'URL: {url}")
    try:
        async with session.get(
            "https://serpapi.com/search.json", params=params
        ) as response:
            print(
                f"Réponse reçue de SERPAPI pour l'URL {url}: Status {response.status}"
            )

            if response.status == 200:
                data = await response.json()
                print(f"Réponse SERPAPI pour {url}: {data}")
                print(
                    f"Premières données reçues de SERPAPI pour {url}: {data['organic_results'][:1]}"
                )
                is_indexed = (
                    "Indexé !"
                    if any(
                        url in result.get("link", "")
                        for result in data.get("organic_results", [])
                    )
                    else "Non indexé"
                )
                print(f"Résultat d'indexation pour {url}: {is_indexed}")
                return is_indexed
            else:
                print(
                    f"Erreur de réponse de SERPAPI pour {url}: Status {response.status}"
                )
    except Exception as e:
        print(f"Exception lors de la vérification de l'indexation pour {url}: {e}")
        is_indexed = "Non indexé"
        return is_indexed