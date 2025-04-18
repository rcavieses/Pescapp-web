import streamlit as st
import json
import os
from pathlib import Path

def get_firebase_config():
    """Obtener configuración de Firebase desde Streamlit secrets"""
    try:
        # Intentar obtener la configuración desde secrets
        config = {
            "type": st.secrets.firebase.type,
            "project_id": st.secrets.firebase.project_id,
            "private_key_id": st.secrets.firebase.private_key_id,
            "private_key": st.secrets.firebase.private_key,
            "client_email": st.secrets.firebase.client_email,
            "client_id": st.secrets.firebase.client_id,
            "auth_uri": st.secrets.firebase.auth_uri,
            "token_uri": st.secrets.firebase.token_uri,
            "auth_provider_x509_cert_url": st.secrets.firebase.auth_provider_x509_cert_url,
            "client_x509_cert_url": st.secrets.firebase.client_x509_cert_url,
            "universe_domain": st.secrets.firebase.universe_domain
        }
        
        # Return credentials directly without creating a temporary file
        return {
            "credentials": config,
            "config": {
                "apiKey": st.secrets.firebase.api_key,
                "authDomain": st.secrets.firebase.auth_domain,
                "projectId": st.secrets.firebase.project_id,
                "storageBucket": st.secrets.firebase.storage_bucket,
                "appId": st.secrets.firebase.app_id
            }
        }
        
    except Exception as e:
        st.error(f"""
        Error loading Firebase configuration. 
        Please make sure you have set up your .streamlit/secrets.toml file with the required Firebase credentials.
        Error: {str(e)}
        """)
        raise e