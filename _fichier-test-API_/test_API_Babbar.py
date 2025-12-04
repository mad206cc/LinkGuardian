import requests

url_to_check = 'https://www.magazette.fr/guide-ultime-pour-voyager-a-moindre-cout/'
api_url = 'https://www.babbar.tech/api/url/overview/main'
api_token = 'lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv'

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_token}"
}

payload = {
    "url": url_to_check
}

response = requests.post(api_url, json=payload, headers=headers)

if response.status_code == 200:
    data = response.json()
    print(response.text)
    print(response.status_code)

    # Traitez ici les données reçues
else:
    # Gérez ici les erreurs
    print(response.text)
    print(response.status_code)

    print(f"Erreur {response.status_code}: {response.text}")
