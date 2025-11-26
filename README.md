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
 1) Ouvrir un invite de commande, et se placer dans le dossier du projet. En parallèle, vérifie que t'as bien activé le Docker Destop.

 2) Dans l'invite de commande, saisir le script suivant : 

 ```bash
 docker compose build --no-cache
 docker compose up -d
 docker exec -it linkguardian_web python -c "from app import app, db; app.app_context().push(); db.create_all()"
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

(Le README a été écrit avec une grande qualité rédactionnel négatif, si vous voyez des fautes, n'hésitez pas à ignorer !)

