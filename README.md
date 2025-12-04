# LinkGuardian
Projet LinkGuardian dédié à la vérification et la data analysis des backlinks, à destination de l'équipe SEO - Karavel.

## **Prise en main de LinkGuardian en local :**

Pour pouvoir ouvrir l'application en **local**, il faut suivre ces étapes : 


1) Avant de commencer, il faut installer [**Anaconda**](https://www.anaconda.com/download/success) et choisir le **Miniconda Installers** pour avoir une version plus léger.

2) Copier les éléments du dossier ```\_fichier-local_``` dans le niveau mère ``\..``.

3) Ensuite, il te suffit d'ouvrir l'**invite de commande**, et entrer saisir le script ci-dessus pour pouvoir créer l'environnement virtuel : 

```bash
conda create -n linkguardian python=3.10
conda activate linkguardian
cd chemin_de_ton_projet_linkguardian
pip install -r requirements.txt
```

4) Dans le même invite de commandes, tapez ce script pour initier les migrations de Flask :

```bash
flask db init
flask db migrate -m "message"
flask db upgrade
```

Tu verras qu'un dossier ```\migrations``` va se créer pour sauvegarder les migrations effectués, en particulier les changements liés au modèle des données. Un autre dossier ```\instance``` contenant une base SQLite ```site.db``` va se créer, c'est la table de données liés au fichier ```models.py```.


3) Ensuite dans ton dossier LinkGuardian, repère le fichier qui s'appelle ```LinkGuardian_Laceur```, et double-clic dessus. A ce stade, tu verras une fenêtre de terminal ouvrir, qui te pose des questions. Tu pourras répondre "O" pour le purge et par le numéro "1" pour le démarrage de l'application.

4) Maintenant t'auras plusieurs fenêtres de termianls ouvertes, **SURTOUT NE PAS FERMER CES FENÊTRES !!!!!!!!** L'application s'ouvrira sur votre navigateur.


## **Prise en main de LinkGuardian sur Docker Destop :**

Pour ce faire, sans modifier le dossier : 
 1) Ouvrir un PowerShell, et se placer dans le dossier du projet. En parallèle, vérifie que t'as bien activé le Docker Destop.

 2) Dans l'invite de commande, saisir le script suivant : 

 ```bash
 docker compose build --no-cache
 docker compose up -d
 docker exec -it linkguardian_web python -c "from app import app, db; app.app_context().push(); db.create_all()"
 ```

 3) Une dernière étape d'initialisation de migration Flask est important, de même dans le PowerShell : 
 ```bash
 docker compose exec web flask db init
 docker compose exec web flask db upgrade
 ```

Suivant la manière comment tu héberges le site, l'adresse URL d'accès peut changer : 
- en local : http://127.0.0.1:5000/
- sur un serveur d'adresse IP XX.XX.XX.XX (celui de Karavel, c'est 10.12.3.12 et il suffit juste de place le dossier entier dans un répertoire dédié. Pour finir, il faut suivre les indications ci-dessus.) : http://XX.XX.XX.XX:5000/ (pour Karavel, c'est donc : http://10.12.3.12:5000/).

Dans ce cas, les données sont stckées sous PostgreSQL pour pouvour utiliser Docker. Si vous souhaiter cosulter la table des données, il faut s'authentifier sur le lien : http://localhost:8080/.

Pour l'authentification, il faut saisir :
- Système : **PostgreSQL**
- Serveur : ```db_host``` (ici c'est **_postgres_**)
- Utilisateur : ```db_user``` (ici c'est **_postgres_**)
- Mot de passe : ```db_pass``` (ici c'est **_Karavel123#_**)
- Base de données : ```db_name``` (ici c'est **_site_**)

**!!! WARNING !!!** : Pour que l'application soit ouvert tout le monde, il faut que le serveur soit allumé en permanence et Docker Destop également.

## **En cas de modification du projet :**

Il est important de s'en souvenir que la projet est séparé en plusieurs, qui s'ollicitent plusieurs extensions.

### 🔧 Celery
Celery est utilisé pour exécuter en arrière-plan toutes les tâches lourdes ou longues
(vérifications des backlinks, import de sites, tâches automatisées, etc.).  
Il permet à l'application de rester fluide pendant que les analyses se déroulent en parallèle.  
Dans LinkGuardian, plusieurs workers Celery traitent les files `urgent`, `standard`, `weekly`.

### 🐰 RabbitMQ
RabbitMQ est le message broker utilisé par Celery.  Il sert de file d'attente pour stocker et distribuer les tâches aux workers.  
Le backend ajoute une tâche → RabbitMQ la met en file → Celery worker l'exécute.
Dans LinkGuardian, on l'utilise principalement pour gérer le lancement des requêtes d'API (Serpapi et Babbar).

### 🗄 Base de données — PostgreSQL

PostgreSQL est utilisé comme base de données principale.
Il stocke l’ensemble des informations du projet :

- utilisateurs & rôles
- sites web surveillés
- backlinks et états d’indexation
- historiques & statistiques des scans
- tags, sources et métadonnées
- tâches Celery associées aux vérifications

L’accès se fait depuis le backend via SQLAlchemy, garantissant
une interaction fiable et performante avec les données. 

Si vous souhaitez consulter ou modifier l'architecture de la base de données, consulter le fichier ```models.py```.

En cas de modification apporter dans ```models.py```, il faut faire une migration à patir du PowerShell (c'est surtout le cas où la première migration a déjà été faites) : 
```bash
docker compose exec web flask db migrate -m "description de la modification"
docker compose exec web flask db upgrade
```

### 🎯 Backend
Développé avec **Python + Flask**, il gère toute la logique métier :
- gestion des utilisateurs & sessions
- communication avec la base de données
- vérification des backlinks
- API et routes utilisées par le frontend
- planification & exécution de tâches via Celery + RabbitMQ

### 🎨 Frontend
Construit en **HTML + TailwindCSS + HTMX + AlpineJS**, il fournit l’interface utilisateur :
- pages dashboard et listing des sites/backlinks
- filtres dynamiques sans rechargement
- interactions légères côté client
- récupération et affichage des données du backend

Dans le cas où des mofications sont apportées dans backend et le frontend, il faut recontruire le container du Docker Destop. Dans le PowerShell, tapez : 
```bash
docker compose down
docker compose up --build -d
```


