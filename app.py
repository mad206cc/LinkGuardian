from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user, login_required
from database import db
from flask_migrate import Migrate
import requests
import urllib.parse
from models import Website
from bs4 import BeautifulSoup
from datetime import datetime,timedelta
from flask_login import LoginManager
from flask import render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, current_user
from models import User, db, Configuration
from models import Tag, db
from models import Source, db
import pandas as pd
import aiohttp
import asyncio
from asyncio import Semaphore
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import logout_user
from requests.exceptions import RequestException
from urllib.parse import urlparse
from serpapi import GoogleSearch
from flask import jsonify, request
from queue import Queue
import time
from threading import Thread
from aiohttp import ClientSession, ClientTimeout
from asyncio import Semaphore
import json
from flask import jsonify
from sqlalchemy import func, desc
import pika
import random
from sqlalchemy import case
from copy import deepcopy
from sqlalchemy import and_
from sqlalchemy import or_
import re
from flask_executor import Executor



SECONDS_BETWEEN_REQUESTS = 150


SEMAPHORE_BABBAR = Semaphore(10)  
MAX_CONCURRENT_REQUESTS = 10
SEMAPHORE_YOURTEXTGURU = Semaphore(2)  
request_counter = 0
AIOHTTP_TIMEOUT = ClientTimeout(total=30)




app = Flask(__name__)
app.secret_key = 'dfsdfsdfdfsdfsdfsdfsdfsdfsdfsdffsd' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.login_view = 'login'  
login_manager.init_app(app)
executor = Executor(app)




# permet de mettre à jour le nom de plateforme d'un site web spécifique en utilisant une requête POST avec les données appropriées.
# La fonction renvoie une réponse JSON pour indiquer le résultat de l'opération.
@app.route('/update-platform-name', methods=['POST'])
def update_platform_name():
    data = request.json
    site = Website.query.get(data['siteId'])
    if site:
        site.platform_name = data['platformName']
        db.session.commit()
        return jsonify({"message": "Mise à jour réussie"})
    return jsonify({"message": "Site non trouvé"}), 404



# Fonctions asynchrones pour la vérification des liens
# effectue de manière asynchrone une requête HTTP GET vers une URL donnée, gère les différents scénarios de réussite, 
# d'expiration du délai et d'erreur de client, et retourne un tuple contenant l'URL et un statut ou un message d'erreur approprié.
async def fetch_status(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            return url, response.status
    except asyncio.TimeoutError:
        return url, 'Timeout'
    except aiohttp.ClientError as e:
        return url, f'Erreur Client: {e}'
    except Exception as e: 
        return url, f'Erreur Générale: {e}'
    


# permet de vérifier de manière asynchrone le statut des URLs des sites web spécifiés en utilisant aiohttp avec une gestion du nombre de requêtes simultanées.
# Les résultats sont renvoyés sous la forme d'une liste de tuples contenant l'URL et le statut ou le message d'erreur.    
async def check_websites(websites, max_concurrent_tasks=50):
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
                return url, 'Échec après plusieurs tentatives'



"""*******************************************************************RECHERCHE******************************************************************"""
# cherche un site dans la base de données avec une URL spécifiée, met à jour ses données avec les informations fournies, sauvegarde les changements dans la base de données,
# rafraîchit l'instance du site, et affiche un message indiquant le succès ou l'échec de la mise à jour.                        
def update_website_data(url_to_check, data):
    site = Website.query.filter_by(url=url_to_check).first()
    if site:
       
        site.page_value = data.get('pageValue', 0)
        site.page_trust = data.get('pageTrust', 0)
        site.bas = data.get('babbarAuthorityScore', 0)
        site.backlinks_external = data.get('backlinksExternal', 0)
        site.num_outlinks_ext = data.get('numOutLinksExt', 0)
        
       
        db.session.commit()
        db.session.refresh(site)
        print(f"Données mises à jour avec succès pour {url_to_check}")
    else:
        print(f"Aucun site trouvé pour l'URL {url_to_check}")


#  parcourt la liste des résultats (URL, statut) et met à jour le champ status_code dans la base de données pour chaque site correspondant à l'URL fournie. 
# Elle commit ensuite les changements dans la base de données.
def update_website_statuses(results):
    for url, status in results:
        website = Website.query.filter_by(url=url).first()
        if website:
            website.status_code = status
            db.session.commit()
url_queue = Queue()



#Api babbar.tech
# envoie une requête POST à l'API Babbar pour récupérer des données pour une URL spécifiée. Elle gère les différentes situations de réponse (réussie, échec)
# et les exceptions liées à la requête. Si elle est en mode asynchrone, elle attend une période définie avant de se terminer. 
# La fonction imprime également divers messages dans la console pour suivre le processus.


def fetch_url_data(url_to_check, async_mode=True):
    global request_counter 

    payload = {"url": url_to_check}
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv"
    }

    try:
        response = requests.post('https://www.babbar.tech/api/url/overview/main', json=payload, headers=headers)
        print(f"Statut de la réponse de l'API : {response.status_code}")

        if response.status_code == 200:
            print("Raw response content:", response.text)
            try:
                data = response.json()
                print(f"Données reçues de l'API pour {url_to_check}: {data}")
                update_website_data(url_to_check, data)
                db.session.commit()
                site = Website.query.filter_by(url=url_to_check).first()
                db.session.refresh(site)
            except ValueError:
                print(f"La réponse ne contient pas de JSON valide: {response.text}")
        else:
            print(f"Échec de la récupération des données pour {url_to_check} : {response.status_code}")
            print("Response text:", response.text)

        request_counter += 1

        if not async_mode and request_counter >= MAX_CONCURRENT_REQUESTS:
            time.sleep(SECONDS_BETWEEN_REQUESTS)
            request_counter = 0

    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête pour {url_to_check} : {e}")



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
            link_present, follow_status = check_link_presence_and_follow_status(html_content, site.link_to_check)
            anchor_present = check_anchor_presence(response.content, site.anchor_text)

            site.link_status = "Lien présent" if link_present else "Lien absent"
            site.anchor_status = "Ancre présente" if anchor_present else "Ancre absente"
            site.link_follow_status = follow_status if link_present else None
            site.last_checked = datetime.utcnow()
            params = {
                "engine": "google",
                "q": f"site:{site.url}",
                "location": "France",
                "api_key": "2d616e924f3b0d90bdcecdae5de3ab32605022360f9598b9c6d25e5a0ed80db5"
            }
            search = GoogleSearch(params)
            results = search.get_dict()
            organic_results = results.get("organic_results", [])
            site.google_index_status = "Indexé !" if any(site.url in result.get("link", "") for result in organic_results) else "Non indexé"
            db.session.commit()
        except RequestException as e:
            site.status_code = None
            site.link_status = "Erreur de vérification"
            site.anchor_status = "Erreur de vérification"
            site.last_checked = datetime.utcnow()
            fetch_url_data(site.url, async_mode=False)
            db.session.commit()


#  prend un ID d'utilisateur, le convertit en entier, puis utilise la session de base de données pour récupérer l'objet utilisateur
# correspondant à partir de la base de données. Cette fonction est utilisée par Flask-Login pour charger un utilisateur lorsqu'il est nécessaire,
# par exemple, lorsqu'un utilisateur est enregistré dans la session et effectue des requêtes ultérieures
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


