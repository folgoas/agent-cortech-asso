import streamlit as st
from mistralai import Mistral
from notion_client import Client
import pandas as pd
import requests
import datetime
import time
import threading
from urllib.parse import quote

# ==============================================================================
# 1. CONFIGURATION & SECRETS
# ==============================================================================
try:
    # Récupération des clés
    NOTION_KEY = st.secrets["NOTION_KEY"]
    NOTION_DB_TASKS = st.secrets["NOTION_DB_TASKS_ID"]
    NOTION_DB_RAPPELS = st.secrets["NOTION_DB_RAPPELS_ID"]
    MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"] # Nouvelle clé
    BREVO_KEY = st.secrets["BREVO_KEY"]
    
    # Optionnel
    MACRODROID_URL = st.secrets.get("MACRODROID_URL", "") 
    
    # Emails
    SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
    TEST_DESTINATAIRE = st.secrets["TEST_DESTINATAIRE"]
except Exception as e:
    st.error(f"⚠️ CLÉS MANQUANTES ! Veuillez configurer les 'Secrets'.\nErreur: {e}")
    st.stop()

# Init API Clients
notion = Client(auth=NOTION_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY) # Init Mistral

# ==============================================================================
# 2. CERVEAU IA (PROMPT SYSTÈME)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es l'IA centrale de l'association Cor-Tech à Cordemais.
Tu remplaces les bénévoles manquants. Tu es autonome, proactif et expert tech.

TES MISSIONS :
1. ADMINISTRATIF : Rédiger emails, PV d'AG, dossiers subventions, synthèses PDF.
2. COM : Créer posts FB/LinkedIn/Twitter, newsletters HTML, communiqués presse.
3. TECH : Expert 3D, Arduino, Code, Gaming. Tu peux débugger et expliquer.
4. GESTION : Planning salles, gestion bénévoles, idées ateliers.
5. VISUEL : Tu sais décrire des images pour les générer.

