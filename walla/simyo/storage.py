# storage.py - Almacenamiento persistente de datos de usuarios
import json
import os
from config import USERS_FILE

def load_all_users() -> dict:
    """Carga el diccionario de usuarios guardados desde el archivo JSON."""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_all_users(data: dict) -> None:
    """Guarda el diccionario de usuarios en el archivo JSON."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user_data(user_id: int | str) -> dict | None:
    """Obtiene los datos guardados de un usuario específico."""
    data = load_all_users()
    return data.get(str(user_id))

def save_user_data(user_id: int | str, email: str, phone: str) -> None:
    """Guarda o actualiza el correo electrónico y teléfono de un usuario."""
    data = load_all_users()
    data[str(user_id)] = {
        "email": email,
        "phone": phone
    }
    save_all_users(data)
