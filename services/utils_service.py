# librairie Flask
import random
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from sqlalchemy import literal

# librairie SQLAlchemy
# à partir du fichier python database.py
from models import Tag, db


# la fonction check_link_presence détermine la présence d'un lien spécifié dans le contenu HTML d'une page web
def check_link_presence(html_content, link_to_check):
    soup = BeautifulSoup(html_content, "html.parser")
    return any(link["href"] == link_to_check for link in soup.find_all("a", href=True))


# la fonction check_anchor_presence détermine la présence d'un texte d'ancre spécifié dans le contenu HTML d'une page web.
def check_anchor_presence(html_content, anchor_text):
    soup = BeautifulSoup(html_content, "html.parser")
    return any(anchor_text in link.text for link in soup.find_all("a"))


def couleur_aleatoire_unique():
    """Génère une couleur hexadécimale aléatoire unique"""
    couleur = "#{:06x}".format(random.randint(0, 0xFFFFFF))

    # ✅ CORRECT : Utiliser literal() pour indiquer que c'est une valeur littérale
    while Tag.query.filter(Tag.couleur == literal(couleur)).first():
        couleur = "#{:06x}".format(random.randint(0, 0xFFFFFF))

    return couleur


# cette fonction est utilisée dans les templates Flask comme filtre pour attribuer une couleur spécifique à un tag donné.
# Si le tag n'est pas dans la liste prédéfinie, la fonction renvoie une couleur par défaut
def tag_color(tag_name):
    """
    Retourne la couleur associée à un tag.
    Si le tag n'existe pas, renvoie noir par défaut.
    """
    if not tag_name:
        return "#000000"

    # Normalise le tag_name pour la recherche dans la base de données
    tag = Tag.query.filter(db.func.lower(Tag.valeur) == tag_name.lower()).first()
    return tag.couleur if tag else "#000000"  # Noir par défaut si aucun tag trouvé


def extract_domain_tag(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc
