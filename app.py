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

# CSS : Barre de chat fixée en bas + Style des boutons
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
# 2. CERVEAU IA (PROMPT SYSTÈME AVANCÉ)
# ==============================================================================
SYSTEM_PROMPT = f"""
Tu es l'IA de l'association Cor-Tech. Tu es autonome et proactif.

RÈGLE D'OR POUR LES EMAILS :
Si l'utilisateur te demande de PRÉPARER, RÉDIGER ou ENVOYER un email, tu ne dois PAS juste écrire le texte.
Tu dois générer un bloc de code JSON strict encadré par des balises spéciales <EMAIL_DRAFT> ... </EMAIL_DRAFT>.

Format attendu :
<EMAIL_DRAFT>
{{
  "destinataire": "email@exemple.com",
  "sujet": "Sujet du mail",
  "corps_html": "<p>Bonjour...</p>"
}}
</EMAIL_DRAFT>

Si l'utilisateur ne précise pas l'email du destinataire, utilise "{TEST_DESTINATAIRE}" par défaut.
Pour le reste (chat normal), réponds normalement en texte.
"""

# ==============================================================================
# 3. FONCTIONS TECHNIQUES
# ==============================================================================

def send_email_brevo_debug(sujet, html_content, to_email):
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
        if r.status_code == 201: return True, "✅ Envoyé !"
        else: return False, f"❌ Erreur Brevo ({r.status_code}) : {r.text}"
    except Exception as e: return False, f"❌ Erreur Script : {e}"

def generate_image_url(prompt):
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
# 4. MOTEUR AUTOMATIQUE
# ==============================================================================
@st.cache_resource
def start_daily_scheduler():
    def scheduler_loop():
        print("⏰ Cron Job démarré")
        last_check = None
        while True:
            now = datetime.datetime.now()
            today = now.strftime("%Y-%m-%d")
            if last_check != today and now.hour >= 9:
                jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                jour_actuel = jours[now.weekday()]
                try:
                    q = notion.databases.query(
                        database_id=NOTION_DB_RAPPELS,
                        filter={"and": [{"property": "Actif", "checkbox": {"equals": True}}, {"property": "Jour", "select": {"equals": jour_actuel}}]}
                    )
                    for p in q.get("results", []):
                        msg = p["properties"]["Message"]["title"][0]["text"]["content"]
                        dest = p["properties"]["Destinataire"]["rich_text"][0]["text"]["content"]
                        send_email_brevo_debug(f"🔔 Rappel : {msg}", f"<p>C'est {jour_actuel}, pense à : <b>{msg}</b></p>", dest)
                except: pass
                last_check = today
            time.sleep(3600) 
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

start_daily_scheduler()

# ==============================================================================
# 5. INTERFACE UTILISATEUR
# ==============================================================================

# --- STATE MANAGEMENT (Mémoire) ---
if "messages" not in st.session_state: st.session_state.messages = []
if "email_draft" not in st.session_state: st.session_state.email_draft = None

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=50)
    st.title("Cor-Tech OS")
    menu = st.radio("Navigation", ["💬 Chat Assistant", "🛠️ Gestion Tâches", "⏰ Rituels", "⚙️ Admin"], label_visibility="collapsed")
    st.divider()
    if st.button("🗑️ Reset Mémoire"):
        st.session_state.messages = []
        st.session_state.email_draft = None
        st.rerun()

# --- PAGES ---