#gère l'inscription des utilisateurs en vérifiant si l'utilisateur est déjà connecté, en traitant les soumissions de formulaires pour créer de nouveaux utilisateurs, 
# et en affichant le formulaire d'inscription dans le cas d'une requête GET. Elle utilise Flask-Login pour vérifier l'état de connexion de l'utilisateur actuel, 
# SQLAlchemy pour interagir avec la base de données, et des messages flash pour informer l'utilisateur sur le succès ou l'échec de l'inscription.

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Ce nom d’utilisateur existe déjà.')
            return redirect(url_for('signup'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Inscription réussie.')
        return redirect(url_for('login'))

    return render_template('signup.html')


# effectue des appels asynchrones à l'API Babbar, vérifie la présence d'un lien et d'une ancre de manière asynchrone, et commet les changements dans la base de données de manière 
# asynchrone. Elle utilise la gestion des exceptions pour gérer les erreurs potentielles lors des appels asynchrones.
async def check_and_update_website_data(session, website):
    print("test NOONE TESTTTTT")
    async with SEMAPHORE_BABBAR:  
        
        try:
            response = await session.post(
                'https://www.babbar.tech/api/url/overview/main',
                json={"url": website.url},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv"
                }
            )

            if response.status == 200:
                data = await response.json()
                website.page_value = data.get('pageValue', 0)
                website.page_trust = data.get('pageTrust', 0)
                website.bas = data.get('babbarAuthorityScore', 0)
                website.backlinks_external = data.get('backlinksExternal', 0)
                website.num_outlinks_ext = data.get('numOutLinksExt', 0)
                
                print("j'affiche la réponse status", response.status)
                print("***",website.page_value, website.page_trust, website.bas, website.backlinks_external, website.num_outlinks_ext+"*****************")
            else:
               
                print(f"Erreur avec l'API Babbar pour le site {website.url}: {response.status}")
        except Exception as e:
           
            print(f"Erreur lors de l'appel à l'API Babbar pour le site {website.url}: {e}")

    # Ici, vous vérifiez la présence du lien et de l'ancre
    # Cette partie du code serait similaire à ce que vous avez déjà pour les fonctions synchrones
    # mais adaptée pour utiliser aiohttp et asynchrone
    try:
        response = await session.get(website.url)
        if response.status == 200:
            content = await response.text()
            soup = BeautifulSoup(content, 'html.parser')
            link_present = any(link['href'] == website.link_to_check for link in soup.find_all('a', href=True))
            anchor_present = any(website.anchor_text in link.text for link in soup.find_all('a'))
            website.link_status = "Lien présent" if link_present else "Lien absent"
            website.anchor_status = "Ancre présente" if anchor_present else "Ancre absente"
        else:
           
            print(f"Erreur de réponse HTTP pour le site {website.url}: {response.status}")
    except Exception as e:
       
        print(f"Erreur lors de la récupération du site {website.url}: {e}")

    asyncio.get_event_loop().run_in_executor(None, db.session.commit)



# gère l'authentification des utilisateurs en vérifiant si un utilisateur est déjà connecté, en traitant les soumissions de formulaires pour vérifier les informations d'identification,
# et en affichant le formulaire de connexion dans le cas d'une requête GET. Elle utilise Flask-Login pour gérer l'état de connexion de l'utilisateur,
# SQLAlchemy pour interagir avec la base de données, et des messages flash pour informer l'utilisateur sur le succès ou l'échec de l'authentification.
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))

        flash('Nom d’utilisateur ou mot de passe incorrect.')

    return render_template('login.html')


#Function pour récupérer les liens si follow ou nofollow
#En résumé, la fonction permet de vérifier si un lien spécifié est présent dans le contenu HTML d'une page
# et fournit également le statut de suivi de ce lien (suivi ou non-suivi).
def check_link_presence_and_follow_status(html_content, link_to_check):
    soup = BeautifulSoup(html_content, 'html.parser')
    parsed_url = urlparse(link_to_check)
    slug = parsed_url.path

    for link in soup.find_all('a', href=True):
        href = link['href']
        parsed_href = urlparse(href)
        href_slug = parsed_href.path

        if href == link_to_check or href_slug == slug:
            follow_status = 'follow' if 'rel' not in link.attrs or 'nofollow' not in link['rel'] else 'nofollow'
            return True, follow_status

    return False, None


# la fonction permet de vérifier de manière asynchrone si un lien spécifié est présent dans le contenu HTML d'une page
# et fournit également le statut de suivi de ce lien (suivi ou non-suivi).
async def check_link_presence_and_follow_status_async(session, url, link_to_check, anchor_text):
    try:
        async with session.get(url, allow_redirects=True) as response:
            if response.status == 200:
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                parsed_url = urlparse(link_to_check)
                slug = parsed_url.path

                link_present = False
                follow_status = None
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    parsed_href = urlparse(href)
                    href_slug = parsed_href.path

                    if href == link_to_check or href_slug == slug:
                        link_present = True
                        follow_status = 'follow' if 'rel' not in link.attrs or 'nofollow' not in link['rel'] else 'nofollow'
                        break 

                anchor_present = any(anchor_text in link.text for link in soup.find_all('a'))
                return link_present, anchor_present, follow_status
            else:
                return False, False, None
    except Exception as e:
        return False, False, None



# cette fonction est responsable de l'ajout d'un site à la base de données, avec des vérifications associées sur l'URL,
# le lien, le texte d'ancre, et le statut de suivi du lien.
@app.route('/add_site', methods=['POST'])
def add_site():
    url = request.form.get('url')
    tag = request.form.get('tag').lower()
    link_to_check = request.form.get('link_to_check')
    anchor_text = request.form.get('anchor_text')
    source_plateforme = request.form.get('source_plateforme')

    if url:
        try:
            response = requests.get(url)
            response.raise_for_status()  
            html_content = response.text

            
            link_present = check_link_presence(html_content, link_to_check)
            anchor_present = check_anchor_presence(html_content, anchor_text)
            link_present, follow_status = check_link_presence_and_follow_status(html_content, link_to_check)
            
            new_site = Website(
                url=url, tag=tag, link_to_check=link_to_check, anchor_text=anchor_text,
                source_plateforme=source_plateforme, user_id=current_user.id,
                link_status="Lien présent" if link_present else "Lien absent",
                anchor_status="Ancre présente" if anchor_present else "Ancre absente",
                link_follow_status=follow_status if link_present else None
                

            )
            db.session.add(new_site)
            db.session.commit()

            perform_check_status(new_site.id)

        except requests.RequestException as e:
            flash(f'Une erreur est survenue lors de la vérification de l\'URL : {e}', 'danger')

    return redirect(url_for('index'))


@app.route('/')
@login_required
def index():
    sort_by = request.args.get('sort', 'url')
    order = request.args.get('order', 'desc')
    filter_status = request.args.get('status')
    filter_tag = request.args.get('tag')
    filter_link_follow = request.args.get('link_follow_status')
    filter_google_indexation = request.args.get('google_index_status')
    filter_page_value = request.args.get('page_value')
    filter_page_trust = request.args.get('page_trust')
    filter_bas = request.args.get('bas')
    filter_backlinks = request.args.get('backlinks_external')
    filter_outlinks = request.args.get('num_outlinks_ext')

    valid_sort_fields = ['url', 'status_code', 'tag', 'link_to_check', 'anchor_text', 'source_plateforme', 'link_follow_status', 'google_index_status', 'page_value', 'page_trust',
                          'bas', 'backlinks_external', 'num_outlinks_ext']

    if sort_by not in valid_sort_fields:
        sort_by = 'url'

    query = db.session.query(Website).filter(Website.user_id == current_user.id)

    if filter_status:
        query = query.filter(Website.status_code == filter_status)
    if filter_tag:
        query = query.filter(Website.tag == filter_tag)
    
    if filter_link_follow:
        query = query.filter(Website.link_follow_status == filter_link_follow)

    if filter_google_indexation:
        query = query.filter(Website.google_index_status == filter_google_indexation)    

    if filter_page_value:
        query = query.filter(Website.page_value == filter_page_value)   

    if filter_page_trust:
        query = query.filter(Website.page_trust == filter_page_trust)   

    if filter_bas:
        query = query.filter(Website.bas == filter_bas)

    if filter_backlinks:
        query = query.filter(Website.backlinks_external == filter_backlinks)                 

    if filter_outlinks:
        query = query.filter(Website.num_outlinks_ext == filter_outlinks)  

    query = query.group_by(Website.url, Website.anchor_text)

    # Tri par défaut (URL)
    default_sort_key = lambda x: x.url
    sites = sorted(query.all(), key=default_sort_key)

    # Appliquer le tri seulement si une colonne différente est sélectionnée
    if sort_by != 'url':
        # Déterminer la fonction de tri pour la colonne sélectionnée
        sort_key = lambda x: getattr(x, sort_by)

        # Appliquer le tri en fonction de l'ordre demandé
        if order == 'asc':
            sites = sorted(sites, key=sort_key)
        else:
            sites = sorted(sites, key=sort_key, reverse=True)


    tags = Tag.query.all()  # Récupère tous les tags(champs valeur) de la base de données
    sources = Source.query.all()  # Récupère toutes les sources
    return render_template('index.html', sites=sites, username=current_user.username, tags=tags, sources=sources)



# fonction automatise le processus de mise à jour des données Babbar pour les sites qui n'ont pas encore ces données. Elle parcourt tous les sites sans données Babbar,
# effectue la mise à jour pour chaque site, et redirige ensuite l'utilisateur vers la page d'accueil.
@app.route('/update_babbar_data')
@login_required
def update_babbar_data():
    sites_to_update = Website.query.filter_by(page_value=None).all()

    for site in sites_to_update:
        fetch_url_data(site.url, async_mode=False)
        db.session.commit() 

    return redirect(url_for('index'))



#--------------------------------------------------------------------------------------------ajouter les routes necessaires(lylia)------------------------------------------------------------------------------

# Route pour afficher la page d'administration
@app.route('/admin', methods=['GET'])
@login_required
def admin():
    if current_user.role != 'admin':
        #flash('Accès refusé, vous devez être un administrateur.')
        return redirect(url_for('index'))
    
    users = User.query.all()  # Récupérer tous les utilisateurs
    return render_template('admin.html', users=users)  # Passer les utilisateurs au template


# Route pour ajouter un nouvel utilisateur
@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        #flash('Accès refusé, vous devez être un administrateur.')
        return redirect(url_for('index'))

    
    username = request.form['username']
    password = request.form['password']

    new_user = User(username=username)  
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    flash('Utilisateur ajouté avec succès.')
    return redirect(url_for('admin'))



