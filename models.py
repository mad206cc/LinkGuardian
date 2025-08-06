from database import db
from datetime import datetime  # Importez datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask_login import login_user, logout_user, current_user, login_required


class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(250), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    tag = db.Column(db.String(50), nullable=True)  # pour les tag
    source_plateforme = db.Column(db.String(100))
    link_to_check = db.Column(db.String(250), nullable=True)
    anchor_text = db.Column(db.String(250), nullable=True)
    link_status = db.Column(db.String(250), nullable=True)
    anchor_status = db.Column(db.String(250), nullable=True)
    last_checked = db.Column(db.DateTime, nullable=True)  # date de la dernière vérification
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    page_value = db.Column(db.Integer)
    page_trust = db.Column(db.Integer)
    bas = db.Column(db.Integer)
    backlinks_external = db.Column(db.Integer)
    num_outlinks_ext = db.Column(db.Integer)
    link_follow_status = db.Column(db.String(50), nullable=True)  # "follow", "nofollow", ou None
    google_index_status = db.Column(db.String(50)) #colonne indexé non indexé Google (serpapi)

    def __repr__(self):
        return f'<Website {self.url}>'
    
class User(UserMixin,db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    #Ajouter ce champs pour le role : 'admin' = administrateur 
    #                                 'user' = utilisateur simple 
    role = db.Column(db.String(50), default='user') 

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    

# Nouvelle classe pour les tags
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valeur = db.Column(db.String(50), nullable=False)  # max 50 caractères
    couleur = db.Column(db.String(7), nullable=True)  # Couleur hexadécimale (ex: #FF5733)

    def __repr__(self):
        return f'<Tag {self.valeur}>'
    

# Nouvelle classe pour les sources 
class Source(db.Model):
    __tablename__ = 'source'  # Nom de la table

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(255), unique=True, nullable=False)  # Nom de la source

    def __repr__(self):
        return f'<Source {self.nom}>'


class Configuration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sms_enabled = db.Column(db.Boolean, default=False)
    phone_number = db.Column(db.String(20), nullable=True)