TON STYLE :
- Pro mais sympa (Esprit Maker/Asso).
- Tu signes "Ton Assistant Cor-Tech 🤖".
- Tu utilises le contexte de l'asso (Lutte fracture numérique, Gaming, Labo Ludik).
"""

# ==============================================================================
# 3. FONCTIONS TECHNIQUES
# ==============================================================================

def send_email_brevo(sujet, html_content, to_email):
    """Envoie un mail HTML via Brevo"""
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": "IA Cor-Tech", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": sujet,
        "htmlContent": f"<html><body>{html_content}</body></html>"
    }
    headers = {"api-key": BREVO_KEY, "content-type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers)
        return r.status_code == 201
    except:
        return False

def send_sms_android(numero, message):
    """Envoie un SMS via passerelle Android (MacroDroid)"""
    if not MACRODROID_URL: return False
    try:
        clean_num = numero.replace(" ", "").replace(".", "")
        params = {"param1": clean_num, "param2": message}
        requests.get(MACRODROID_URL, params=params)
        return True
    except:
        return False

def generate_image_url(prompt):
    """Génère une image via Pollinations"""
    encoded = quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?nologo=true"

def add_notion_task(nom, responsable, priorite, frequence):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_TASKS},
            properties={
                "Nom": {"title": [{"text": {"content": nom}}]},
                "Responsable": {"rich_text": [{"text": {"content": responsable}}]},
                "Priorite": {"select": {"name": priorite}},
                "Frequence": {"select": {"name": frequence}},
                "Statut": {"status": {"name": "À faire"}}
            }
        )
        return True
    except: return False

def add_notion_rappel(msg, dest, jour):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_RAPPELS},
            properties={
                "Message": {"title": [{"text": {"content": msg}}]},
                "Destinataire": {"rich_text": [{"text": {"content": dest}}]},
                "Jour": {"select": {"name": jour}},
                "Actif": {"checkbox": True}
            }
        )
        return True
    except: return False

# ==============================================================================
# 4. MOTEUR D'AUTOMATISATION
# ==============================================================================
@st.cache_resource
def start_daily_scheduler():
    def scheduler_loop():
        print("⏰ Démarrage du Cron Job interne...")
        last_check_date = None
        while True:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            # Vérification quotidienne à partir de 9h
            if last_check_date != today_str and now.hour >= 9:
                print(f"--- Tâches auto du {today_str} ---")
                jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                jour_actuel = jours_fr[now.weekday()]
                try:
                    query = notion.databases.query(
                        database_id=NOTION_DB_RAPPELS,
                        filter={"and": [{"property": "Actif", "checkbox": {"equals": True}}, {"property": "Jour", "select": {"equals": jour_actuel}}]}
                    )
                    results = query.get("results", [])
                    for page in results:
                        props = page["properties"]
                        msg = props["Message"]["title"][0]["text"]["content"]
                        dest = props["Destinataire"]["rich_text"][0]["text"]["content"]
                        send_email_brevo(f"🔔 Rappel Cor-Tech : {msg}", f"<p>C'est {jour_actuel}, pense à : <b>{msg}</b></p>", dest)
                        print(f"✅ Rappel envoyé à {dest}")
                except Exception as e:
                    print(f"❌ Erreur Scheduler : {e}")
                last_check_date = today_str
            time.sleep(3600) 
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    return t

start_daily_scheduler()

# ==============================================================================
# 5. INTERFACE GRAPHIQUE
# ==============================================================================
st.set_page_config(page_title="Cor-Tech OS", page_icon="🤖", layout="wide")

st.title("🚀 Cor-Tech : Centre de Commandement")
st.caption(f"Propulsé par Mistral AI 🇫🇷 • Surveillance active...")

tabs = st.tabs(["💬 Assistant", "🛠️ Tâches", "⏰ Rappels", "⚙️ Admin"])

# --- TAB 1 : CHAT ---
with tabs[0]:
    st.info("💡 Commandes : 'Visuel pour l'atelier', 'Rédige un mail', 'Synthétise'...")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    # Affichage historique
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if "image" in msg: st.image(msg["image"])
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Votre ordre ?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        # --- LOGIQUE MISTRAL ---
        
        # 1. Gestion des Images (On garde Pollinations, mais c'est Mistral qui écrit le prompt)
        if "visuel" in prompt.lower() or "affiche" in prompt.lower() or "image" in prompt.lower():
            # On demande à Mistral de créer le prompt anglais
            try:
                chat_response = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[
                        {"role": "system", "content": "Tu es un expert en art digital. Traduis la demande en un prompt court en anglais pour un générateur d'image."},
                        {"role": "user", "content": prompt}
                    ]
                )
                img_desc = chat_response.choices[0].message.content
                img_url = generate_image_url(img_desc)
                
                with st.chat_message("assistant"):
                    st.image(img_url, caption="Visuel généré par IA")
                    st.markdown(f"[Télécharger]({img_url})")
                st.session_state.messages.append({"role": "assistant", "content": "Visuel généré.", "image": img_url})
            except Exception as e:
                st.error(f"Erreur Image : {e}")

        # 2. Gestion Texte Classique
        else:
            try:
                # On prépare l'historique pour Mistral
                messages_for_mistral = [{"role": "system", "content": SYSTEM_PROMPT}]
                # On ajoute l'historique de session (en filtrant les images)
                for m in st.session_state.messages:
                    if "image" not in m: # On n'envoie pas les images à Mistral (texte uniquement)
                        messages_for_mistral.append({"role": m["role"], "content": m["content"]})
                
                # Appel API Mistral
                chat_response = mistral_client.chat.complete(
                    model="mistral-large-latest", # Le meilleur modèle
                    messages=messages_for_mistral
                )
                
                ai_reply = chat_response.choices[0].message.content
                
                with st.chat_message("assistant"): st.markdown(ai_reply)
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                
            except Exception as e:
                st.error(f"Erreur Mistral AI : {e}")

# --- TAB 2 : TACHES ---
with tabs[1]:
    with st.form("tache"):
        c1, c2 = st.columns(2)
        n = c1.text_input("Quoi faire ?")
        r = c2.text_input("Qui ?", "Sébastien")
        p = c1.selectbox("Priorité", ["Moyenne", "Haute", "Urgente"])
        f = c2.selectbox("Fréquence", ["Ponctuel", "Hebdo"])
        if st.form_submit_button("Ajouter"):
            if add_notion_task(n, r, p, f): st.success("✅ Tâche ajoutée")
            else: st.error("Erreur Notion")

# --- TAB 3 : RAPPELS ---
with tabs[2]:
    with st.form("rappel"):
        c1, c2 = st.columns(2)
        m = c1.text_input("Message")
        d = c2.text_input("Email", TEST_DESTINATAIRE)
        j = st.selectbox("Jour", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"])
        if st.form_submit_button("Programmer"):
            if add_notion_rappel(m, d, j): st.success("✅ Rituel programmé")
            else: st.error("Erreur Notion")
            
    if st.button("Voir les rituels actifs"):
        try:
            res = notion.databases.query(database_id=NOTION_DB_RAPPELS, filter={"property": "Actif", "checkbox": {"equals": True}})
            for pg in res["results"]:
                st.text(f"📅 {pg['properties']['Jour']['select']['name']} : {pg['properties']['Message']['title'][0]['text']['content']}")
        except: st.warning("Rien à afficher")

# --- TAB 4 : ADMIN ---
with tabs[3]:
    c1, c2 = st.columns(2)
    if c1.button("📧 Test Email"):
        if send_email_brevo("Test Agent", "<h1>Ça marche !</h1>", TEST_DESTINATAIRE): st.success("Email OK")
        else: st.error("Erreur Email")
    if c2.button("📱 Test SMS"):
        if MACRODROID_URL:
            num = st.text_input("Numéro")
            if num and st.button("Envoyer"):
                send_sms_android(num, "Test SMS")
        else: st.warning("Pas de MacroDroid configuré")