# Route pour modifier un utilisateur
@app.route('/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user or current_user.role != 'admin':
        #flash('Utilisateur non trouvé ou accès refusé.')
        return redirect(url_for('admin'))

    
    new_username = request.form['username']
    new_password = request.form['password']

    # Vérifie si le nom d'utilisateur a changé
    if new_username and new_username != user.username:
        user.username = new_username

    # Vérifie si un nouveau mot de passe a été fourni
    if new_password:
        user.set_password(new_password)  # Met à jour le mot de passe

        
    db.session.commit()
    flash('Utilisateur modifié avec succès.')
    return redirect(url_for('admin'))



# Route pour supprimer un utilisateur
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user and current_user.role == 'admin':
        db.session.delete(user)
        db.session.commit()
        flash('Utilisateur supprimé avec succès.')
    else:
        flash('Utilisateur non trouvé ou accès refusé.')
    return redirect(url_for('admin'))


# Route pour ajouter un site dans la liste des sites
@app.route('/add_tag', methods=['POST'])
def add_tag():
    data = request.get_json()
    nouvelle_couleur = couleur_aleatoire_unique()
    new_tag = Tag(valeur=data['valeur'], couleur=nouvelle_couleur)
    db.session.add(new_tag)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/delete_tag', methods=['POST'])
def delete_tag():
    data = request.get_json()
    tag_to_delete = Tag.query.filter_by(valeur=data['valeur']).first()

    if tag_to_delete:
        db.session.delete(tag_to_delete)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Tag not found'}), 404
    

# Route pour ajouter une source dans la liste des sources
@app.route('/add_source', methods=['POST'])
def add_source():
    data = request.get_json()
    new_source = Source(nom=data['nom'])
    db.session.add(new_source)
    db.session.commit()
    return jsonify({'success': True})


# Route pour supprimer une source
@app.route('/delete_source', methods=['POST'])
def delete_source():
    data = request.get_json()
    source_name = data['nom']
    source = Source.query.filter_by(nom=source_name).first()

    if source:
        db.session.delete(source)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Source introuvable'}), 404


#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# la fonction check_link_presence détermine la présence d'un lien spécifié dans le contenu HTML d'une page web
def check_link_presence(html_content, link_to_check):
    soup = BeautifulSoup(html_content, 'html.parser')
    return any(link['href'] == link_to_check for link in soup.find_all('a', href=True))


# la fonction check_anchor_presence détermine la présence d'un texte d'ancre spécifié dans le contenu HTML d'une page web.
def check_anchor_presence(html_content, anchor_text):
    soup = BeautifulSoup(html_content, 'html.parser')
    return any(anchor_text in link.text for link in soup.find_all('a'))


# cette fonction permet à l'utilisateur de supprimer un site de la base de données en fonction de son identifiant, 
# puis elle redirige l'utilisateur vers la page d'accueil.
@app.route('/delete_site/<int:site_id>', methods=['POST'])
def delete_site(site_id):
    site_to_delete = Website.query.get(site_id)
    if site_to_delete:
        duplicates = Website.query.filter(and_(
            Website.url == site_to_delete.url,
            Website.anchor_text == site_to_delete.anchor_text,
            Website.id != site_to_delete.id  
        )).all()

        for duplicate in duplicates:
            db.session.delete(duplicate)
        db.session.delete(site_to_delete)
        
        db.session.commit()
    return redirect(url_for('index'))


 # cette fonction sert à Supprimer tous les sites de la base de données
@app.route('/delete_all_sites', methods=['POST'])
def delete_all_sites():

    Website.query.delete()
    db.session.commit()
    return redirect(url_for('index'))



def couleur_aleatoire_unique():
    # Récupérer toutes les couleurs existantes dans la base de données
    tags_existants = Tag.query.with_entities(Tag.couleur).all()
    couleurs_existantes = {Tag.couleur for (Tag.couleur,) in tags_existants}  # Utiliser une compréhension de set

    while True:
        # Générer une couleur aléatoire
        couleur = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        if couleur not in couleurs_existantes:
            return couleur


# cette fonction est utilisée dans les templates Flask comme filtre pour attribuer une couleur spécifique à un tag donné.
# Si le tag n'est pas dans la liste prédéfinie, la fonction renvoie une couleur par défaut
@app.template_filter('tag_color')
def tag_color(tag_name):
   # Normalise le tag_name pour la recherche dans la base de données
    tag = Tag.query.filter(db.func.lower(Tag.valeur) == tag_name.lower()).first()
    
    # Retourne la couleur du tag ou une couleur par défaut si le tag n'existe pas
    return tag.couleur if tag else "#000000"  # Noir par défaut si aucun tag trouvé

    

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
                soup = BeautifulSoup(content, 'html.parser')

                link_present, follow_status = check_link_presence_and_follow_status(soup, link_to_check)
                print(f"Statut du lien pour {url}: {link_present}, Follow: {follow_status}")
                anchor_present = any(anchor_text in link.text for link in soup.find_all('a'))

                return link_present, anchor_present, follow_status
            else : 
                 print(f"Échec de la réponse HTTP pour {url}: {response.status}")
    except Exception as e:
        print(f"Erreur lors de la récupération de {url}: {e}")
        return False, False, None




# cette fonction asynchrone est utilisée pour récupérer des données sur une URL depuis l'API de Babbar Tech de manière asynchrone,
# mettre à jour les informations du site dans la base de données, et committer les changements
async def fetch_url_data_async(urls_to_check):
    payload_list = [{"url": url} for url in urls_to_check]
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer lrU6gM7ev17v45DTS45dqznlEVvoapsNIotq5aQMeusGOtemdrWlqcpkIIMv"
    }

    batch_size = 5 
    for i in range(0, len(payload_list), batch_size):
        batch_payload = payload_list[i:i+batch_size]
        async with aiohttp.ClientSession() as session:
            for payload in batch_payload:
                async with session.post('https://www.babbar.tech/api/url/overview/main', json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        update_website_data(payload["url"], data)
                        db.session.commit()
                    else:
                        print(f"Échec de la récupération des données pour {payload['url']} : {response.status}")
            await asyncio.sleep(150)  # Attendre 1 minute entre les lots




####################################################################################SERP API Async##############################################################################################################

# cette fonction est utilisée pour vérifier si une URL donnée est indexée sur Google en utilisant l'API SERPAPI.
async def check_google_indexation(session, url):
    query = f"site:{url}"
    params = {
        "engine": "google",
        "q": query,
        "location": "France",
        "api_key": "2d616e924f3b0d90bdcecdae5de3ab32605022360f9598b9c6d25e5a0ed80db5"
    }
    print(f"Envoi de la requête SERPAPI pour l'URL: {url}")
    try: 
        async with session.get("https://serpapi.com/search.json", params=params) as response:
            print(f"Réponse reçue de SERPAPI pour l'URL {url}: Status {response.status}")

            if response.status == 200:
                data = await response.json()
                print(f"Réponse SERPAPI pour {url}: {data}") 
                print(f"Premières données reçues de SERPAPI pour {url}: {data['organic_results'][:1]}")
                is_indexed = "Indexé !" if any(url in result.get('link', '') for result in data.get("organic_results", [])) else "Non indexé"
                print(f"Résultat d'indexation pour {url}: {is_indexed}")
                return is_indexed
            else:
                print(f"Erreur de réponse de SERPAPI pour {url}: Status {response.status}")
    except Exception as e:
        print(f"Exception lors de la vérification de l'indexation pour {url}: {e}")  
        is_indexed = "Non indexé"
        return is_indexed
        
@app.route('/get_latest_sites_data')
def get_latest_sites_data():
    sites = Website.query.group_by(Website.url).order_by(func.max(Website.last_checked).desc()).all()
    sites_data = [{
        "url": site.url,
        "link_to_check": site.link_to_check,
        "status_code": site.status_code,
        "link_status": site.link_status,
        "anchor_status" : site.anchor_status,
        "last_checked": site.last_checked,
        "page_value" : site.page_value,
        "page_trust" : site.page_trust,
        "bas" : site.bas,
        "backlinks_external": site.backlinks_external,
        "num_outlinks_ext" : site.num_outlinks_ext,
        "link_follow_status": site.link_follow_status,
        "google_index_status" : site.google_index_status,
    } for site in sites]
    print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ ELLE MARCHE $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    return jsonify({'sites': sites_data})



##################################################################################################################################################################################################
# conçue pour être déclenchée via une requête POST sur la route /check_all_sites. Elle envoie des messages à une file d'attente RabbitMQ,
# chaque message contenant les détails d'un site, afin d'initier la vérification de tous les sites enregistrés dans la base de données.
# Route pour vérifier tous les sites

@app.route('/check_all_sites', methods=['POST'])
def check_all_sites():
    print("Début de la préparation des messages pour la vérification des sites")
    if request.method == 'POST':
        try:
            parameters = pika.ConnectionParameters('localhost', connection_attempts=5, retry_delay=10)  
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue='site_check_queue')

            sites = Website.query.group_by(Website.url).order_by(func.max(Website.last_checked).desc()).all()
            for site in sites:
                message = json.dumps({
                    "url": site.url,
                    "link_to_check": site.link_to_check,
                    "anchor_text": site.anchor_text,
                })
                channel.basic_publish(exchange='',
                                    routing_key='site_check_queue',
                                    body=message)
            
            asyncio.run(process_websites(sites))
            
            flash("Toutes les URLs ont été ajoutées et traitées", "success")
            connection.close()  
            
            return redirect(url_for('index'))
        except pika.exceptions.AMQPConnectionError as e:
            flash('Erreur de connexion à RabbitMQ', 'error')
            return redirect(url_for('index'))
    else:
        flash('Aucun fichier sélectionné', 'error')

    return redirect(url_for('index'))

     
