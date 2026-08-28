import io
import os
import tempfile
import zipfile
import requests
import streamlit as st
import subprocess
from supabase import create_client, Client

# 1. Configurações de API e Banco de Dados
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "SUA_SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "SUA_SUPABASE_KEY")
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/SEU_LINK_DE_PAGAMENTO"

# Inicializa conexão com Supabase
@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.set_page_config(page_title="Reels Downloader Pro", page_icon="⚡")

# 2. Tela de Login / Cadastro
if "user" not in st.session_state:
    st.session_state.user = None

def login_form():
    st.sidebar.title("🔐 Área do Usuário")
    opcao = st.sidebar.radio("Escolha:", ["Login", "Cadastrar"])
    
    email = st.sidebar.text_input("E-mail")
    password = st.sidebar.text_input("Senha", type="password")
    
    if opcao == "Cadastrar":
        if st.sidebar.button("Criar Conta"):
            res = supabase.auth.sign_up({"email": email, "password": password})
            st.sidebar.success("Conta criada com sucesso! Faça login.")
    else:
        if st.sidebar.button("Entrar"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.sidebar.success("Login realizado!")
                st.rerun()
            except Exception as e:
                st.sidebar.error("E-mail ou senha inválidos.")

if not st.session_state.user:
    st.title("🎬 Instagram Reels Downloader Pro")
    st.info("Faça login ou crie uma conta na barra lateral para acessar o sistema.")
    login_form()
    st.stop()

# 3. Verificação de Assinatura / Créditos
user_id = st.session_state.user.id
user_email = st.session_state.user.email

st.sidebar.write(f"Conectado como: **{user_email}**")
if st.sidebar.button("Sair"):
    st.session_state.user = None
    st.rerun()

# Consulta o status do usuário no banco de dados
profile = supabase.table("profiles").select("*").eq("id", user_id).execute()

is_vip = False
if profile.data:
    is_vip = profile.data[0].get("is_vip", False)

# 4. Bloqueio de Conteúdo para Não-Pagantes
if not is_vip:
    st.title("⭐ Assine o Plano Pro")
    st.warning("Sua conta ainda não possui uma assinatura ativa para baixar os vídeos.")
    st.markdown(f"[👉 Clique aqui para assinar por R$ 29,90/mês no Stripe]({STRIPE_PAYMENT_LINK})")
    st.info("Após efetuar o pagamento, seu acesso será liberado automaticamente.")
    st.stop()

# 5. Aplicação Principal (Liberada para Assinantes)
st.title("🎬 Painel de Download de Reels (VIP)")

apify_token = st.secrets.get("APIFY_TOKEN", "")
username = st.text_input("Digite o @ do perfil do Instagram:")

col1, col2 = st.columns(2)
with col1:
    filtro = st.selectbox("Ordenar por:", ["Últimos publicados", "Mais virais (Views)"])
with col2:
    quantidade = st.number_input("Quantidade de vídeos:", min_value=1, max_value=50, value=5)

if st.button("Buscar e Gerar ZIP"):
    if not username:
        st.error("Insira o nome de usuário do Instagram.")
        st.stop()

    st.info("1/4 - Buscando Reels via Apify...")
    actor_url = f"https://api.apify.com/v2/acts/apify~instagram-reel-scraper/run-sync-get-dataset-items?token={apify_token}"
    payload = {"username": [username], "resultsLimit": int(quantidade * 2)}
    
    response = requests.post(actor_url, json=payload)
    if response.status_code not in [200, 201]:
        st.error("Erro ao buscar dados do Instagram.")
        st.stop()
        
    reels_data = response.json()
    if not reels_data:
        st.warning("Nenhum vídeo encontrado.")
        st.stop()

    if filtro == "Mais virais (Views)":
        reels_data = sorted(reels_data, key=lambda x: x.get("playCount", 0), reverse=True)
    
    selected_reels = reels_data[:int(quantidade)]

    st.info("2/4 - Baixando os vídeos...")
    with tempfile.TemporaryDirectory() as temp_dir:
        links_file = os.path.join(temp_dir, "links.txt")
        download_folder = os.path.join(temp_dir, "downloads")
        os.makedirs(download_folder, exist_ok=True)
        
        with open(links_file, "w") as f:
            for item in selected_reels:
                raw_url = item.get("url")
                if raw_url:
                    clean_url = raw_url.rstrip("/")
                    f.write(f"{clean_url}/embed/captioned/\n")

        cmd = [
            "yt-dlp",
            "--referer", "https://www.instagram.com/",
            "-a", links_file,
            "-o", os.path.join(download_folder, "%(id)s.%(ext)s"),
            "--sleep-interval", "2",
            "--max-sleep-interval", "4"
        ]
        subprocess.run(cmd)

        st.info("3/4 - Compactando arquivos...")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(download_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    zip_file.write(file_path, arcname=file)

        zip_buffer.seek(0)
        st.success("Tudo pronto!")
        st.download_button(
            label="📦 Baixar Vídeos (.ZIP)",
            data=zip_buffer,
            file_name=f"{username}_reels.zip",
            mime="application/zip"
        )
