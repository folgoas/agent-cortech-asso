import streamlit as st
from mistralai import Mistral
from notion_client import Client
import requests
import datetime
import time
import threading
from urllib.parse import quote

# ==============================================================================
# 1. CONFIGURATION & STYLE
# ==============================================================================
st.set_page_config(page_title="Cor-Tech OS", page_icon="🤖", layout="wide")

# CSS pour masquer les éléments inutiles et fixer la barre de chat
st.markdown("""
<style>
    .stChatInput {position: fixed; bottom: 0; padding-bottom: 20px; z-index: 100;}
    .block-container {padding-bottom: 120px;} /* Espace pour ne pas cacher le dernier message */
</style>
""", unsafe_allow_html=True)

try:
    # Récupération des clés
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

# Init Clients
notion = Client(auth=NOTION_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# ==============================================================================
# 2. FONCTIONS TECHNIQUES (Avec DEBUG Email)
# ==============================================================================

def send_email_brevo_debug(sujet, html_content, to_email):
    """Envoie un mail avec retour d'erreur précis"""
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
        if r.status_code == 201:
            return True, "✅ Envoyé"
        else:
            # On retourne le code erreur et le message technique de Brevo
            return False, f"❌ Erreur Brevo ({r.status_code}) : {r.text}"
    except Exception as e:
        return False, f"❌ Erreur Script : {e}"

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
# 3. MOTEUR AUTOMATIQUE (Background)
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
# 4. INTERFACE UTILISATEUR (Nouvelle UI)
# ==============================================================================

# --- SIDEBAR (Navigation) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=50)
    st.title("Cor-Tech OS")
    st.caption("Mistral AI Connected 🟢")
    
    menu = st.radio("Navigation", ["💬 Chat Assistant", "🛠️ Gestion Tâches", "⏰ Rituels", "⚙️ Admin / Debug"], label_visibility="collapsed")
    
    st.divider()
    st.markdown("### 📊 État Rapide")
    # Petit widget pour voir si Notion répond
    if st.button("Test Connexion Notion"):
        try:
            u = notion.users.me()
            st.success("Notion OK")
        except: st.error("Notion HS")

# --- PAGE PRINCIPALE (Dynamique) ---

if menu == "💬 Chat Assistant":
    # Entête discret
    st.markdown("### 🤖 Assistant Bénévole")
    st.caption("Expert Tech, Administratif & Communication. Propulsé par Mistral Large.")

    if "messages" not in st.session_state: st.session_state.messages = []

    # Zone d'affichage des messages (Scrolle naturellement)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if "image" in msg: st.image(msg["image"], width=400)
            st.markdown(msg["content"])

    # Zone de saisie (Fixée en bas grâce au CSS)
    if prompt := st.chat_input("Demandez une tâche, un mail, un visuel..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        # LOGIQUE MISTRAL
        if any(x in prompt.lower() for x in ["visuel", "affiche", "image"]):
            try:
                # 1. Mistral créé le prompt
                res = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": f"Crée un prompt court en anglais pour générer une image artistique : {prompt}"}]
                )
                desc = res.choices[0].message.content
                url = generate_image_url(desc)
                
                with st.chat_message("assistant"):
                    st.image(url, caption="Généré par Pollinations")
                    st.markdown(f"[Télécharger l'image]({url})")
                st.session_state.messages.append({"role": "assistant", "content": "Visuel généré.", "image": url})
            except Exception as e: st.error(f"Erreur Image: {e}")
        else:
            try:
                # 2. Mistral Chat normal
                hist = [{"role": "system", "content": "Tu es l'assistant de l'asso Cor-Tech. Ton pro, sympa, tech. Tu rédiges mails, posts, documents."}]
                for m in st.session_state.messages:
                    if "image" not in m: hist.append({"role": m["role"], "content": m["content"]})
                
                res = mistral_client.chat.complete(model="mistral-large-latest", messages=hist)
                reply = res.choices[0].message.content
                
                with st.chat_message("assistant"): st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e: st.error(f"Erreur Mistral: {e}")

elif menu == "🛠️ Gestion Tâches":
    st.header("Nouvelle Mission")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        n = c1.text_input("Tâche à faire")
        r = c2.text_input("Qui s'en occupe ?", "Sébastien")
        p = c1.selectbox("Priorité", ["Moyenne", "Haute", "Urgente"])
        f = c2.selectbox("Fréquence", ["Ponctuel", "Hebdomadaire"])
        if st.button("Enregistrer la tâche", type="primary"):
            if add_notion_task(n, r, p, f): st.success("C'est noté dans Notion !")
            else: st.error("Erreur de connexion Notion")

elif menu == "⏰ Rituels":
    st.header("Rappels Automatiques")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        m = c1.text_input("Message du rappel")
        d = c2.text_input("Email destinataire", TEST_DESTINATAIRE)
        j = st.selectbox("Jour", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"])
        if st.button("Programmer le rituel"):
            if add_notion_rappel(m, d, j): st.success("Rituel activé !")
            else: st.error("Erreur Notion")

elif menu == "⚙️ Admin / Debug":
    st.header("Centre de diagnostic")
    st.info("Utilisez cette page pour comprendre pourquoi les mails ne partent pas.")
    
    st.markdown("#### 1. Test Email (Debug Mode)")
    col_a, col_b = st.columns(2)
    email_test = col_a.text_input("Envoyer à", TEST_DESTINATAIRE)
    
    if col_a.button("Lancer le test Email"):
        with st.spinner("Tentative d'envoi..."):
            succes, message = send_email_brevo_debug("Test Debug Cor-Tech", "<h1>Ceci est un test</h1>", email_test)
            if succes:
                st.success(message)
            else:
                st.error(message)
                st.warning("👉 Vérifiez que 'SENDER_EMAIL' dans vos secrets correspond bien à votre compte Brevo validé.")

    st.markdown("#### 2. Test SMS")
    tel = col_b.text_input("Numéro")
    if col_b.button("Test SMS"):
        # Logique SMS ici (identique V1)
        st.info("Appel MacroDroid lancé...")