@app.route('/import', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            df = pd.read_excel(file)
            df.columns = [col.lower() for col in df.columns]
            print("Affichage des colonnes", df.columns)
            websites = []

            for index, row in df.iterrows():
                url = row.get('url', '')
                tag = row.get('tag', '').lower()
                source_plateforme = row.get('plateforme', '')
                link_to_check = row.get('link_to_check', '')
                anchor_text = row.get('anchor_text', '')

                if url:
                    new_site = Website(
                        url=url,
                        tag=tag,
                        source_plateforme=source_plateforme,
                        link_to_check=link_to_check,
                        anchor_text=anchor_text,
                        user_id=current_user.id
                    )

                    db.session.add(new_site)
                    websites.append(new_site)

            db.session.commit()  

            asyncio.run(process_websites(websites))
            get_latest_sites_data()
            print("£££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££")
            flash("Toutes les URLs ont été ajoutées et traitées", "success")
           
            return redirect(url_for('index'))
        else:
            flash('Aucun fichier sélectionné', 'error')

    return render_template('import.html')



# traiter en parallèle plusieurs sites web de manière asynchrone. Pour chaque site, elle appelle une fonction asynchrone
# check_and_update_website_data qui effectue une vérification et une mise à jour des données
async def process_websites(websites):

    async with ClientSession() as session:

        tasks = [check_status(website.id) for website in websites]

        await asyncio.gather(*tasks)



"""********************************************************************CHECK_STATUS**********************************************************************************"""


# Une fonction est conçue pour déclencher la vérification du statut du lien et du texte d'ancre, ainsi que la mise à jour des données Babbar pour un site spécifié.
# Après avoir effectué ces opérations, elle sauvegarde les changements dans la base de données et redirige l'utilisateur vers la page d'accueil.
@app.route('/check_status/<int:site_id>', methods=['GET', 'POST'])
async def check_status(site_id):
    site = Website.query.get(site_id)
    if site:
        try:
            site_copy = deepcopy(site)
            perform_check_status(site.id) 
            fetch_url_data(site.url, async_mode=False)  
            site.last_checked = datetime.utcnow() 
            db.session.commit()  

            new_site = Website(
                url=site_copy.url,
                status_code=site_copy.status_code,
                tag=site_copy.tag,
                source_plateforme=site_copy.source_plateforme,
                link_to_check=site_copy.link_to_check,
                anchor_text=site_copy.anchor_text,
                link_status=site_copy.link_status,
                anchor_status=site_copy.anchor_status,
                last_checked=site_copy.last_checked,
                user_id=site_copy.user_id,
                page_value=site_copy.page_value,
                page_trust=site_copy.page_trust,
                bas=site_copy.bas,
                backlinks_external=site_copy.backlinks_external,
                num_outlinks_ext=site_copy.num_outlinks_ext,
                link_follow_status=site_copy.link_follow_status,
                google_index_status=site_copy.google_index_status
            )

            db.session.add(new_site)
            db.session.commit()  

        except RequestException as e:
            print(f"Erreur de requête : {e}")

    return redirect(url_for('index'))



# Fonction pour vérifier les sites et mettre à jour les résultats dans la base de données depuis le fichier excel
# vérifier les sites web de manière asynchrone, obtenir leurs statuts et mettre à jour les informations dans la base de données en fonction des résultats de la vérification
async def check_and_update_sites(sites):
    results = await check_websites(sites)
    for url, status in results:
        site = next((site for site in sites if site.url == url), None)
        if site:
            site.status_code = status
            if status == 200:
                link_present, anchor_present = await check_link_and_anchor(site.url, site.link_to_check, site.anchor_text)
                site.link_status = "Lien présent" if link_present else "Lien absent"
                site.anchor_status = "Ancre présente" if anchor_present else "Ancre manquante"
            else:
                site.link_status = "Erreur de vérification"
                site.anchor_status = "Erreur de vérification"
            site.last_checked = datetime.utcnow()
            db.session.commit()



#utilisée pour planifier une vérification hebdomadaire de tous les sites web en appelant la fonction asynchrone check_all_sites() dans un contexte approprié.
def check_all_sites_weekly():
    with app.app_context():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(check_all_sites())


#configuration de la page Configuration
# Route pour afficher la page de configuration
# afficher et mettre à jour les configurations de l'application. Si la méthode est GET, elle affiche simplement la page de configuration avec les valeurs actuelles. 
# Si la méthode est POST, elle traite les données du formulaire, met à jour la configuration dans la base de données, et redirige l'utilisateur vers la page de configuration
# avec un message de confirmation.        
@app.route('/configuration', methods=['GET', 'POST'])
@login_required
def configuration():
    if request.method == 'POST':
        sms_enabled = request.form.get('sms_enabled') == 'on'
        phone_number = request.form.get('phone_number')
        config = Configuration.query.first()
        if not config:
            config = Configuration()
            db.session.add(config)
        config.sms_enabled = sms_enabled
        config.phone_number = phone_number
        db.session.commit()
        flash('Configuration sauvegardée avec succès.')
        return redirect(url_for('configuration'))
    else:
        config = Configuration.query.first()
        return render_template('configuration.html', config=config)
    


# permet d'ajouter des URL à une file d'attente en réponse à des requêtes POST. Elle offre un mécanisme simple pour planifier des tâches en ajoutant
# des URLs à une file d'attente depuis l'extérieur de l'application Flask.
@app.route('/add_url_to_queue', methods=['POST'])
def add_url_to_queue():
    url_to_check = request.form.get('url_to_check')
    if url_to_check:
        url_queue.put(url_to_check)
        print(f"URL ajoutée à la file d'attente: {url_to_check}") 
        return jsonify({"message": "URL ajoutée à la file d'attente"}), 200
    return jsonify({"message": "Aucune URL fournie"}), 400



#  traiter de manière continue les URL présentes dans une file d'attente. Elle s'assure que le traitement est effectué à un rythme régulier,
# avec une pause entre chaque traitement pour respecter une éventuelle limite d'API. conçue pour être exécutée dans un thread ou un processus séparé,
# de manière à ne pas bloquer le fonctionnement principal de l'application.
def process_url_queue():
    while True:
        if not url_queue.empty():
            url_to_check = url_queue.get()
            print(f"Traitement de l'URL: {url_to_check}")
            fetch_url_data(url_to_check)  
            url_queue.task_done()  
            time.sleep(SECONDS_BETWEEN_REQUESTS) 
        else:
            time.sleep(10) 



#Ajout de page 
# permet à un utilisateur ou à un robot d'accéder au fichier "robots.txt" en visitant l'URL "/robots.txt" de l'application Flask. Le fichier "robots.txt" est généralement utilisé
# pour fournir des directives aux robots d'exploration web sur la manière dont ils devraient accéder et explorer le site.
@app.route("/robots.txt")
def robots_txt():
    return app.send_static_file("robots.txt")


#  permet à un utilisateur ou à un robot d'accéder au fichier "sitemap.xml" en visitant l'URL '/sitemap.xml' de l'application Flask. Le fichier "sitemap.xml" est généralement utilisé
# pour fournir des informations structurées sur la structure du site aux moteurs de recherche.
@app.route('/sitemap.xml')
def sitemap_xml():
    return app.send_static_file('sitemap.xml')

#  permet à un utilisateur ou à un robot d'accéder au fichier "sitemap_index.xml" en visitant l'URL '/sitemap_index.xml' de l'application Flask. Le fichier "sitemap_index.xml" est 
# généralement utilisé pour référencer plusieurs fichiers de sitemap et indiquer aux moteurs de recherche où trouver des informations détaillées sur la structure du site.
@app.route('/sitemap_index.xml')
def sitemap_index_xml():
    return app.send_static_file('sitemap_index.xml')



#Ajout des données pour le dashboard
# ette route récupère et affiche des informations statistiques sur les backlinks pour un utilisateur spécifique, y compris le nombre de liens par statut HTTP,
# le nombre de liens Follow et NoFollow, ainsi que les statistiques d'ancrage. Ces informations sont ensuite rendues dans un template HTML pour affichage sur la page.
@app.route('/backlink-analysis')
@login_required
def backlink_analysis():
    user_id = current_user.id  
    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
    ).filter(
    Website.user_id == user_id
    ).group_by(Website.url).subquery()

    
