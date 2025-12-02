import streamlit as st
import google.generativeai as genai
from notion_client import Client
import pandas as pd
import requests
import datetime
import time
import threading
from urllib.parse import quote

# ==============================================================================
# 1. CONFIGURATION & SECRETS (Chargement automatique)
# ==============================================================================
try:
    # Récupération des clés depuis les réglages sécurisés de Streamlit
    NOTION_KEY = st.secrets["NOTION_KEY"]
    NOTION_DB_TASKS = st.secrets["NOTION_DB_TASKS_ID"]
    NOTION_DB_RAPPELS = st.secrets["NOTION_DB_RAPPELS_ID"]
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
    BREVO_KEY = st.secrets["BREVO_KEY"]
    # Optionnel : SMS Android (si configuré avec MacroDroid)
    MACRODROID_URL = st.secrets.get("MACRODROID_URL", "") 
    
    # Emails
    SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
    TEST_DESTINATAIRE = st.secrets["TEST_DESTINATAIRE"]
except Exception as e:
    st.error(f"⚠️ CLÉS MANQUANTES ! Veuillez configurer les 'Secrets' sur Streamlit Cloud.\nErreur: {e}")
    st.stop()

# Init API Clients
notion = Client(auth=NOTION_KEY)
genai.configure(api_key=GEMINI_KEY)

# ==============================================================================
# 2. CERVEAU IA (PROMPT SYSTÈME 70 FONCTIONS)
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
# 3. FONCTIONS TECHNIQUES (Mails, SMS, Notion, Images)
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
# 4. MOTEUR D'AUTOMATISATION (Background Thread)
# ==============================================================================
# Ce code tourne en arrière-plan pour vérifier les rappels tous les jours
# Astuce : On utilise le cache de Streamlit pour lancer le thread une seule fois.

@st.cache_resource
def start_daily_scheduler():
    def scheduler_loop():
        print("⏰ Démarrage du Cron Job interne...")
        last_check_date = None
        
        while True:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            
            # On vérifie une fois par jour (par exemple vers 09h00 du matin)
            # Ou simplement : si on a changé de jour par rapport au dernier check
            if last_check_date != today_str and now.hour >= 9:
                
                print(f"--- Exécution des tâches auto du {today_str} ---")
                
                # 1. Quel jour sommes-nous ?
                jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                jour_actuel = jours_fr[now.weekday()]
                
                try:
                    # 2. Récupérer les RAPPELS Notion du jour
                    query = notion.databases.query(
                        database_id=NOTION_DB_RAPPELS,
                        filter={
                            "and": [
                                {"property": "Actif", "checkbox": {"equals": True}},
                                {"property": "Jour", "select": {"equals": jour_actuel}}
                            ]
                        }
                    )
                    
                    # 3. Envoyer les mails
                    results = query.get("results", [])
                    if results:
                        for page in results:
                            props = page["properties"]
                            msg = props["Message"]["title"][0]["text"]["content"]
                            dest = props["Destinataire"]["rich_text"][0]["text"]["content"]
                            
                            # Envoi Mail
                            send_email_brevo(
                                f"🔔 Rappel Cor-Tech : {msg}", 
                                f"<p>Bonjour,</p><p>C'est {jour_actuel}, pense à : <b>{msg}</b></p>", 
                                dest
                            )
                            print(f"✅ Rappel envoyé à {dest}")
                except Exception as e:
                    print(f"❌ Erreur Scheduler : {e}")
                
                last_check_date = today_str
            
            # On dort 1 heure avant de re-vérifier l'heure
            time.sleep(3600) 

    # Lancement du thread
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    return t

# Démarrage du moteur au lancement de l'app
start_daily_scheduler()

# ==============================================================================
# 5. INTERFACE GRAPHIQUE (Streamlit)
# ==============================================================================
st.set_page_config(page_title="Cor-Tech OS", page_icon="🤖", layout="wide")

st.title("🚀 Cor-Tech : Centre de Commandement")
st.caption("Agent Autonome Actif • Surveillance des rappels en cours...")

