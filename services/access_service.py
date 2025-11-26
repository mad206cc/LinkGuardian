from models import UserAccess
from flask_login import current_user

def user_can_access_data(current_user_id, target_user_id):
    """Retourne True si l'utilisateur courant peut consulter les données du target_user"""

    # Accès à ses propres données
    if current_user_id == target_user_id:
        return True

    # Admin OU main_admin → accès total
    if current_user.role in ["admin", "main_admin"]:
        return True

    # Sinon → vérifier s'il a un partage
    access = UserAccess.query.filter_by(
        owner_id=target_user_id,
        grantee_id=current_user_id
    ).first()

    return bool(access)