# ******************************Requête principale pour récupérer les données de statut HTTP pour les URL avec la date last_checked la plus récente***************************
    status_counts_query = db.session.query(
    Website.status_code,
    func.count(Website.status_code)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
    ).filter(Website.user_id == user_id).group_by(Website.status_code).all()

    print(status_counts_query)

    status_counts = {"200": 0, "3XX": 0, "4XX": 0, "5XX": 0}
    for status, count in status_counts_query:
        print("le status code : ", status)
        if status == 200:
            status_counts["200"] += count
        elif 300 <= status < 400:
            status_counts["3XX"] += count
        elif 400 <= status < 500:
            status_counts["4XX"] += count
        elif 500 <= status < 600:
            status_counts["5XX"] += count   

    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
    ).filter(
    Website.user_id == user_id
    ).group_by(Website.url).subquery()

    follow_counts_query = db.session.query(
    Website.link_follow_status,
    func.count(Website.link_follow_status)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
    ).filter(
    Website.user_id == user_id,
    or_(
        Website.link_follow_status != None,  
        Website.link_follow_status != ''   
    )
).group_by(Website.link_follow_status).all()

    follow_counts = {"follow": 0, "nofollow": 0}
    for status, count in follow_counts_query:
        if status.lower() == 'follow':
            follow_counts['follow'] += count
        elif status.lower() == 'nofollow':
            follow_counts['nofollow'] += count
            

    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
     ).filter(
    Website.user_id == user_id
     ).group_by(Website.url).subquery()

    #************************** Requête principale pour récupérer les données de statut des URL source pour les URL avec la date last_checked la plus récente*************************
    source_url_counts_query = db.session.query(
    Website.link_status,
    func.count(Website.link_status)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
   ).filter(Website.user_id == user_id, 
            or_(
       Website.user_id == user_id,
       Website.link_status != 'Erreur de vérification'
    )
            ).group_by(Website.link_status).all()

    source_url_counts = {"Lien présent": 0, "Lien absent": 0}
    for status, count in source_url_counts_query:
        if status.lower() == 'lien présent':
            source_url_counts['Lien présent'] += count
        elif status.lower() == 'lien absent':
            source_url_counts['Lien absent'] += count

    
      # ****************************************************Récupération des données des tags***************************************************************
    tag_stats_query = db.session.query(
        Website.tag,
        func.count(Website.tag)
    ).join(
        subquery,
        and_(
            Website.url == subquery.c.url,
            Website.last_checked == subquery.c.max_last_checked
        )
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.tag).all()

    total_count = sum(count for _, count in tag_stats_query)
    tag_stats = [{"tag": tag, "count": count, "percentage": (count / total_count) * 100} for tag, count in tag_stats_query]

    # **************************************************Récupération des données backlinks des sites********************************************************
    site_stats_query = db.session.query(
    Website.tag,
    func.count(Website.tag)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
    ).filter(
    Website.user_id == user_id
    ).group_by(Website.tag).all()
    total_count_sites = sum(count for site, count in site_stats_query)
    site_stats = [{"site": site, "count": count, "percentage": (count / total_count_sites) * 100} for site, count in site_stats_query] 

    
    outlinks_stats = get_outlinks_data(user_id)
    google_index_data = get_google_index_data(user_id)
    google_index_data_tag = get_google_index_data_tag(user_id)
    anchor_data = get_anchor_data(user_id)
    anchor_stats = get_anchor_data(user_id)
    tag_stats1 = get_tag_data(user_id)
    tag_data = get_tag_data(user_id)

    return render_template('backlink_analysis.html', status_counts=status_counts, follow_counts=follow_counts, anchor_stats=anchor_stats, tag_stats1=tag_stats1,
    source_url_counts=source_url_counts,outlinks_stats=outlinks_stats, google_index_data=google_index_data, tag_data=tag_data, anchor_data=anchor_data, 
    tag_stats=tag_stats, site_stats=site_stats,google_index_data_tag=google_index_data_tag,)


@app.route('/get_anchor_diversity_data', methods=['GET'])
def get_anchor_diversity_data():
    tag = request.args.get('tag')
    user_id = current_user.id 
    tag = request.args.get('tag')
  
    anchor_stats = get_anchor_data_tag(user_id, tag)
    # Renvoyer les données au format JSON
    return jsonify(anchor_stats)

@app.route('/get_page_comparison_data', methods=['GET'])
def get_page_comparison_data():
    # Récupérer le tag de la requête
    tag = request.args.get('tag')
    user_id = current_user.id 

    # Utiliser le tag pour récupérer les données de valeur de page et de confiance de page depuis la base de données
    page_value_data = get_page_value_data_for_tag(user_id, tag)
    page_trust_data = get_page_trust_data_for_tag(user_id, tag)

    # Construire une structure de données avec les données récupérées
    comparison_data = {
        'page_value_data': page_value_data,
        'page_trust_data': page_trust_data
    }
    
    # Renvoyer les données au format JSON
    return jsonify(comparison_data)

def get_page_trust_data_for_tag(user_id, tag):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,  
        Website.tag == tag
    ).group_by(Website.url).subquery()


    page_trust_data = db.session.query(
        Website.anchor_text,
        Website.url,
        Website.page_trust
    ).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).filter(Website.user_id == user_id
    ).all()

    return [{'anchor_text': data.anchor_text, 'url': data.url, 'page_trust': data.page_trust} for data in page_trust_data]



def get_page_value_data_for_tag(user_id, tag):

    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(Website.url).subquery()

    page_value_data = db.session.query(
        Website.anchor_text,
        Website.url,
        Website.page_value
    ).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).filter(
        Website.user_id == user_id
    ).all()
    
    return [{'anchor_text': data.anchor_text, 'url': data.url, 'page_value': data.page_value} for data in page_value_data]