if menu == "💬 Chat Assistant":
    st.markdown("### 🤖 Assistant Bénévole")
    
    # 1. ZONE D'AFFICHAGE DU BROUILLON (Si un mail est prêt)
    if st.session_state.email_draft:
        with st.expander("📝 BROUILLON PRÊT - Valider l'envoi ?", expanded=True):
            st.info("L'IA a préparé ce mail. Vous pouvez le modifier avant envoi.")
            
            with st.form("confirm_email"):
                d_to = st.text_input("Destinataire", st.session_state.email_draft["destinataire"])
                d_sub = st.text_input("Sujet", st.session_state.email_draft["sujet"])
                d_body = st.text_area("Corps (HTML ou Texte)", st.session_state.email_draft["corps_html"], height=200)
                
                c1, c2 = st.columns([1, 4])
                if c1.form_submit_button("🚀 ENVOYER"):
                    with st.spinner("Envoi..."):
                        ok, log = send_email_brevo_debug(d_sub, d_body, d_to)
                        if ok:
                            st.success(log)
                            st.session_state.email_draft = None # On vide le brouillon
                            st.session_state.messages.append({"role": "assistant", "content": f"✅ Mail envoyé à {d_to}"})
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(log)
                
                if c2.form_submit_button("❌ Annuler"):
                    st.session_state.email_draft = None
                    st.rerun()

    # 2. ZONE DE CHAT
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if "image" in msg: st.image(msg["image"], width=400)
            if "content" in msg: st.markdown(msg["content"])

    # 3. SAISIE
    if prompt := st.chat_input("Ex: Prépare un mail de bienvenue pour folgoas@live.fr..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        # A. MODE IMAGE
        if any(x in prompt.lower() for x in ["visuel", "affiche", "image"]):
            try:
                res = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": f"Prompt anglais court pour image artistique: {prompt}"}]
                )
                desc = res.choices[0].message.content
                url = generate_image_url(desc)
                with st.chat_message("assistant"):
                    st.image(url)
                    st.markdown(f"[Télécharger]({url})")
                st.session_state.messages.append({"role": "assistant", "content": "Visuel généré.", "image": url})
            except: st.error("Erreur image")

        # B. MODE TEXTE / EMAIL
        else:
            try:
                hist = [{"role": "system", "content": SYSTEM_PROMPT}]
                for m in st.session_state.messages:
                    if "image" not in m: hist.append({"role": m["role"], "content": m["content"]})
                
                res = mistral_client.chat.complete(model="mistral-large-latest", messages=hist)
                reply = res.choices[0].message.content

                # DETECTION DU JSON EMAIL
                if "<EMAIL_DRAFT>" in reply:
                    # Extraction du JSON
                    json_str = reply.split("<EMAIL_DRAFT>")[1].split("</EMAIL_DRAFT>")[0]
                    try:
                        email_data = json.loads(json_str)
                        st.session_state.email_draft = email_data
                        st.session_state.messages.append({"role": "assistant", "content": "Je t'ai préparé le brouillon ci-dessus ⬆️"})
                        st.rerun() # On recharge pour afficher le formulaire
                    except:
                        st.error("Erreur de lecture du format email IA.")
                        st.write(reply)
                else:
                    # Réponse classique
                    with st.chat_message("assistant"): st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})

            except Exception as e: st.error(f"Erreur Mistral: {e}")

elif menu == "🛠️ Gestion Tâches":
    st.header("Nouvelle Mission")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        n = c1.text_input("Tâche")
        r = c2.text_input("Responsable", "Sébastien")
        p = c1.selectbox("Priorité", ["Moyenne", "Haute", "Urgente"])
        f = c2.selectbox("Fréquence", ["Ponctuel", "Hebdo"])
        if st.button("Ajouter", type="primary"):
            if add_notion_task(n, r, p, f): st.success("Noté !")
            else: st.error("Erreur Notion")

elif menu == "⏰ Rituels":
    st.header("Rappels")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        m = c1.text_input("Message")
        d = c2.text_input("Email", TEST_DESTINATAIRE)
        j = st.selectbox("Jour", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"])
        if st.button("Programmer"):
            if add_notion_rappel(m, d, j): st.success("Activé !")
            else: st.error("Erreur Notion")

elif menu == "⚙️ Admin":
    st.header("Debug")
    if st.button("Test Email Rapide"):
        ok, msg = send_email_brevo_debug("Test", "Test", TEST_DESTINATAIRE)
        if ok: st.success(msg)
        else: st.error(msg)
