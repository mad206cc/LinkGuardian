from flask_login import LoginManager

login_manager = LoginManager() # initialisation de Flask-Login pour la gestion des utilisateurs
login_manager.login_view = 'auth_routes.login'  # redirection vers la page de connexion si l'utilisateur n'est pas authentifié