def extract_domain_tag(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc

@app.route('/get_google_index_data_by_domain', methods=['GET'])
def get_google_index_data_tag_by_domain():
    tag = request.args.get('tag')
    user_id = current_user.id
    google_index_data = get_google_index_data_for_tag_by_domain(user_id, tag)
    return jsonify(google_index_data)


def get_google_index_data_for_tag_by_domain(user_id, tag):
    # Sous-requête pour obtenir la date last_checked la plus récente pour chaque ensemble de lignes identiques
    latest_last_checked_subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(
        Website.url
    ).subquery()

    # Récupérer les enregistrements correspondant à la date last_checked la plus récente pour chaque doublon
    latest_records_query = db.session.query(
        Website.url,
        Website.google_index_status,
        func.count(Website.google_index_status)
    ).join(
        latest_last_checked_subquery,
        and_(
            Website.url == latest_last_checked_subquery.c.url,
            Website.last_checked == latest_last_checked_subquery.c.max_last_checked
        )
    ).filter(
        Website.user_id == user_id,
        or_(
            Website.google_index_status != None,  
            Website.google_index_status != ''   
        )
    ).group_by(
        Website.url,
        Website.google_index_status
    )

    # Créer un dictionnaire pour stocker les comptes par domaine
    domain_counts = {}

    # Compter le nombre de pages indexées et non indexées par domaine
    for url, index_status, count in latest_records_query.all():
        domain = extract_domain(url)
        if domain not in domain_counts:
            domain_counts[domain] = {"indexed": 0, "not_indexed": 0}
        if index_status.lower() == 'indexé !':
            domain_counts[domain]["indexed"] += count
        elif index_status.lower() == 'non indexé':
            domain_counts[domain]["not_indexed"] += count

    # Convertir les résultats en un format JSON compatible
    google_index_data_json = {
        'domains': domain_counts
    }

    return google_index_data_json

@app.route('/get_google_index_data_tag', methods=['GET'])
def get_google_index_data_tag_route():
    tag = request.args.get('tag')
    user_id = current_user.id
    google_index_data = get_google_index_data_for_tag(user_id, tag)
    return jsonify(google_index_data)


def get_google_index_data_for_tag(user_id, tag):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(Website.url).subquery()

    google_index_data_tag = db.session.query(
        Website.tag,
        func.sum(case((Website.google_index_status == 'Indexé !', 1), else_=0)).label('count_indexed'),
        func.sum(case((Website.google_index_status == 'Non indexé', 1), else_=0)).label('count_not_indexed')
        ).join(
          subquery,
          and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
        ).filter(
            Website.user_id == user_id
        ).group_by(Website.tag).all()

    # Convertir les résultats en un format JSON compatible
    google_index_data_json = {
        'labels': [item.tag for item in google_index_data_tag],
        'indexedCounts': [item.count_indexed for item in google_index_data_tag],
        'notIndexedCounts': [item.count_not_indexed for item in google_index_data_tag]
    }

    return google_index_data_json



@app.route('/get_follow_nofollow_counts_domain_tag')
@login_required
def get_follow_nofollow_counts_domain_tag():
    tag = request.args.get('tag')  
    user_id = current_user.id
    follow_nofollow_counts = get_follow_nofollow_counts_domain_tag(user_id, tag)
    return jsonify(follow_nofollow_counts)



def get_follow_nofollow_counts_domain_tag(user_id, tag):
    # Récupérer les comptes follow et nofollow pour chaque domaine en fonction du tag
    domain_counts = {}
    domains = db.session.query(Website.url.distinct()).filter_by(user_id=user_id, tag=tag).all()

    for domain in domains:
        domain_url = domain[0]
        follow_count = db.session.query(func.count(Website.id)).filter_by(user_id=user_id, tag=tag, url=domain_url, link_follow_status='follow').scalar()
        nofollow_count = db.session.query(func.count(Website.id)).filter_by(user_id=user_id, tag=tag, url=domain_url, link_follow_status='nofollow').scalar()
        domain_counts[domain_url] = {"follow": follow_count, "nofollow": nofollow_count}

    return domain_counts


@app.route('/get_link_follow_status_counts_domain_table_tag')
@login_required
def get_link_follow_status_data_tableau():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    page = request.args.get('page', 1, type=int)  # Récupère le numéro de page, par défaut 1
    user_id = current_user.id
    link_follow_counts = get_link_follow_status_count_domain_table(user_id, tag, page)
    
    return jsonify(link_follow_counts)

def get_link_follow_status_count_domain_table(user_id, tag, page):
    # Sous-requête pour obtenir la date last_checked la plus récente pour chaque ensemble de lignes identiques
    latest_last_checked_subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(
        Website.url
    ).subquery()

    # Récupérer les enregistrements correspondant à la date last_checked la plus récente pour chaque doublon
    latest_records_query = db.session.query(
        Website.url,
        Website.link_follow_status,
        func.count(Website.link_follow_status)
    ).join(
        latest_last_checked_subquery,
        and_(
            Website.url == latest_last_checked_subquery.c.url,
            Website.last_checked == latest_last_checked_subquery.c.max_last_checked
        )
    ).filter(
        Website.user_id == user_id,
        or_(
            Website.link_follow_status != None,  
            Website.link_follow_status != ''   
        )
    ).group_by(
        Website.url,
        Website.link_follow_status
    )

    # Paginer les résultats
    link_follow_status_counts = latest_records_query.paginate(page=page, per_page=10)
    
    # Créer un dictionnaire pour stocker les comptes par domaine
    domain_counts = {}

    # Compter le nombre de liens pour chaque statut de lien par domaine
    for url, link_status, count in link_follow_status_counts.items:
        domain = extract_domain(url)
        if domain not in domain_counts:
            domain_counts[domain] = {"follow": 0, "nofollow": 0}
        if link_status.lower() == 'follow':
            domain_counts[domain]["follow"] += count
        elif link_status.lower() == 'nofollow':
            domain_counts[domain]["nofollow"] += count

    # Créer un dictionnaire pour les données de la page actuelle
    current_page_data = {
        "total_pages": link_follow_status_counts.pages,
        "current_page": page,
        "data": domain_counts
    }

    return current_page_data



@app.route('/get_source_url_counts_tag', methods=['GET'])
def get_source_url_counts_tag():
    tag = request.args.get('tag')
    user_id = current_user.id
    source_url_counts = get_source_url_counts_by_tag(tag, user_id)

    return jsonify(source_url_counts)


def get_source_url_counts_by_tag(tag, user_id):
    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
    ).filter(
    Website.user_id == user_id,
    Website.tag == tag
    ).group_by(Website.url).subquery()

    source_url_counts_query = db.session.query(
    Website.link_status,
    func.count(Website.link_status)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
   ).filter(Website.user_id == user_id, 
            or_(
       Website.user_id == user_id,
       Website.link_status != 'Erreur de vérification'
    )
            ).group_by(Website.link_status).all()

    source_url_counts = {"Lien présent": 0, "Lien absent": 0}
    for status, count in source_url_counts_query:
        if status.lower() == 'lien présent':
            source_url_counts['Lien présent'] += count
        elif status.lower() == 'lien absent' or status.lower() == 'URL non présente':
            source_url_counts['Lien absent'] += count
    return source_url_counts


@app.route('/get_source_url_counts_tag_sites', methods=['GET'])
def get_source_url_counts_tag1():
    tag = request.args.get('tag')
    print("*****************TAG*****************",tag)
    user_id = current_user.id
    source_url_counts = get_source_url_counts_by_tag1(tag, user_id)

    return jsonify(source_url_counts)


def get_source_url_counts_by_tag1(tag, user_id):
    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
    ).filter(
    Website.user_id == user_id,
    Website.tag == tag
    ).group_by(Website.url).subquery()

    source_url_counts_query = db.session.query(
    Website.link_status,
    func.count(Website.link_status)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
   ).filter(Website.user_id == user_id, 
            or_(
       Website.user_id == user_id,
       Website.link_status != 'Erreur de vérification'
    )
            ).group_by(Website.link_status).all()

    source_url_counts = {"Lien présent": 0, "Lien absent": 0}
    for status, count in source_url_counts_query:
        if status.lower() == 'lien présent':
            source_url_counts['Lien présent'] += count
        elif status.lower() == 'lien absent' or status.lower() == 'URL non présente':
            source_url_counts['Lien absent'] += count
    return source_url_counts

@app.route('/get_follow_counts_tag')
@login_required
def get_follow_counts_tag_route():
    tag = request.args.get('tag')  
    user_id = current_user.id
    follow_counts = get_follow_counts_tag(user_id, tag)
    return jsonify(follow_counts)



def get_follow_counts_tag(user_id, tag):
    # Effectuez vos requêtes pour récupérer les données follow_counts en fonction du tag
    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked')
    ).filter(
    Website.user_id == user_id,
    Website.tag == tag
    ).group_by(Website.url).subquery()

    follow_counts_query = db.session.query(
    Website.link_follow_status,
    func.count(Website.link_follow_status)
    ).join(
    subquery,
    and_(
        Website.url == subquery.c.url,
        Website.last_checked == subquery.c.max_last_checked
    )
    ).filter(
    Website.user_id == user_id,
    or_(
        Website.link_follow_status != None,  
        Website.link_follow_status != ''   
    )
).group_by(Website.link_follow_status).all()

    follow_counts = {"follow": 0, "nofollow": 0}
    for status, count in follow_counts_query:
        if status.lower() == 'follow':
            follow_counts['follow'] += count
        elif status.lower() == 'nofollow':
            follow_counts['nofollow'] += count
    return follow_counts


@app.route('/get_urls_by_domain')
def get_urls_by_domain():
    domain = request.args.get('domain')
    user_id = current_user.id
    
    # Subquery pour récupérer la dernière date last_checked pour chaque URL
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()
    
    # Requête pour récupérer les URLs correspondant aux dernières dates last_checked
    urls_query = db.session.query(Website.url).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).all()

    urls = [url[0] for url in urls_query if extract_domain_tag(url[0]) == domain]
    print("les urls sont là", urls)
    return jsonify(urls)

@app.route('/get_domain')
@login_required
def get_domaine_route():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    print(tag)
    page = request.args.get('page', 1, type=int)  # Récupère le numéro de page, par défaut 1
    user_id = current_user.id
    status_counts = get_domaine(user_id, tag)
    print("domain",status_counts)
    return jsonify(status_counts)

def get_domaine(user_id, tag):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked'),
        Website.user_id,
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag 
    ).group_by(Website.url).subquery()

    # Récupérer toutes les données d'URLs pour le tag donné
    url_data = db.session.query(subquery.c.url).all()

    # Initialiser un ensemble pour stocker les domaines uniques
    unique_domains = set()

    # Extraire les domaines uniques des données d'URLs
    for row in url_data:
        domain = extract_domain(row[0])  # Fonction à implémenter pour extraire le domaine
        unique_domains.add(domain)

    # Convertir l'ensemble d'URLs en liste pour le retour
    domain_list = list(unique_domains)

    return domain_list


@app.route('/get_status_counts_domain_table_tag')
@login_required
def get_http_status_data_tableau():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    page = request.args.get('page', 1, type=int)  # Récupère le numéro de page, par défaut 1
    user_id = current_user.id
    status_counts = get_status_count_domain_table(user_id, tag, page)
    
    return jsonify(status_counts)



