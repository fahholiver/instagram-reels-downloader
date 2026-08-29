import streamlit as st
import apify_client
import requests
import zipfile
import io
import os
import shutil
import tempfile
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from supabase import create_client, ClientOptions
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Configuração da página
st.set_page_config(
    page_title="Instagram Reels Downloader",
    page_icon="📥",
    layout="centered"
)

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DO TEMPLATE (ajuste estes valores para mudar o layout)
# -----------------------------------------------------------------------------
CANVAS_WIDTH = 1080          # Largura final do vídeo gerado
CANVAS_HEIGHT = 1920         # Altura final fixa (proporção 9:16, padrão Reels)

HEADER_HEIGHT = 560          # Altura da faixa com avatar + nome + @ + legenda (ajustado p/ margem maior)
BOX_TOP_MARGIN = 20          # Espaço entre o header e a caixa do vídeo
BOX_BOTTOM_MARGIN = 40       # Espaço em branco abaixo da caixa (igual à margem lateral)
BOX_HEIGHT = CANVAS_HEIGHT - HEADER_HEIGHT - BOX_TOP_MARGIN - BOX_BOTTOM_MARGIN
# Altura da caixa (o "limite" do vídeo) é o que sobra depois das margens acima

AVATAR_SIZE = 110
AVATAR_MARGIN_TOP = 300      # margem grande no topo, como no seu exemplo

BOX_SIDE_MARGIN = 40        # margem branca nas laterais da caixa do vídeo (mesma do avatar)

# Fontes (instaladas via packages.txt -> fonts-dejavu-core). Se não existirem,
# cai para a fonte padrão do Pillow (mais simples, mas funciona).
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG_COLOR = (255, 255, 255)
TEXT_COLOR = (10, 10, 10)
HANDLE_COLOR = (100, 100, 100)
BOX_COLOR = (255, 255, 255)   # fundo/limite do vídeo agora é branco (era preto)
VERIFIED_BLUE = (59, 130, 246)

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PUBLICAÇÃO NO INSTAGRAM (Instagram API with Instagram Login)
# -----------------------------------------------------------------------------
# Esse é o host certo para tokens que começam com "IGAA" (gerados via login direto
# do Instagram, sem precisar de Página do Facebook vinculada). É diferente do
# graph.facebook.com, usado no fluxo antigo via Facebook Login.
IG_GRAPH_BASE = "https://graph.instagram.com"
IG_STORAGE_BUCKET = "reels-videos"  # bucket público no Supabase Storage (criar manualmente)
IG_CONTAINER_POLL_SECONDS = 5
IG_CONTAINER_MAX_WAIT_SECONDS = 180


# -----------------------------------------------------------------------------
# FUNÇÕES DE TEMPLATE / VÍDEO
# -----------------------------------------------------------------------------
def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def crop_avatar_region(img, zoom, offset_x_pct, offset_y_pct):
    """
    Recorta uma região quadrada da imagem original, controlada por zoom
    (1.0 = sem zoom, mostra o maior quadrado possível) e posição
    horizontal/vertical (0 a 100%, para "passear" pela imagem quando
    o zoom deixa sobra para os lados).
    """
    width, height = img.size
    base_side = min(width, height)
    side = base_side / max(zoom, 1.0)
    side = max(side, 10)  # nunca deixar o lado zerar

    max_x_offset = max(width - side, 0)
    max_y_offset = max(height - side, 0)

    x0 = (offset_x_pct / 100.0) * max_x_offset
    y0 = (offset_y_pct / 100.0) * max_y_offset

    box = (x0, y0, x0 + side, y0 + side)
    return img.crop(box)


def make_circular_avatar(image_data, size):
    """
    Recorta a foto de perfil em um círculo, sem distorcer.
    Aceita tanto bytes quanto um objeto PIL.Image (já recortado/com zoom aplicado).
    """
    if isinstance(image_data, Image.Image):
        img = image_data.convert("RGBA")
    else:
        img = Image.open(io.BytesIO(image_data)).convert("RGBA")
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((0, 0, size, size), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)
    return output


