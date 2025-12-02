import streamlit as st
from mistralai import Mistral
from notion_client import Client
import requests
import datetime
import time
import threading
from urllib.parse import quote
import json
import re

# ==============================================================================
# 1. CONFIGURATION & STYLE
# ==============================================================================
st.set_page_config(page_title="Cor-Tech OS", page_icon="🤖", layout="wide")

st.markdown("""
<style>
    .stChatInput {position: fixed; bottom: 0; padding-bottom: 20px; z-index: 100;}
    .block-container {padding-bottom: 120px;} 
    div[data-testid="stExpander"] {border: 2px solid #ff4b4b; border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

try:
    NOTION_KEY = st.secrets["NOTION_KEY"]
    NOTION_DB_TASKS = st.secrets["NOTION_DB_TASKS_ID"]
    NOTION_DB_RAPPELS = st.secrets["NOTION_DB_RAPPELS_ID"]
    MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"]
    BREVO_KEY = st.secrets["BREVO_KEY"]
    MACRODROID_URL = st.secrets.get("MACRODROID_URL", "") 
    SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
    TEST_DESTINATAIRE = st.secrets["TEST_DESTINATAIRE"]
except Exception as e:
    st.error(f"⚠️ CLÉS MANQUANTES ! Vérifiez les secrets.\n{e}")
    st.stop()

notion = Client(auth=NOTION_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# ==============================================================================
# 2. CERVEAU IA (PROMPT ROBUSTE)
# ==============================================================================
SYSTEM_PROMPT = f"""
Tu es l'IA de l'association Cor-Tech.

RÈGLE D'OR POUR LES EMAILS :
Si l'utilisateur demande de PRÉPARER/RÉDIGER un email, tu dois générer un JSON strict.
IMPORTANT : Ne mets JAMAIS de vrais retours à la ligne (touche Entrée) à l'intérieur du JSON. Écris tout le code HTML sur une seule ligne continue.

Format OBLIGATOIRE :
<EMAIL_DRAFT>
{{
  "destinataire": "email@exemple.com",
  "sujet": "Sujet du mail",
  "corps_html": "<p>Bonjour,</p><p>Ceci est le contenu...</p>"
}}
</EMAIL_DRAFT>

Si pas d'email précisé, utilise "{TEST_DESTINATAIRE}".
Pour le reste, réponds normalement.
"""

# ==============================================================================
# 3. FONCTIONS TECHNIQUES (+ Nettoyeur JSON)
# ==============================================================================

def clean_json_input(raw_json):
    """
    Répare le JSON cassé par Mistral s'il contient des retours à la ligne.
    On remplace les retours à la ligne par des espaces, car le HTML s'en fiche.
    """
    # Enlever les espaces au début/fin
    cleaned = raw_json.strip()
    # Remplacer les vrais sauts de ligne par un espace simple (pour éviter de casser la string JSON)
    cleaned = cleaned.replace("\n", " ").replace("\r", "")
    return cleaned

def send_email_brevo_debug(sujet, html_content, to_email):
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": "IA Cor-Tech", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