def get_status_count_domain_table(user_id, tag, page):
    # Sous-requête pour obtenir la date last_checked la plus récente pour chaque ensemble de lignes identiques
    latest_last_checked_subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(
        Website.url,  # Vous pouvez ajuster les colonnes utilisées pour identifier les doublons
        Website.status_code, 
        # Ajoutez d'autres colonnes si nécessaire pour identifier les doublons
    ).subquery()

    # Récupérer les enregistrements correspondant à la date last_checked la plus récente pour chaque doublon
    latest_records_query = db.session.query(
        Website.url,
        Website.status_code,
        func.count(Website.status_code)
    ).join(
        latest_last_checked_subquery,
        and_(
            Website.url == latest_last_checked_subquery.c.url,
            Website.last_checked == latest_last_checked_subquery.c.max_last_checked
        )
    ).group_by(
        Website.url,
        Website.status_code
    )

    # Paginer les résultats
    statuses = latest_records_query.paginate(page=page, per_page=10)
    
    # Créer un dictionnaire pour stocker les comptes par domaine
    domain_counts = {}

    # Compter le nombre de lignes pour chaque statut code par domaine
    for url, status, count in statuses.items:
        domain = extract_domain(url)
        if domain not in domain_counts:
            domain_counts[domain] = {"200": 0, "3XX": 0, "4XX": 0, "5XX": 0}
        if status == 200:
            domain_counts[domain]["200"] += count
        elif 300 <= status < 400:
            domain_counts[domain]["3XX"] += count
        elif 400 <= status < 500:
            domain_counts[domain]["4XX"] += count
        elif 500 <= status < 600:
            domain_counts[domain]["5XX"] += count

    # Créer un dictionnaire pour les données de la page actuelle
    current_page_data = {
        "total_pages": statuses.pages,
        "current_page": page,
        "data": domain_counts
    }

    return current_page_data

@app.route('/get_status_counts_domain_tag')
@login_required
def get_http_status_data():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    user_id = current_user.id
    status_counts = get_status_count_domain(user_id, tag)
    return jsonify(status_counts)



def get_status_count_domain(user_id, tag):
    # Sous-requête pour obtenir la date last_checked la plus récente pour chaque ensemble de lignes identiques
    latest_last_checked_subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(
        Website.url,  # Vous pouvez ajuster les colonnes utilisées pour identifier les doublons
        Website.status_code, 
        # Ajoutez d'autres colonnes si nécessaire pour identifier les doublons
    ).subquery()

    # Récupérer les enregistrements correspondant à la date last_checked la plus récente pour chaque doublon
    latest_records_query = db.session.query(
        Website.url,
        Website.status_code,
        func.count(Website.status_code)
    ).join(
        latest_last_checked_subquery,
        and_(
            Website.url == latest_last_checked_subquery.c.url,
            Website.last_checked == latest_last_checked_subquery.c.max_last_checked
        )
    ).group_by(
        Website.url,
        Website.status_code
    ).all()

    # Créer un dictionnaire pour stocker les comptes par domaine
    domain_counts = {}

    # Compter le nombre de lignes pour chaque statut code par domaine
    for url, status, count in latest_records_query:
        domain = extract_domain(url)
        if domain not in domain_counts:
            domain_counts[domain] = {"200": 0, "3XX": 0, "4XX": 0, "5XX": 0}
        if status == 200:
            domain_counts[domain]["200"] += count
        elif 300 <= status < 400:
            domain_counts[domain]["3XX"] += count
        elif 400 <= status < 500:
            domain_counts[domain]["4XX"] += count
        elif 500 <= status < 600:
            domain_counts[domain]["5XX"] += count

    return domain_counts

@app.route('/get_status_count_tag')
@login_required
def get_status_counts_tag_route():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    user_id = current_user.id
    status_counts = get_status_counts_tag(user_id, tag)
    return jsonify(status_counts)

def get_status_counts_tag(user_id, tag):
    # Sous-requête pour obtenir la date last_checked la plus récente pour chaque ensemble de lignes identiques
    latest_last_checked_subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag
    ).group_by(
        Website.url,  # Vous pouvez ajuster les colonnes utilisées pour identifier les doublons
        Website.status_code, 
        # Ajoutez d'autres colonnes si nécessaire pour identifier les doublons
    ).subquery()

    # Récupérer les enregistrements correspondant à la date last_checked la plus récente pour chaque doublon
    latest_records_query = db.session.query(
        Website.status_code,
        func.count(Website.status_code)
    ).join(
        latest_last_checked_subquery,
        and_(
            Website.url == latest_last_checked_subquery.c.url,
            Website.last_checked == latest_last_checked_subquery.c.max_last_checked
        )
    ).group_by(Website.status_code).all()

    # Créer le dictionnaire pour stocker les comptes
    status_counts = {"200": 0, "3XX": 0, "4XX": 0, "5XX": 0}

    # Compter le nombre de lignes pour chaque statut code
    for status, count in latest_records_query:
        if status == 200:
            status_counts["200"] += count
        elif 300 <= status < 400:
            status_counts["3XX"] += count
        elif 400 <= status < 500:
            status_counts["4XX"] += count
        elif 500 <= status < 600:
            status_counts["5XX"] += count   

    return status_counts

def extract_domain(url):
    parsed_url = urllib.parse.urlparse(url)
    return parsed_url.netloc



@app.route('/get_domaine_tag_backlinks')
@login_required
def get_domaine_tag_backlinks_route():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    limit = request.args.get('limit', type=int)  # Récupère le paramètre de requête 'limit', par défaut 10
    offset = request.args.get('offset', type=int)  # Récupère le paramètre de requête 'offset', par défaut 0
    user_id = current_user.id
    anchor_stats = get_domaine_tag_backlinks(user_id, tag)
    return jsonify(anchor_stats)


def get_domaine_tag_backlinks(user_id, tag):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked'),
        Website.user_id,
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag 
    ).group_by(Website.url).subquery()

    # Récupérer toutes les données d'URLs pour le tag donné
    url_data = db.session.query(subquery.c.url).all()

    # Initialiser un dictionnaire pour compter les occurrences de chaque domaine
    domain_counts = {}

    # Compter les occurrences de chaque domaine dans les données
    for row in url_data:
        domain = extract_domain(row[0])  # Fonction à implémenter pour extraire le domaine
        if domain in domain_counts:
            domain_counts[domain] += 1
        else:
            domain_counts[domain] = 1

    # Calculer le nombre total d'URLs
    total_urls = len(url_data)

    # Calculer les pourcentages en fonction du nombre total d'URLs
    domain_stats = []
    for domain, count in domain_counts.items():
        percentage = (count / total_urls) * 100 if total_urls > 0 else 0
        domain_stats.append({'domain': domain, 'count': count, 'percentage': round(percentage, 2)})

    return domain_stats

@app.route('/get_domaine_tag')
@login_required
def get_domaine_tag_route():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    limit = request.args.get('limit', type=int)  # Récupère le paramètre de requête 'limit', par défaut 10
    offset = request.args.get('offset', type=int)  # Récupère le paramètre de requête 'offset', par défaut 0
    user_id = current_user.id
    anchor_stats = get_domaine_tag(user_id, tag, limit, offset)

    return jsonify(anchor_stats)

def get_domaine_tag(user_id, tag, limit=10, offset=0):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked'),
        Website.user_id,
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag 
    ).group_by(Website.url).subquery()

    total_urls = db.session.query(func.count()).select_from(subquery).scalar()
    
    # Récupérer les données d'URLs avec pagination
    url_data = db.session.query(subquery.c.url).offset(offset).limit(limit).all()

    # Extraire les domaines des URLs
    domains = set()
    for row in url_data:
        domain = extract_domain(row[0])  # Fonction à implémenter pour extraire le domaine
        domains.add(domain)

    # Compter les occurrences de chaque domaine
    domain_counts = {}
    for domain in domains:
        count = sum(1 for row in url_data if extract_domain(row[0]) == domain)
        domain_counts[domain] = count

    # Calculer les pourcentages
    domain_stats = []
    for domain, count in domain_counts.items():
        percentage = (count / total_urls) * 100 if total_urls > 0 else 0
        domain_stats.append({'domain': domain, 'count': count, 'percentage': round(percentage, 2)})

    return domain_stats


@app.route('/get_anchor_data_tag')
@login_required
def get_anchor_data_tag_route():
    tag = request.args.get('tag')  # Récupère le paramètre de requête 'tag'
    user_id = current_user.id
    anchor_stats = get_anchor_data_tag(user_id, tag)
    return jsonify(anchor_stats)
    
def get_anchor_data_tag(user_id, tag):
    subquery = db.session.query(
    Website.url,
    func.max(Website.last_checked).label('max_last_checked'),
    Website.user_id,
    
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag 
    ).group_by(Website.url).subquery()

    total_links = db.session.query(func.count()).select_from(subquery).scalar()
    anchor_data = db.session.query(
        Website.anchor_text,
        func.count(Website.id).label('count')
    ).join(
        subquery,
        and_(
            Website.url == subquery.c.url,
            Website.last_checked == subquery.c.max_last_checked,
            
        )
    ).filter(
        Website.user_id == user_id,
    ).group_by(Website.anchor_text).all()
    
    anchor_stats = []
    for anchor, count in anchor_data:
        percentage = (count / total_links) * 100 if total_links > 0 else 0
        anchor_stats.append({'anchor': anchor, 'count': count, 'percentage': percentage}) 

    return anchor_stats

