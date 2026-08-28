import streamlit as st
import apify_client

# Configuração da página
st.set_page_config(
    page_title="Instagram Reels Downloader",
    page_icon="📥",
    layout="centered"
)

st.title("📥 Instagram Reels Downloader")
st.write("Digite o @ do perfil do Instagram para baixar os vídeos em lote.")

# Tenta carregar o Token do Apify a partir dos Secrets do Streamlit
try:
    APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
except Exception:
    st.error("⚠️ Token do Apify não configurado nos Secrets do Streamlit.")
    st.stop()

# Formulário de Download (Acesso livre sem login)
with st.form("downloader_form"):
    username = st.text_input("Perfil do Instagram (sem @):", placeholder="ex: instagram")
    count = st.number_input("Quantidade de vídeos para buscar:", min_value=1, max_value=20, value=3)
    submit_button = st.form_submit_button("Buscar e Baixar Reels")

if submit_button:
    if not username.strip():
        st.warning("Por favor, digite o nome de usuário do Instagram.")
    else:
        # Remove @ caso o usuário tenha digitado
        clean_username = username.strip().replace("@", "")
        
        with st.spinner(f"Buscando {count} Reels de @{clean_username}..."):
            try:
                # Inicializa o cliente do Apify
                client = apify_client.ApifyClient(APIFY_TOKEN)
                
                # Parâmetros de execução do Actor
                run_input = {
                    "directUrls": [f"https://www.instagram.com/{clean_username}/"],
                    "resultsType": "posts",
                    "resultsLimit": count,
                }
                
                # Executa o Actor do Apify
                run = client.actor("apify/instagram-scraper").call(run_input=run_input)
                
                # Acesso corrigido usando notação de objeto (.default_dataset_id)
                dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
                dataset_items = client.dataset(dataset_id).list_items().items

                video_urls = []
                for item in dataset_items:
                    # Filtra apenas postagens que possuem URL de vídeo
                    if item.get("isVideo") and item.get("videoUrl"):
                        video_urls.append(item.get("videoUrl"))
                    elif item.get("type") == "Video" and item.get("videoUrl"):
                        video_urls.append(item.get("videoUrl"))

                if not video_urls:
                    st.error("Nenhum vídeo/Reel público encontrado para este perfil.")
                else:
                    st.success(f"Encontrados {len(video_urls)} vídeos!")
                    
                    # Exibe os links e tocadores de vídeo
                    for idx, url in enumerate(video_urls, 1):
                        st.write(f"**Vídeo {idx}**")
                        st.video(url)
                        
            except Exception as e:
                st.error(f"Erro ao processar a requisição no Apify: {e}")