# Onglets
tabs = st.tabs(["💬 Assistant & Création", "🛠️ Gestion Tâches", "⏰ Rituels & Rappels", "⚙️ Admin / Test"])

# --- TAB 1 : CHAT INTELLIGENT ---
with tabs[0]:
    st.info("💡 Demandez : 'Rédige la newsletter', 'Crée un visuel pour l'atelier 3D', 'Synthétise ce texte'...")
    
    if "messages" not in st.session_state: st.session_state.messages = []
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if "image" in msg: st.image(msg["image"])
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Votre ordre ?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        # Logique IA + Image
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Détection d'intention "Image"
        if "visuel" in prompt.lower() or "affiche" in prompt.lower() or "image" in prompt.lower():
            # 1. On demande à Gemini de créer le prompt anglais
            prompt_img_gen = f"Crée une description en anglais courte (prompt) pour générer une image : {prompt}"
            img_desc = model.generate_content(prompt_img_gen).text
            img_url = generate_image_url(img_desc)
            
            # 2. On affiche l'image
            with st.chat_message("assistant"):
                st.image(img_url, caption="Visuel généré par IA")
                st.markdown(f"Voici le visuel demandé. [Télécharger]({img_url})")
            
            st.session_state.messages.append({"role": "assistant", "content": "Visuel généré.", "image": img_url})
            
        else:
            # Réponse Texte classique
            response = model.generate_content(f"{SYSTEM_PROMPT}\nHistorique: {st.session_state.messages}\nUser: {prompt}")
            with st.chat_message("assistant"):
                st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})

# --- TAB 2 : TACHES ---
with tabs[1]:
    st.subheader("Ajout rapide")
    with st.form("tache"):
        c1, c2 = st.columns(2)
        n = c1.text_input("Quoi faire ?")
        r = c2.text_input("Qui ?", "Sébastien")
        p = c1.selectbox("Priorité", ["Moyenne", "Haute", "Urgente"])
        f = c2.selectbox("Fréquence", ["Ponctuel", "Hebdo"])
        if st.form_submit_button("Ajouter"):
            if add_notion_task(n, r, p, f): st.success("✅ Tâche ajoutée")
            else: st.error("Erreur connexion Notion")

# --- TAB 3 : RAPPELS ---
with tabs[2]:
    st.subheader("Programmer un rituel")
    with st.form("rappel"):
        c1, c2 = st.columns(2)
        m = c1.text_input("Message")
        d = c2.text_input("Email", TEST_DESTINATAIRE)
        j = st.selectbox("Jour", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"])
        if st.form_submit_button("Programmer"):
            if add_notion_rappel(m, d, j): st.success("✅ Rituel programmé")
            else: st.error("Erreur connexion Notion")
            
    if st.button("Voir les rituels actifs"):
        try:
            res = notion.databases.query(database_id=NOTION_DB_RAPPELS, filter={"property": "Actif", "checkbox": {"equals": True}})
            for pg in res["results"]:
                st.text(f"📅 {pg['properties']['Jour']['select']['name']} : {pg['properties']['Message']['title'][0]['text']['content']}")
        except: st.warning("Rien à afficher")

# --- TAB 4 : TESTS ---
with tabs[3]:
    st.markdown("### Tests de connexion")
    c1, c2 = st.columns(2)
    if c1.button("📧 Test Email"):
        if send_email_brevo("Test Agent", "<h1>Ça marche !</h1>", TEST_DESTINATAIRE):
            st.success("Email OK")
        else: st.error("Erreur Email")
        
    if c2.button("📱 Test SMS"):
        if MACRODROID_URL:
            # Mettre un numéro de test ici ou demander via input
            num_test = st.text_input("Numéro pour le test SMS")
            if num_test and st.button("Envoyer SMS"):
                if send_sms_android(num_test, "Test SMS Cor-Tech"): st.success("SMS Envoyé au téléphone")
        else:
            st.warning("URL MacroDroid non configurée dans les Secrets")