def draw_verified_badge(draw_ctx, x, y, size=34):
    """Desenha um selo azul de verificado com um check branco."""
    draw_ctx.ellipse((x, y, x + size, y + size), fill=VERIFIED_BLUE)
    cx, cy = x + size / 2, y + size / 2
    draw_ctx.line(
        [
            (cx - size * 0.22, cy),
            (cx - size * 0.05, cy + size * 0.2),
            (cx + size * 0.25, cy - size * 0.22),
        ],
        fill=(255, 255, 255),
        width=max(2, size // 8),
        joint="curve",
    )


def build_background_canvas(avatar_bytes, full_name, username, verified, caption=""):
    """
    Monta o fundo estático: avatar + nome + selo + @usuario no topo, e a
    caixa preta (o LIMITE onde o vídeo será posicionado) logo abaixo.
    Retorna: (caminho_png, box_x, box_y, box_w, box_h)
    """
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # --- Calcula a largura do bloco (avatar + espaço + texto) para centralizar ---
    avatar_text_gap = 30
    name_font = load_font(FONT_BOLD_PATH, 46)
    handle_font = load_font(FONT_REGULAR_PATH, 36)

    display_name = full_name or username
    handle_text = f"@{username}"

    name_w = draw.textlength(display_name, font=name_font)
    handle_w = draw.textlength(handle_text, font=handle_font)

    badge_size = 36
    badge_gap = 14
    name_line_w = name_w + (badge_gap + badge_size if verified else 0)

    text_block_w = max(name_line_w, handle_w)
    total_block_w = AVATAR_SIZE + avatar_text_gap + text_block_w

    block_start_x = (CANVAS_WIDTH - total_block_w) / 2
    avatar_x = block_start_x
    text_x = block_start_x + AVATAR_SIZE + avatar_text_gap

    # --- Avatar ---
    avatar_pasted = False
    if avatar_bytes:
        try:
            avatar = make_circular_avatar(avatar_bytes, AVATAR_SIZE)
            canvas.paste(avatar, (int(avatar_x), AVATAR_MARGIN_TOP), avatar)
            avatar_pasted = True
        except Exception as avatar_err:
            avatar_pasted = False
            st.warning(f"Não foi possível usar a foto de perfil no template: {avatar_err}")

    if not avatar_pasted:
        draw.ellipse(
            (
                avatar_x,
                AVATAR_MARGIN_TOP,
                avatar_x + AVATAR_SIZE,
                AVATAR_MARGIN_TOP + AVATAR_SIZE,
            ),
            fill=(210, 210, 210),
        )

    # --- Nome + selo verificado ---
    name_y = AVATAR_MARGIN_TOP + 2
    draw.text((text_x, name_y), display_name, font=name_font, fill=TEXT_COLOR)

    if verified:
        draw_verified_badge(draw, text_x + name_w + badge_gap, name_y + 6, size=badge_size)

    handle_y = name_y + 58
    draw.text((text_x, handle_y), handle_text, font=handle_font, fill=HANDLE_COLOR)

    # --- Legenda opcional (texto extra abaixo do @) ---
    if caption:
        cap_font = load_font(FONT_BOLD_PATH, 34)
        cap_y = handle_y + 70
        wrapped = textwrap.fill(caption, width=42)
        draw.multiline_text(
            (CANVAS_WIDTH / 2, cap_y),
            wrapped,
            font=cap_font,
            fill=TEXT_COLOR,
            anchor="ma",
            align="center",
            spacing=6,
        )

    # --- Caixa = o limite onde o vídeo pode ocupar (com margem nas laterais) ---
    box_x, box_y = BOX_SIDE_MARGIN, HEADER_HEIGHT + BOX_TOP_MARGIN
    box_w, box_h = CANVAS_WIDTH - (2 * BOX_SIDE_MARGIN), BOX_HEIGHT
    draw.rectangle((box_x, box_y, box_x + box_w, box_y + box_h), fill=BOX_COLOR)

    tmp_path = os.path.join(tempfile.gettempdir(), f"bg_{username}.png")
    canvas.save(tmp_path)
    return tmp_path, box_x, box_y, box_w, box_h


def compose_video_with_template(video_path, background_png, box_x, box_y, box_w, box_h, output_path):
    """
    Usa o FFmpeg para:
      1) Redimensionar o vídeo original para CABER dentro da caixa (contain
         fit) sem cortar nada. Se o vídeo for vertical, ele bate no limite
         de ALTURA da caixa; se for mais horizontal, bate no limite de
         LARGURA. As sobras continuam pretas (mesma cor da caixa).
      2) Sobrepor o vídeo redimensionado, centralizado, no fundo estático
         (avatar + nome + @ + caixa).
    """
    filter_complex = (
        f"[1:v]scale={box_w}:{box_h}:force_original_aspect_ratio=decrease[vid];"
        f"[0:v][vid]overlay="
        f"x={box_x}+({box_w}-overlay_w)/2:y={box_y}+({box_h}-overlay_h)/2[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", background_png,
        "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "1:a?",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Erro no FFmpeg: {result.stderr[-800:]}")


def download_bytes(url, headers, timeout=30):
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.content


# -----------------------------------------------------------------------------
# FUNÇÕES DE PUBLICAÇÃO NO INSTAGRAM (Meta Graph API)
# -----------------------------------------------------------------------------
def get_ig_login_account(access_token):
    """
    Para tokens do tipo Instagram API with Instagram Login (prefixo IGAA).
    Não existe /me/accounts aqui -- a própria conta já vem direto em /me.
    """
    resp = requests.get(
        f"{IG_GRAPH_BASE}/me",
        params={"fields": "user_id,username,account_type", "access_token": access_token},
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or "user_id" not in data:
        raise RuntimeError(f"Erro ao buscar a conta: {data}")
    return data


def upload_video_to_supabase_storage(supabase_client, local_path, dest_filename, bucket=IG_STORAGE_BUCKET):
    """
    Sobe o vídeo para um bucket público do Supabase Storage e retorna a URL
    pública -- a Meta precisa conseguir baixar o vídeo por essa URL.
    """
    with open(local_path, "rb") as f:
        file_bytes = f.read()

    supabase_client.storage.from_(bucket).upload(
        dest_filename,
        file_bytes,
        {"content-type": "video/mp4", "upsert": "true"},
    )
    public_url = supabase_client.storage.from_(bucket).get_public_url(dest_filename)
    return public_url


def create_media_container(ig_user_id, video_url, caption, access_token):
    """Cria o container do Reels (etapa 1 de 2 da publicação)."""
    resp = requests.post(
        f"{IG_GRAPH_BASE}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption or "",
            "access_token": access_token,
        },
        timeout=60,
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise RuntimeError(f"Erro ao criar container: {data}")
    return data["id"]


def wait_for_container_ready(container_id, access_token):
    """Aguarda a Meta terminar de processar o vídeo (status_code=FINISHED)."""
    elapsed = 0
    while elapsed < IG_CONTAINER_MAX_WAIT_SECONDS:
        resp = requests.get(
            f"{IG_GRAPH_BASE}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        data = resp.json()
        status_code = data.get("status_code")

        if status_code == "FINISHED":
            return True
        if status_code == "ERROR":
            raise RuntimeError(f"A Meta reportou erro ao processar o vídeo: {data}")

        time.sleep(IG_CONTAINER_POLL_SECONDS)
        elapsed += IG_CONTAINER_POLL_SECONDS

    raise TimeoutError("Tempo esgotado esperando a Meta processar o vídeo (container não ficou FINISHED).")


def publish_container(ig_user_id, container_id, access_token):
    """Publica de fato o container já processado (etapa 2 de 2)."""
    resp = requests.post(
        f"{IG_GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=60,
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise RuntimeError(f"Erro ao publicar: {data}")
    return data["id"]


def publish_reel_now(ig_user_id, video_url, caption, access_token):
    """Orquestra o fluxo completo: cria container -> espera -> publica."""
    container_id = create_media_container(ig_user_id, video_url, caption, access_token)
    wait_for_container_ready(container_id, access_token)
    media_id = publish_container(ig_user_id, container_id, access_token)
    return media_id


def create_scheduled_post(supabase_client, ig_id, ig_username, video_url, caption, scheduled_time_iso):
    return supabase_client.table("scheduled_posts").insert({
        "ig_id": ig_id,
        "ig_username": ig_username,
        "video_url": video_url,
        "caption": caption,
        "scheduled_time": scheduled_time_iso,
        "status": "pending",
    }).execute()


def list_scheduled_posts(supabase_client, status=None):
    query = supabase_client.table("scheduled_posts").select("*").order("scheduled_time")
    if status:
        query = query.eq("status", status)
    return query.execute().data


def update_scheduled_post_status(supabase_client, post_id, status, media_id=None, error_message=None):
    update_data = {"status": status}
    if media_id:
        update_data["published_media_id"] = media_id
    if error_message:
        update_data["error_message"] = error_message
    supabase_client.table("scheduled_posts").update(update_data).eq("id", post_id).execute()


# -----------------------------------------------------------------------------
# CONEXÃO E AUTENTICAÇÃO COM SUPABASE
# -----------------------------------------------------------------------------
@st.cache_resource
def init_supabase():
    missing_keys = []
    if "SUPABASE_URL" not in st.secrets:
        missing_keys.append("SUPABASE_URL")
    if "SUPABASE_KEY" not in st.secrets:
        missing_keys.append("SUPABASE_KEY")

    if missing_keys:
        st.error(f"⚠️ As seguintes chaves estão faltando nos Secrets do Streamlit: {', '.join(missing_keys)}")
        return None

    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        options = ClientOptions(postgrest_client_timeout=30)
        return create_client(url, key, options=options)
    except Exception as e:
        st.error(f"⚠️ Erro ao inicializar o cliente do Supabase: {e}")
        return None


supabase = init_supabase()

# Gerenciamento de sessão do usuário
if "user" not in st.session_state:
    st.session_state["user"] = None

# TELA DE LOGIN / REGISTRO
if st.session_state["user"] is None:
    st.title("🔒 Login - Instagram Reels Downloader")

    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])

    with tab1:
        st.subheader("Acessar sua conta")
        login_email = st.text_input("E-mail", key="login_email")
        login_password = st.text_input("Senha", type="password", key="login_password")

        if st.button("Entrar"):
            if not login_email or not login_password:
                st.warning("Preencha todos os campos.")
            elif supabase:
                try:
                    res = supabase.auth.sign_in_with_password({
                        "email": login_email.strip(),
                        "password": login_password.strip()
                    })
                    if res.user:
                        st.session_state["user"] = res.user
                        st.success("Login realizado com sucesso!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro no login: {e}")

    with tab2:
        st.subheader("Criar nova conta")
        signup_email = st.text_input("E-mail", key="signup_email")
        signup_password = st.text_input("Senha", type="password", key="signup_password")

        if st.button("Cadastrar"):
            if not signup_email or not signup_password:
                st.warning("Preencha todos os campos.")
            elif supabase:
                try:
                    res = supabase.auth.sign_up({
                        "email": signup_email.strip(),
                        "password": signup_password.strip()
                    })
                    if res.user:
                        st.success("Conta criada com sucesso! Faça login para continuar.")
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

    st.stop()

# -----------------------------------------------------------------------------
# PAINEL PRINCIPAL (APÓS LOGIN)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 Logado como: **{st.session_state['user'].email}**")
    if st.button("Sair (Logout)"):
        if supabase:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
        st.session_state["user"] = None
        st.rerun()

st.title("📥 Instagram Reels Downloader")
st.write("Monte seu template, veja a prévia, depois busque os Reels e baixe tudo já pronto em um ZIP.")

# Verifica se o FFmpeg está disponível no ambiente
if shutil.which("ffmpeg") is None:
    st.error(
        "⚠️ O FFmpeg não foi encontrado no ambiente. Adicione um arquivo "
        "`packages.txt` na raiz do repositório com a linha `ffmpeg` "
        "(e reinicie o app) para que a montagem do template funcione."
    )

# -----------------------------------------------------------------------------
# ETAPA 1 — MONTAR E PRÉ-VISUALIZAR O TEMPLATE
# -----------------------------------------------------------------------------
st.header("1️⃣ Monte seu template")

avatar_file = st.file_uploader("Foto de perfil (opcional):", type=["png", "jpg", "jpeg"], key="avatar_uploader")

avatar_data = None
if avatar_file is not None:
    try:
        original_img = Image.open(avatar_file).convert("RGB")
        st.image(original_img, caption="Foto enviada", width=150)

        zoom = st.slider("Zoom da foto:", min_value=1.0, max_value=3.0, value=1.0, step=0.05, key="avatar_zoom")
        pos_x = st.slider("Posição horizontal:", min_value=0, max_value=100, value=50, key="avatar_pos_x")
        pos_y = st.slider("Posição vertical:", min_value=0, max_value=100, value=50, key="avatar_pos_y")

        avatar_data = crop_avatar_region(original_img, zoom, pos_x, pos_y)

        preview_avatar = make_circular_avatar(avatar_data, 150)
        st.image(preview_avatar, caption="Prévia do avatar recortado")
    except Exception as upload_err:
        st.error(f"Não foi possível processar a imagem enviada: {upload_err}")
        avatar_data = None

col1, col2 = st.columns(2)
with col1:
    display_name = st.text_input("Nome a exibir no template:", placeholder="ex: Usuário Aqui", key="tpl_name")
    verified = st.checkbox("Mostrar selo de verificado", value=False, key="tpl_verified")
with col2:
    display_handle = st.text_input("Usuário a exibir (sem @):", placeholder="ex: arrobaaqui", key="tpl_handle")

caption = st.text_input("Texto extra abaixo do @ (opcional):", placeholder="ex: Confira esse vídeo!", key="tpl_caption")

template_name = display_name.strip() if display_name.strip() else "Usuário Aqui"
template_handle = display_handle.strip().replace("@", "") if display_handle.strip() else "arrobaaqui"

bg_path, box_x, box_y, box_w, box_h = build_background_canvas(
    avatar_data,
    template_name,
    template_handle,
    verified,
    caption.strip() if caption else "",
)

st.subheader("Prévia do template")
st.image(bg_path, caption="A área branca abaixo do header é o limite onde o vídeo vai entrar", width=320)

st.markdown("---")

# -----------------------------------------------------------------------------
# ETAPA 2 — BUSCAR VÍDEOS E BAIXAR
# -----------------------------------------------------------------------------
st.header("2️⃣ Buscar vídeos e baixar")

# Carrega o Token do Apify a partir dos Secrets
if "APIFY_TOKEN" not in st.secrets:
    st.error("⚠️ A chave APIFY_TOKEN não foi configurada nos Secrets do Streamlit.")
    st.stop()

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]

with st.form("downloader_form"):
    username = st.text_input("Perfil do Instagram (sem @) — usado para buscar os vídeos:", placeholder="ex: instagram")
    count = st.number_input("Quantidade de vídeos para buscar:", min_value=1, max_value=20, value=3)
    submit_button = st.form_submit_button("Buscar e Baixar Reels (ZIP)")

if submit_button:
    if not username.strip():
        st.warning("Por favor, digite o nome de usuário do Instagram.")
    else:
        clean_username = username.strip().replace("@", "")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        with st.spinner(f"Buscando Reels de @{clean_username}..."):
            try:
                client = apify_client.ApifyClient(APIFY_TOKEN)

                # Posts/Reels do perfil
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
                    st.success(f"Encontrados {len(video_urls)} vídeos! Aplicando o template e compactando...")

                    # Reutiliza o template (bg_path, box_x/y/w/h) já montado na Etapa 1

                    progress_bar = st.progress(0)
                    zip_buffer = io.BytesIO()
                    composed_paths = []

                    with tempfile.TemporaryDirectory() as tmp_dir:
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                            for idx, url in enumerate(video_urls, 1):
                                try:
                                    raw_video_path = os.path.join(tmp_dir, f"raw_{idx}.mp4")
                                    output_video_path = os.path.join(tmp_dir, f"reel_{clean_username}_{idx}.mp4")

                                    video_bytes = download_bytes(url, headers)
                                    with open(raw_video_path, "wb") as f:
                                        f.write(video_bytes)

                                    compose_video_with_template(
                                        raw_video_path, bg_path, box_x, box_y, box_w, box_h, output_video_path
                                    )

                                    zip_file.write(output_video_path, arcname=os.path.basename(output_video_path))
                                    composed_paths.append(output_video_path)

                                except Exception as req_err:
                                    st.warning(f"Não foi possível processar o vídeo {idx}: {req_err}")

                                progress_bar.progress(idx / len(video_urls))

                        zip_buffer.seek(0)

                        st.success("ZIP gerado com sucesso!")

                        st.download_button(
                            label="💾 Baixar todos os vídeos (.ZIP)",
                            data=zip_buffer,
                            file_name=f"reels_{clean_username}.zip",
                            mime="application/zip"
                        )

                        st.write("---")
                        st.subheader("Pré-visualização dos vídeos com template:")
                        for idx, path in enumerate(composed_paths, 1):
                            st.write(f"**Vídeo {idx}**")
                            with open(path, "rb") as vf:
                                st.video(vf.read())

            except Exception as e:
                st.error(f"Erro ao processar a requisição: {e}")

st.markdown("---")

# -----------------------------------------------------------------------------
# ETAPA 3 — AGENDAR / PUBLICAR NO INSTAGRAM (uso pessoal, modo teste)
# -----------------------------------------------------------------------------
st.header("3️⃣ Agendar/Publicar no Instagram (uso pessoal)")

if "IG_ACCESS_TOKEN" not in st.secrets:
    st.info(
        "Para usar essa etapa, adicione `IG_ACCESS_TOKEN` nos Secrets do Streamlit "
        "(gerado no Graph API Explorer do Meta for Developers)."
    )
else:
    IG_ACCESS_TOKEN = st.secrets["IG_ACCESS_TOKEN"]

    # --- Descobrir a conta via Instagram Login ---
    with st.expander("🔍 Descobrir minha Instagram Account ID"):
        if st.button("Buscar minha conta"):
            try:
                account = get_ig_login_account(IG_ACCESS_TOKEN)
                st.success(
                    f"Conta **@{account['username']}** ({account.get('account_type', '')}) "
                    f"→ ID: `{account['user_id']}`"
                )
            except Exception as lookup_err:
                st.error(f"Erro ao buscar a conta: {lookup_err}")

    st.markdown("Cole aqui o ID que você encontrou acima:")
    ig_user_id = st.text_input("Instagram Business Account ID:", key="ig_user_id_input")

    st.subheader("Publicar um vídeo")
    schedule_video_file = st.file_uploader("Vídeo (.mp4) já com o template aplicado:", type=["mp4"], key="ig_video_uploader")
    ig_caption = st.text_area("Legenda do Reels:", key="ig_caption_input")
    schedule_mode = st.radio("Quando publicar?", ["Agora", "Agendar para depois"], key="ig_schedule_mode")

    scheduled_datetime_iso = None
    if schedule_mode == "Agendar para depois":
        col_a, col_b = st.columns(2)
        with col_a:
            schedule_date = st.date_input("Data:", key="ig_schedule_date")
        with col_b:
            schedule_time_input = st.time_input("Hora:", key="ig_schedule_time")
        scheduled_dt = datetime.combine(schedule_date, schedule_time_input)
        scheduled_datetime_iso = scheduled_dt.isoformat()

    if st.button("Confirmar", key="ig_confirm_button"):
        if not ig_user_id.strip():
            st.warning("Preencha a Instagram Business Account ID acima.")
        elif schedule_video_file is None:
            st.warning("Envie o vídeo que deseja publicar.")
        elif not supabase:
            st.error("Conexão com o Supabase não disponível — não dá pra guardar o vídeo.")
        else:
            try:
                with st.spinner("Enviando vídeo para o Storage..."):
                    tmp_video_path = os.path.join(tempfile.gettempdir(), f"ig_upload_{int(time.time())}.mp4")
                    with open(tmp_video_path, "wb") as f:
                        f.write(schedule_video_file.getvalue())

                    dest_filename = f"reel_{int(time.time())}.mp4"
                    public_video_url = upload_video_to_supabase_storage(supabase, tmp_video_path, dest_filename)

                if schedule_mode == "Agora":
                    with st.spinner("Publicando no Instagram (isso pode levar até 1-2 minutos)..."):
                        media_id = publish_reel_now(ig_user_id.strip(), public_video_url, ig_caption, IG_ACCESS_TOKEN)
                    st.success(f"Publicado com sucesso! ID da publicação: `{media_id}`")
                else:
                    create_scheduled_post(supabase, ig_user_id.strip(), None, public_video_url, ig_caption, scheduled_datetime_iso)
                    st.success(f"Agendado para {scheduled_dt.strftime('%d/%m/%Y às %H:%M')}!")

            except Exception as publish_err:
                st.error(f"Erro ao publicar/agendar: {publish_err}")

    st.subheader("📋 Agendamentos pendentes")
    try:
        pending_posts = list_scheduled_posts(supabase, status="pending") if supabase else []
        if not pending_posts:
            st.caption("Nenhum agendamento pendente.")
        else:
            for post in pending_posts:
                st.write(f"🕒 **{post['scheduled_time']}** — {post.get('caption', '')[:60] or '(sem legenda)'}")

            if st.button("🔄 Verificar e publicar agendados que já venceram"):
                now_iso = datetime.now().isoformat()
                published_count = 0
                for post in pending_posts:
                    if post["scheduled_time"] <= now_iso:
                        try:
                            media_id = publish_reel_now(
                                post["ig_id"], post["video_url"], post.get("caption", ""), IG_ACCESS_TOKEN
                            )
                            update_scheduled_post_status(supabase, post["id"], "published", media_id=media_id)
                            published_count += 1
                        except Exception as auto_publish_err:
                            update_scheduled_post_status(supabase, post["id"], "error", error_message=str(auto_publish_err))
                            st.error(f"Erro ao publicar agendamento {post['id']}: {auto_publish_err}")

                if published_count:
                    st.success(f"{published_count} vídeo(s) publicado(s)!")
                    st.rerun()
                else:
                    st.info("Nenhum agendamento estava vencido ainda.")
    except Exception as list_err:
        st.error(f"Erro ao listar agendamentos: {list_err}")