#  fournit une analyse statistique des textes d'ancrage utilisés par un utilisateur, en calculant le nombre de liens et le pourcentage associé pour chaque texte d'ancre.
# Ces statistiques peuvent être utiles pour comprendre la diversité des ancres de liens dans le contenu associé à un utilisateur spécifique.
def get_anchor_data(user_id):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked'),
        Website.user_id
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()

    total_links = db.session.query(func.count()).select_from(subquery).scalar()
    anchor_data = db.session.query(
        Website.anchor_text, 
        func.count(Website.id).label('count')
    ).join(
        subquery,
        and_(
            Website.url == subquery.c.url, 
            Website.last_checked == subquery.c.max_last_checked
        )
    ).filter_by(user_id=user_id).group_by(Website.anchor_text).all()
    anchor_stats = []
    for anchor, count in anchor_data:
        percentage = (count / total_links) * 100 if total_links > 0 else 0
        anchor_stats.append({'anchor': anchor, 'count': count, 'percentage': percentage})

    return anchor_stats


def get_tag_data(user_id):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked'),
        Website.user_id
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()

    total_links = db.session.query(func.count()).select_from(subquery).scalar()
    tag_data = db.session.query(
        Website.tag, 
        func.count(Website.id).label('count')
    ).join(
        subquery,
        and_(
            Website.url == subquery.c.url, 
            Website.last_checked == subquery.c.max_last_checked
        )
    ).filter_by(user_id=user_id).group_by(Website.tag).all()

    tag_stats = []
    for tag, count in tag_data:
        percentage = (count / total_links) * 100 if total_links > 0 else 0
        tag_stats.append({'tag': tag, 'count': count, 'percentage': percentage})

    return tag_stats

def get_outlinks_data(user_id):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()
    outlinks_data = db.session.query(
        Website.anchor_text, 
        func.count(Website.id).label('count')
    ).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).filter(
        Website.user_id == user_id,
        Website.num_outlinks_ext.isnot(None) 
    ).group_by(Website.anchor_text).all()
    total_links = db.session.query(func.count(Website.id)).filter_by(user_id=user_id).scalar()
    outlinks_stats = []
    for anchor, count in outlinks_data:
        percentage = (count / total_links) * 100 if total_links > 0 else 0
        outlinks_stats.append({'anchor': anchor, 'count': count, 'percentage': percentage})

    return outlinks_stats

@app.route('/get_urls')
def get_urls():
    user_id = current_user.id  
    anchor_text = request.args.get('anchor_text')
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.anchor_text == anchor_text
    ).group_by(Website.url).subquery()
    urls_query = db.session.query(Website.url).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).all()

    urls = [url[0] for url in urls_query]
    print("les urls sont là", urls)
    return jsonify(urls)


@app.route('/get_tag_urls')
def get_tag_urls():
    user_id = current_user.id
    tag = request.args.get('tag') 
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id,
        Website.tag == tag 
    ).group_by(Website.url).subquery()

    urls_query = db.session.query(Website.url).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).all()

    urls = [url[0] for url in urls_query]
    return jsonify(urls)



def get_google_index_data(user_id):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()
    google_index_data = db.session.query(
        Website.anchor_text,
        func.sum(case((Website.google_index_status == 'Indexé !', 1), else_=0)).label('count_indexed'),
        func.sum(case((Website.google_index_status == 'Non indexé', 1), else_=0)).label('count_not_indexed')
    ).join(
        subquery,
        and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.anchor_text).all()

    return google_index_data


def get_google_index_data_tag(user_id):
    subquery = db.session.query(
        Website.url,
        func.max(Website.last_checked).label('max_last_checked')
    ).filter(
        Website.user_id == user_id
    ).group_by(Website.url).subquery()

    google_index_data_tag = db.session.query(
        Website.tag,
        func.sum(case((Website.google_index_status == 'Indexé !', 1), else_=0)).label('count_indexed'),
        func.sum(case((Website.google_index_status == 'Non indexé', 1), else_=0)).label('count_not_indexed')
        ).join(
          subquery,
          and_(Website.url == subquery.c.url, Website.last_checked == subquery.c.max_last_checked)
        ).filter(
            Website.user_id == user_id
        ).group_by(Website.tag).all()

    return google_index_data_tag



@app.route('/get_values')
def get_values():
    user_id = current_user.id
    anchor_text = request.args.get('anchor_text')
    selected_url = request.args.get('url')
    values_query = db.session.query(
        Website.page_value,
        Website.page_trust,
        Website.bas,
        Website.backlinks_external,
        Website.num_outlinks_ext,
        Website.last_checked 
    ).filter(
        Website.user_id == user_id,
        Website.anchor_text == anchor_text,
        Website.url == selected_url
    ).all()

    if values_query:
        page_values = []
        page_trusts = []
        bas_values = []
        backlinks = []
        outlinks = []
        last_checked_dates = []

        for row in values_query:
           if row.page_value is not None:
              page_values.append(row.page_value)
           if row.page_trust is not None:
              page_trusts.append(row.page_trust)
           if row.bas is not None:
              bas_values.append(row.bas)
           if row.backlinks_external is not None:
              backlinks.append(row.backlinks_external)
           if row.num_outlinks_ext is not None:
              outlinks.append(row.num_outlinks_ext)
           if row.last_checked is not None:
              last_checked_dates.append(row.last_checked.strftime('%Y-%m-%d %H:%M:%S'))
           else:
              last_checked_dates.append(None) 
 
        values = {
            'page_value': page_values,
            'page_trust': page_trusts,
            'bas': bas_values,
            'backlinks': backlinks,
            'outlinks': outlinks,
            'last_checked': last_checked_dates 
        }

        print("j'affiche les valeurs", values)
        return jsonify(values)
    else:
        return jsonify({})


@app.route('/get_values_tags')
def get_values_tags():
    user_id = current_user.id
    tags = request.args.get('tags')
    selected_url = request.args.get('url')

    # Extraire le domaine de l'URL sélectionnée
    selected_domain = urlparse(selected_url).netloc

    values_query = db.session.query(
        Website.url,
        Website.page_value,
        Website.page_trust,
        Website.bas,
        Website.backlinks_external,
        Website.num_outlinks_ext,
        Website.last_checked  
    ).filter(
        Website.user_id == user_id,
        Website.tag == tags,
        func.lower(extract_domain(Website.url)) == func.lower(selected_domain)  # Filtrer par domaine
    ).all()

    if values_query:
        values = {
            'urls': [row.url for row in values_query],  # Liste des URLs correspondantes
            'page_values': [row.page_value for row in values_query],
            'page_trusts': [row.page_trust for row in values_query],
            'bas_values': [row.bas for row in values_query],
            'backlinks': [row.backlinks_external for row in values_query],
            'outlinks': [row.num_outlinks_ext for row in values_query],
            'last_checked': [row.last_checked.strftime('%Y-%m-%d %H:%M:%S') if row.last_checked else None for row in values_query]
        }

        print("j'affiche les valeurs", values)
        return jsonify(values)
    else:
        return jsonify({})
    

@app.route('/get_values_filter_tags')
def get_values_filter_tags():
    user_id = current_user.id
    tags = request.args.get('tags')
    print("le filtre", tags)
    selected_url = request.args.get('url')

    values_query = db.session.query(
        Website.page_value,
        Website.page_trust,
        Website.bas,
        Website.backlinks_external,
        Website.num_outlinks_ext,
        Website.last_checked  
    ).filter(
        Website.user_id == user_id,
        Website.tag == tags,
        Website.url == selected_url
    ).all()

    if values_query:
        page_values = []
        page_trusts = []
        bas_values = []
        backlinks = []
        outlinks = []
        last_checked_dates = []

        for row in values_query:
           if row.page_value is not None:
              page_values.append(row.page_value)
           if row.page_trust is not None:
              page_trusts.append(row.page_trust)
           if row.bas is not None:
              bas_values.append(row.bas)
           if row.backlinks_external is not None:
              backlinks.append(row.backlinks_external)
           if row.num_outlinks_ext is not None:
              outlinks.append(row.num_outlinks_ext)
           if row.last_checked is not None:
              last_checked_dates.append(row.last_checked.strftime('%Y-%m-%d %H:%M:%S'))
           else:
              last_checked_dates.append(None)  
  
        values = {
            'page_value': page_values,
            'page_trust': page_trusts,
            'bas': bas_values,
            'backlinks': backlinks,
            'outlinks': outlinks,
            'last_checked': last_checked_dates  
        }

        print("j'affiche les valeurs", values)
        return jsonify(values)
    else:
        return jsonify({})
    



# cette fonction est utilisée pour déconnecter l'utilisateur et le rediriger vers la page de connexion de l'application Flask.
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login')) 



Thread(target=process_url_queue).start()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_all_sites_weekly, 'interval', weeks=1)
    scheduler.start()

# l'exécution de la fonction check_all_sites_weekly à des intervalles réguliers (une fois par semaine) en utilisant le planificateur Flask APScheduler.
#  Ensuite, il démarre l'application Flask en mode débogage.
if __name__ == '__main__':

        Thread(target=start_scheduler).start()
        app.run(host="0.0.0.0", port=5000, debug=True)

        """with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      scheduler = BackgroundScheduler()
      scheduler.add_job(check_all_sites_weekly, 'interval', weeks=1)
      scheduler.start()
      app.run(debug=True)"""