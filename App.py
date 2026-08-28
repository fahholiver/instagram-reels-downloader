import streamlit as st
import apify_client
import requests
import zipfile
import io

# Configuração da página
st.set_page_config(
    page_title="Instagram Reels Downloader",
    page_icon="📥",
    layout="centered"
)

st.title("📥 Instagram Reels Downloader")
st.write("Digite o @ do perfil do Instagram para baixar os vídeos em lote em um arquivo ZIP.")

# Tenta carregar o Token do Apify a partir dos Secrets do Streamlit
try:
    APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
except Exception:
    st.error("⚠️ Token do Apify não configurado nos Secrets do Streamlit.")
    st.stop()

# Formulário de Download
with st.form("downloader_form"):
    username = st.text_input("Perfil do Instagram (sem @):", placeholder="ex: instagram")
    count = st.number_input("Quantidade de vídeos para buscar:", min_value=1, max_value=20, value=3)
    submit_button = st.form_submit_button("Buscar e Baixar Reels (ZIP)")

if submit_button:
    if not username.strip():
        st.warning("Por favor, digite o nome de usuário do Instagram.")
    else:
        clean_username = username.strip().replace("@", "")
        
        with st.spinner(f"Buscando {count} Reels de @{clean_username}..."):
            try:
                client = apify_client.ApifyClient(APIFY_TOKEN)
                
                run_input = {
                    "directUrls": [f"https://www.instagram.com/{clean_username}/"],
                    "resultsType": "posts",
                    "resultsLimit": count,
                }
                
                run = client.actor("apify/instagram-scraper").call(run_input=run_input)
                
                dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
                dataset_items = client.dataset(dataset_id).list_items().items

                video_urls = []
                for item in dataset_items:
                    if item.get("isVideo") and item.get("videoUrl"):
                        video_urls.append(item.get("videoUrl"))
                    elif item.get("type") == "Video" and item.get("videoUrl"):
                        video_urls.append(item.get("videoUrl"))

                if not video_urls:
                    st.error("Nenhum vídeo/Reel público encontrado para este perfil.")
                else:
                    st.success(f"Encontrados {len(video_urls)} vídeos! Baixando e compactando...")
                    
                    # Barra de progresso do download
                    progress_bar = st.progress(0)
                    
                    # Cria o arquivo ZIP em memória
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        }
                        
                        for idx, url in enumerate(video_urls, 1):
                            try:
                                response = requests.get(url, headers=headers, timeout=30)
                                if response.status_code == 200:
                                    video_filename = f"reel_{clean_username}_{idx}.mp4"
                                    zip_file.writestr(video_filename, response.content)
                            except Exception as req_err:
                                st.warning(f"Não foi possível baixar o vídeo {idx}: {req_err}")
                            
                            progress_bar.progress(idx / len(video_urls))

                    zip_buffer.seek(0)
                    
                    st.success("ZIP gerado com sucesso!")
                    
                    # Botão nativo do Streamlit para baixar o arquivo no computador ou celular
                    st.download_button(
                        label="💾 Baixar todos os vídeos (.ZIP)",
                        data=zip_buffer,
                        file_name=f"reels_{clean_username}.zip",
                        mime="application/zip"
                    )

                    # Exibe também as prévias dos vídeos na tela
                    st.write("---")
                    st.subheader("Pré-visualização dos vídeos:")
                    for idx, url in enumerate(video_urls, 1):
                        st.write(f"**Vídeo {idx}**")
                        st.video(url)
                        
            except Exception as e:
                st.error(f"Erro ao processar a requisição no Apify: {e}")
