import streamlit as st
import firebase_admin
from firebase_admin import auth, credentials, firestore
from firebase_admin._auth_utils import UserNotFoundError
import requests
import json
from services.firebase_service import get_collection, query_documents
from services.user_service import get_user_by_email, create_user, get_user
import os
from config.firebase_config import get_firebase_config
from datetime import datetime
import pytz
import uuid
import time

def get_firebase_auth():
    """Get Firebase REST API authentication object with secrets configuration"""
    if 'firebase_auth' not in st.session_state:
        try:
            # Obtain configuration from secrets.toml through firebase_config
            firebase_config = get_firebase_config()
            
            if not firebase_config or 'config' not in firebase_config or 'apiKey' not in firebase_config['config']:
                raise ValueError("Firebase configuration is missing required fields")
                
            st.session_state['firebase_auth'] = {
                'api_key': firebase_config['config']['apiKey'],
                'base_url': 'https://identitytoolkit.googleapis.com/v1'
            }
        except Exception as e:
            st.error("""
            Error loading Firebase authentication configuration. 
            Please make sure you have set up your .streamlit/secrets.toml file with the required Firebase credentials.
            Required fields in secrets.toml:
            [firebase]
            api_key = "your-api-key"
            auth_domain = "your-auth-domain"
            project_id = "your-project-id"
            storage_bucket = "your-storage-bucket"
            app_id = "your-app-id"
            """)
            raise e
            
    return st.session_state['firebase_auth']

def sign_in_with_email_password(email, password):
    """Sign in using Firebase REST API"""
    auth_config = get_firebase_auth()
    url = f"{auth_config['base_url']}/accounts:signInWithPassword?key={auth_config['api_key']}"
    
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.HTTPError as e:
        error_message = json.loads(e.response.text)['error']['message']
        return False, error_message

def verify_credentials(email, password):
    try:
        # Sign in using REST API
        success, result = sign_in_with_email_password(email, password)
        if not success:
            return False, None, result
            
        # Get user data from Firestore
        db = firestore.client()
        user_ref = db.collection('users').document(result['localId']).get()
        
        if user_ref.exists:
            user_data = user_ref.to_dict()
            user_data['id'] = result['localId']
            user_data['token'] = result['idToken']
            return True, user_data, "Login successful"
        else:
            return False, None, "User data not found"
            
    except Exception as e:
        return False, None, str(e)

def register_user(email, password, name, role="user"):
    try:
        # Verificar si el usuario ya existe
        existing_user = get_user_by_email(email)
        if (existing_user):
            return False, "El correo electrónico ya está registrado"
        
        # Registrar usuario usando REST API
        auth_config = get_firebase_auth()
        url = f"{auth_config['base_url']}/accounts:signUp?key={auth_config['api_key']}"
        
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        user_id = result['localId']
        
        # Obtener zona horaria UTC-7 para la fecha de creación
        tz = pytz.timezone('America/Denver')
        created_at = datetime.now(tz).strftime("%d de %B de %Y, %I:%M:%S%p UTC-7")
        
        # Crear objeto de usuario para Firestore
        user_data = {
            "id": user_id,
            "email": email,
            "name": name,
            "role": role,
            "createdAt": created_at
        }
        
        # Almacenar el usuario en Firestore
        get_collection("users").document(user_id).set(user_data)
        
        # Actualizar el perfil del usuario
        update_profile_url = f"{auth_config['base_url']}/accounts:update?key={auth_config['api_key']}"
        profile_payload = {
            "idToken": result['idToken'],
            "displayName": name,
            "returnSecureToken": True
        }
        
        requests.post(update_profile_url, json=profile_payload)
        
        return True, "Usuario registrado exitosamente"
    
    except requests.exceptions.HTTPError as e:
        error_message = json.loads(e.response.text)['error']['message']
        
        if error_message == "EMAIL_EXISTS":
            return False, "El email ya está en uso"
        elif error_message == "WEAK_PASSWORD":
            return False, "La contraseña es demasiado débil, debe tener al menos 6 caracteres"
        elif error_message == "INVALID_EMAIL":
            return False, "Formato de email inválido"
        else:
            return False, f"Error al registrar usuario: {error_message}"
    except Exception as e:
        return False, f"Error al registrar usuario: {str(e)}"

def change_password(email, current_password, new_password):
    try:
        # Verificar credenciales actuales
        success, result = sign_in_with_email_password(email, current_password)
        if not success:
            return False, "La contraseña actual es incorrecta"
        
        # Cambiar contraseña usando REST API
        auth_config = get_firebase_auth()
        url = f"{auth_config['base_url']}/accounts:update?key={auth_config['api_key']}"
        
        payload = {
            "idToken": result['idToken'],
            "password": new_password,
            "returnSecureToken": True
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        return True, "Contraseña actualizada exitosamente"
    
    except requests.exceptions.HTTPError as e:
        error_message = json.loads(e.response.text)['error']['message']
        
        if error_message == "INVALID_ID_TOKEN":
            return False, "La sesión ha expirado, por favor inicie sesión nuevamente"
        elif error_message == "WEAK_PASSWORD":
            return False, "La nueva contraseña es demasiado débil"
        else:
            return False, f"Error al cambiar contraseña: {error_message}"
    except Exception as e:
        return False, f"Error al cambiar contraseña: {str(e)}"

def reset_password(email):
    """Send password reset email using REST API"""
    try:
        auth_config = get_firebase_auth()
        url = f"{auth_config['base_url']}/accounts:sendOobCode?key={auth_config['api_key']}"
        
        payload = {
            "requestType": "PASSWORD_RESET",
            "email": email
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        return True, "Se ha enviado un enlace de restablecimiento de contraseña a su correo"
    except requests.exceptions.HTTPError as e:
        error_message = json.loads(e.response.text)['error']['message']
        if error_message == "EMAIL_NOT_FOUND":
            return False, "No existe una cuenta con este correo electrónico"
        else:
            return False, f"Error al enviar el correo de restablecimiento: {error_message}"
    except Exception as e:
        return False, f"Error al restablecer contraseña: {str(e)}"

# Función para cerrar sesión
def logout_user():
    """Handle user logout"""
    try:
        # Just clear session state since Firebase handles token invalidation
        return True, "Logout successful"
    except Exception as e:
        return False, str(e)

# Función para actualizar el perfil de usuario
def update_user_profile(user_id, name=None, photo_url=None):
    try:
        # Obtener usuario
        user_data = get_user(user_id)
        
        if not user_data:
            return False, "Usuario no encontrado"
        
        # Actualizar datos en Firestore
        updates = {}
        
        if name:
            updates["name"] = name
        
        if photo_url:
            updates["photoURL"] = photo_url
        
        # Si hay actualizaciones, aplicarlas
        if updates:
            get_collection("users").document(user_id).update(updates)
            
            # Si el usuario está en session_state, actualizar también allí
            if 'user' in st.session_state and st.session_state['user'].get('id') == user_id:
                for key, value in updates.items():
                    st.session_state['user'][key] = value
        
        return True, "Perfil actualizado exitosamente"
    
    except Exception as e:
        return False, f"Error al actualizar perfil: {str(e)}"

# Función para obtener el usuario actual
def get_current_user():
    """Get currently authenticated user data"""
    if 'user' in st.session_state:
        return st.session_state['user']
    return None

# Función para actualizar el rol de un usuario
def update_user_role(user_id, new_role):
    try:
        # Actualizar el rol del usuario en Firestore
        get_collection("users").document(user_id).update({"role": new_role})
        
        return True, f"Rol actualizado a '{new_role}' exitosamente"
    except Exception as e:
        return False, f"Error al actualizar rol: {str(e)}"

# Función para verificar token y mantener sesión
def verify_session_token():
    try:
        if 'auth_token' not in st.session_state:
            return False
            
        # Verify token is valid
        decoded_token = auth.verify_id_token(st.session_state['auth_token'])
        
        # Check if token is expired
        exp_time = decoded_token.get('exp', 0)
        if exp_time < time.time():
            return False
            
        return True
    except Exception:
        return False

# Función para obtener los usuarios asignados a un monitor
def get_assigned_users(monitor_id):
    # Buscar asignaciones
    assignments = query_documents("assignments", "monitor_id", "==", monitor_id)
    
    if not assignments:
        return []
    
    # Obtener IDs de usuarios asignados
    user_ids = [assignment['user_id'] for assignment in assignments]
    
    # Obtener datos de usuarios
    users = []
    for user_id in user_ids:
        user_doc = get_collection("users").document(user_id).get()
        if user_doc.exists:
            users.append(user_doc.to_dict())
    
    return users

# Función para asignar un usuario a un monitor
def assign_user_to_monitor(user_id, monitor_id):
    # Crear un documento en la colección de asignaciones
    assignment_data = {
        "user_id": user_id,
        "monitor_id": monitor_id,
        "assigned_at": datetime.now().isoformat()
    }
    
    # Generar ID único para la asignación (combinación de user_id y monitor_id)
    assignment_id = f"{user_id}_{monitor_id}"
    
    # Almacenar la asignación en Firestore
    get_collection("assignments").document(assignment_id).set(assignment_data)
    
    return True, "Usuario asignado exitosamente"
