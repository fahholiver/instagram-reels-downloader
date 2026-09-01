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
import random
from datetime import datetime, timezone, timedelta
from supabase import create_client, ClientOptions
from PIL import Image, ImageDraw, ImageFont, ImageOps
from ig_publisher import (
    IG_GRAPH_BASE,
    get_ig_login_account,
    get_ig_account_stats,
    get_ig_recent_media,
    create_media_container,
    wait_for_container_ready,
    publish_container,
    publish_reel_now,
)
from translations import t

# Configuração da página
st.set_page_config(
    page_title="Instagram Reels Downloader",
    page_icon="📥",
    layout="centered"
)

# -----------------------------------------------------------------------------
# SELETOR DE IDIOMA (fica visível em qualquer tela, inclusive antes do login)
# -----------------------------------------------------------------------------
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"  # padrão inglês (uso no Reino Unido)

with st.sidebar:
    lang_choice = st.selectbox(
        "🌐 Language / Idioma",
        ["English", "Português (Brasil)"],
        index=0 if st.session_state["lang"] == "en" else 1,
        key="lang_selector",
    )
    st.session_state["lang"] = "en" if lang_choice == "English" else "pt"

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
# CONFIGURAÇÃO DA PUBLICAÇÃO NO INSTAGRAM
# -----------------------------------------------------------------------------
# IG_GRAPH_BASE, timings de container etc. vêm do módulo ig_publisher.py
IG_STORAGE_BUCKET = "reels-videos"  # bucket público no Supabase Storage (criar manualmente)


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
            st.warning(t("avatar_use_error", error=avatar_err))

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
def upload_video_bytes_to_storage(supabase_client, file_bytes, dest_filename, bucket=IG_STORAGE_BUCKET):
    """
    Sobe o vídeo (em bytes) para um bucket público do Supabase Storage e
    retorna a URL pública -- a Meta precisa conseguir baixar o vídeo por essa URL.
    """
    supabase_client.storage.from_(bucket).upload(
        dest_filename,
        file_bytes,
        {"content-type": "video/mp4", "upsert": "true"},
    )
    public_url = supabase_client.storage.from_(bucket).get_public_url(dest_filename)
    return public_url


def save_ig_account(supabase_client, user_id, account_info, access_token):
    """
    Salva (ou atualiza, se já existir) uma conta do Instagram vinculada ao
    usuário logado no app -- é isso que garante que cada login só vê as
    próprias contas conectadas.
    """
    return supabase_client.table("ig_accounts").upsert({
        "user_id": user_id,
        "ig_user_id": account_info["user_id"],
        "username": account_info.get("username"),
        "account_type": account_info.get("account_type"),
        "access_token": access_token,
    }, on_conflict="user_id,ig_user_id").execute()


def list_ig_accounts(supabase_client, user_id):
    return (
        supabase_client.table("ig_accounts")
        .select("*")
        .eq("user_id", user_id)
        .order("username")
        .execute()
        .data
    )


def format_compact_number(n):
    """1234 -> '1.2K', 1500000 -> '1.5M'. Deixa números grandes legíveis no card."""
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


@st.cache_data(ttl=300, show_spinner=False)
def get_cached_account_stats(access_token):
    """
    Cacheia por 5 minutos -- evita bater na API do Instagram toda vez que a
    página recarrega (o que ela faz a cada clique em qualquer botão do app).
    """
    return get_ig_account_stats(access_token)


@st.cache_data(ttl=300, show_spinner=False)
def get_cached_recent_media(access_token, limit=6):
    """Mesma lógica de cache, mas pro feed recente (miniaturas dos posts)."""
    return get_ig_recent_media(access_token, limit=limit)


def create_scheduled_post(supabase_client, user_id, ig_id, access_token, video_url, caption, scheduled_time_iso, storage_path=None):
    return supabase_client.table("scheduled_posts").insert({
        "user_id": user_id,
        "ig_id": ig_id,
        "access_token": access_token,
        "video_url": video_url,
        "storage_path": storage_path,
        "caption": caption,
        "scheduled_time": scheduled_time_iso,
        "status": "pending",
    }).execute()


def list_scheduled_posts(supabase_client, user_id, status=None):
    query = supabase_client.table("scheduled_posts").select("*").eq("user_id", user_id).order("scheduled_time")
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


def aplicar_jitter(dt, minutos=10):
    """
    Aplica uma variação aleatória de +/- 'minutos' ao horário desejado, pra
    não publicar sempre no segundo exato (evita parecer bot). O horário que
    o usuário digitou vira só uma referência, não um compromisso exato.
    """
    offset_segundos = random.randint(-minutos * 60, minutos * 60)
    return dt + timedelta(seconds=offset_segundos)


def gerar_horarios_em_massa(data_inicio, dias_semana_selecionados, horarios_por_dia, quantidade_videos, jitter_minutos=10):
    """
    Gera uma lista de datetimes para distribuir 'quantidade_videos' vídeos,
    publicando 'len(horarios_por_dia)' vídeos por dia, só nos dias da semana
    selecionados (0=Segunda ... 6=Domingo), a partir de 'data_inicio'.
    Cada horário já sai com uma variação aleatória aplicada (jitter).
    """
    resultado = []
    dia_atual = data_inicio
    dias_verificados = 0
    limite_seguranca = 3650  # ~10 anos, evita loop infinito se nada for selecionado

    while len(resultado) < quantidade_videos and dias_verificados < limite_seguranca:
        if dia_atual.weekday() in dias_semana_selecionados:
            for horario in horarios_por_dia:
                if len(resultado) >= quantidade_videos:
                    break
                horario_base = datetime.combine(dia_atual, horario)
                resultado.append(aplicar_jitter(horario_base, jitter_minutos))
        dia_atual += timedelta(days=1)
        dias_verificados += 1

    return resultado


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
        st.error(t("missing_secrets_error", keys=', '.join(missing_keys)))
        return None

    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        options = ClientOptions(postgrest_client_timeout=30)
        return create_client(url, key, options=options)
    except Exception as e:
        st.error(t("supabase_init_error", error=e))
        return None


supabase = init_supabase()

# Gerenciamento de sessão do usuário
if "user" not in st.session_state:
    st.session_state["user"] = None

# TELA DE LOGIN / REGISTRO
if st.session_state["user"] is None:
    st.title(t("login_page_title"))

    tab1, tab2 = st.tabs([t("tab_login"), t("tab_signup")])

    with tab1:
        st.subheader(t("login_subheader"))
        login_email = st.text_input(t("email_label"), key="login_email")
        login_password = st.text_input(t("password_label"), type="password", key="login_password")

        if st.button(t("login_button")):
            if not login_email or not login_password:
                st.warning(t("fill_all_fields"))
            elif supabase:
                try:
                    res = supabase.auth.sign_in_with_password({
                        "email": login_email.strip(),
                        "password": login_password.strip()
                    })
                    if res.user:
                        st.session_state["user"] = res.user
                        st.success(t("login_success"))
                        st.rerun()
                except Exception as e:
                    st.error(t("login_error", error=e))

    with tab2:
        st.subheader(t("signup_subheader"))
        signup_email = st.text_input(t("email_label"), key="signup_email")
        signup_password = st.text_input(t("password_label"), type="password", key="signup_password")

        if st.button(t("signup_button")):
            if not signup_email or not signup_password:
                st.warning(t("fill_all_fields"))
            elif supabase:
                try:
                    res = supabase.auth.sign_up({
                        "email": signup_email.strip(),
                        "password": signup_password.strip()
                    })
                    if res.user:
                        st.success(t("signup_success"))
                except Exception as e:
                    st.error(t("signup_error", error=e))

    st.stop()

# -----------------------------------------------------------------------------
# PAINEL PRINCIPAL (APÓS LOGIN)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.write(t("logged_in_as", email=st.session_state['user'].email))
    if st.button(t("logout_button")):
        if supabase:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
        st.session_state["user"] = None
        st.rerun()

st.title(t("app_title"))
st.write(t("app_subtitle"))

# Verifica se o FFmpeg está disponível no ambiente
if shutil.which("ffmpeg") is None:
    st.error(t("ffmpeg_missing"))

# -----------------------------------------------------------------------------
# ETAPA 1 — MONTAR E PRÉ-VISUALIZAR O TEMPLATE
# -----------------------------------------------------------------------------
st.header(t("step1_header"))

avatar_file = st.file_uploader(t("avatar_uploader_label"), type=["png", "jpg", "jpeg"], key="avatar_uploader")

avatar_data = None
if avatar_file is not None:
    try:
        original_img = Image.open(avatar_file).convert("RGB")
        st.image(original_img, caption=t("uploaded_photo_caption"), width=150)

        zoom = st.slider(t("zoom_slider_label"), min_value=1.0, max_value=3.0, value=1.0, step=0.05, key="avatar_zoom")
        pos_x = st.slider(t("pos_x_slider_label"), min_value=0, max_value=100, value=50, key="avatar_pos_x")
        pos_y = st.slider(t("pos_y_slider_label"), min_value=0, max_value=100, value=50, key="avatar_pos_y")

        avatar_data = crop_avatar_region(original_img, zoom, pos_x, pos_y)

        preview_avatar = make_circular_avatar(avatar_data, 150)
        st.image(preview_avatar, caption=t("avatar_preview_caption"))
    except Exception as upload_err:
        st.error(t("avatar_process_error", error=upload_err))
        avatar_data = None

col1, col2 = st.columns(2)
with col1:
    display_name = st.text_input(t("display_name_label"), placeholder=t("display_name_placeholder"), key="tpl_name")
    verified = st.checkbox(t("verified_checkbox_label"), value=False, key="tpl_verified")
with col2:
    display_handle = st.text_input(t("display_handle_label"), placeholder=t("display_handle_placeholder"), key="tpl_handle")

caption = st.text_input(t("caption_input_label"), placeholder=t("caption_input_placeholder"), key="tpl_caption")

template_name = display_name.strip() if display_name.strip() else t("default_display_name")
template_handle = display_handle.strip().replace("@", "") if display_handle.strip() else t("default_display_handle")

bg_path, box_x, box_y, box_w, box_h = build_background_canvas(
    avatar_data,
    template_name,
    template_handle,
    verified,
    caption.strip() if caption else "",
)

st.subheader(t("template_preview_subheader"))
st.image(bg_path, caption=t("template_preview_caption"), width=320)

st.markdown("---")

# -----------------------------------------------------------------------------
# ETAPA 2 — BUSCAR VÍDEOS E BAIXAR
# -----------------------------------------------------------------------------
st.header(t("step2_header"))

# Carrega o Token do Apify a partir dos Secrets
if "APIFY_TOKEN" not in st.secrets:
    st.error(t("apify_token_missing"))
    st.stop()

APIFY_TOKEN = st.secrets["APIFY_TOKEN"]

with st.form("downloader_form"):
    username = st.text_input(t("username_field_label"), placeholder=t("username_field_placeholder"))
    count = st.number_input(t("count_field_label"), min_value=1, max_value=20, value=3)
    ordenar_por = st.radio(
        t("order_by_label"),
        [t("order_by_recent"), t("order_by_viral")],
        key="ordenar_por_input",
    )
    submit_button = st.form_submit_button(t("fetch_button"))

if submit_button:
    if not username.strip():
        st.warning(t("enter_username_warning"))
    else:
        clean_username = username.strip().replace("@", "")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        with st.spinner(t("fetching_spinner", username=clean_username)):
            try:
                client = apify_client.ApifyClient(APIFY_TOKEN)

                buscar_virais = ordenar_por == t("order_by_viral")
                # Pra achar os "mais virais" precisamos olhar mais posts do que o pedido
                # e escolher os melhores depois -- senão só teria os N mais recentes pra escolher.
                pool_size = min(int(count) * 5, 100) if buscar_virais else int(count)

                # Posts/Reels do perfil
                run_input = {
                    "directUrls": [f"https://www.instagram.com/{clean_username}/"],
                    "resultsType": "posts",
                    "resultsLimit": pool_size,
                }
                run = client.actor("apify/instagram-scraper").call(run_input=run_input)
                dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
                dataset_items = client.dataset(dataset_id).list_items().items

                video_items = []
                for item in dataset_items:
                    is_video = (item.get("isVideo") and item.get("videoUrl")) or (
                        item.get("type") == "Video" and item.get("videoUrl")
                    )
                    if is_video:
                        video_items.append(item)

                if buscar_virais:
                    def score_engajamento(item):
                        views = item.get("videoViewCount") or item.get("videoPlayCount") or 0
                        likes = item.get("likesCount") or 0
                        comments = item.get("commentsCount") or 0
                        return views + likes + comments

                    video_items.sort(key=score_engajamento, reverse=True)

                video_items = video_items[:int(count)]
                video_urls = [item.get("videoUrl") for item in video_items]

                if not video_urls:
                    st.error(t("no_videos_found_error"))
                else:
                    st.success(t("videos_found_success", count=len(video_urls)))

                    # Reutiliza o template (bg_path, box_x/y/w/h) já montado na Etapa 1

                    progress_bar = st.progress(0)
                    zip_buffer = io.BytesIO()
                    composed_paths = []
                    generated_videos_batch = []  # guardado em session_state pro agendamento em massa

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

                                    with open(output_video_path, "rb") as composed_f:
                                        generated_videos_batch.append({
                                            "filename": os.path.basename(output_video_path),
                                            "bytes": composed_f.read(),
                                        })

                                except Exception as req_err:
                                    st.warning(t("video_process_warning", index=idx, error=req_err))

                                progress_bar.progress(idx / len(video_urls))

                        zip_buffer.seek(0)

                        st.session_state["generated_videos"] = generated_videos_batch

                        st.success(t("zip_success", count=len(generated_videos_batch)))

                        st.download_button(
                            label=t("download_zip_button"),
                            data=zip_buffer,
                            file_name=f"reels_{clean_username}.zip",
                            mime="application/zip"
                        )

                        st.write("---")
                        st.subheader(t("video_preview_subheader"))
                        for idx, path in enumerate(composed_paths, 1):
                            st.write(t("video_label", index=idx))
                            with open(path, "rb") as vf:
                                st.video(vf.read())

            except Exception as e:
                st.error(t("request_error", error=e))

st.markdown("---")

# -----------------------------------------------------------------------------
# ETAPA 3 — AGENDAR / PUBLICAR NO INSTAGRAM (uso pessoal, modo teste)
# -----------------------------------------------------------------------------
st.header(t("step3_header"))

IG_SCHEDULING_ENABLED = st.secrets.get("IG_SCHEDULING_ENABLED", False)

if not IG_SCHEDULING_ENABLED:
    st.warning(t("scheduling_disabled_warning"))
    st.stop()

current_user_id = st.session_state["user"].id

# --- Conectar uma conta do Instagram a ESTE login ---
with st.expander(t("connect_account_expander")):
    st.caption(t("connect_account_caption"))
    novo_token = st.text_input(t("token_input_label"), type="password", key="novo_ig_token")
    if st.button(t("connect_account_button"), key="conectar_ig_button"):
        if not novo_token.strip():
            st.warning(t("paste_token_warning"))
        else:
            try:
                account_info = get_ig_login_account(novo_token.strip())
                save_ig_account(supabase, current_user_id, account_info, novo_token.strip())
                st.success(t("account_connected_success", username=account_info['username']))
                st.rerun()
            except Exception as connect_err:
                st.error(t("connect_error", error=connect_err))

# --- Dropdown com as contas JÁ conectadas por esse usuário ---
minhas_contas = list_ig_accounts(supabase, current_user_id) if supabase else []

if not minhas_contas:
    st.info(t("no_accounts_info"))
    st.stop()

tab_dashboard, tab_manage = st.tabs([t("dashboard_tab_label"), t("manage_tab_label")])

with tab_dashboard:
    # --- Dashboard: um card por conta conectada, com dados reais ---
    st.subheader(t("dashboard_subheader"))

    all_pending_posts = list_scheduled_posts(supabase, current_user_id, status="pending") if supabase else []

    dashboard_cols = st.columns(2)
    for idx, acc in enumerate(minhas_contas):
        with dashboard_cols[idx % 2]:
            try:
                stats = get_cached_account_stats(acc["access_token"])
            except Exception as stats_err:
                stats = None
                st.error(t("dashboard_stats_error", error=stats_err))

            if stats:
                username = stats.get('username', acc['username'])
                account_type = stats.get("account_type", "")
                biography = (stats.get("biography") or "").strip()
                followers = format_compact_number(stats.get("followers_count"))
                posts = format_compact_number(stats.get("media_count"))
                pic_url = stats.get("profile_picture_url", "")
                pending_for_this_account = len([p for p in all_pending_posts if p.get("ig_id") == acc["ig_user_id"]])

                avatar_html = (
                    f'<img src="{pic_url}" style="width:44px;height:44px;border-radius:50%;'
                    f'object-fit:cover;flex-shrink:0;">'
                    if pic_url else
                    '<div style="width:44px;height:44px;border-radius:50%;background:#e0e0e0;flex-shrink:0;"></div>'
                )

                bio_html = (
                    f'<div style="color:#555;font-size:0.78rem;margin-top:8px;line-height:1.3;">{biography[:90]}</div>'
                    if biography else ""
                )

                limited_html = (
                    f'<div style="color:#aaa;font-size:0.68rem;margin-top:6px;">{t("dashboard_limited_stats")}</div>'
                    if stats.get("_stats_limited") else ""
                )

                # --- Miniaturas do feed recente ---
                try:
                    recent_media = get_cached_recent_media(acc["access_token"], limit=6)
                except Exception:
                    recent_media = []

                feed_html = ""
                if recent_media:
                    thumbs_html = "".join(
                        f'<a href="{m["permalink"]}" target="_blank">'
                        f'<img src="{m["thumbnail"]}" style="width:100%;aspect-ratio:1;object-fit:cover;'
                        f'border-radius:6px;">'
                        f'</a>'
                        for m in recent_media
                    )
                    feed_html = f"""
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:10px;">
                        {thumbs_html}
                    </div>
                    """

                # --- Moldura de iPhone (só visual, via CSS) envolvendo o card inteiro ---
                phone_html = f"""
                <div style="
                    background:#000;
                    border-radius:34px;
                    padding:10px;
                    box-shadow:0 6px 18px rgba(0,0,0,0.25);
                    margin-bottom:16px;
                    max-width:280px;
                ">
                    <div style="
                        background:#fff;
                        border-radius:24px;
                        padding:22px 14px 16px 14px;
                        position:relative;
                        overflow:hidden;
                    ">
                        <div style="
                            position:absolute; top:0; left:50%; transform:translateX(-50%);
                            width:80px; height:16px; background:#000;
                            border-bottom-left-radius:12px; border-bottom-right-radius:12px;
                        "></div>
                        <div style="display:flex;align-items:center;gap:10px;">
                            {avatar_html}
                            <div style="line-height:1.2;min-width:0;">
                                <div style="font-weight:700;font-size:0.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">@{username}</div>
                                <div style="color:#888;font-size:0.72rem;">{account_type}</div>
                            </div>
                        </div>
                        {bio_html}
                        <div style="display:flex;gap:20px;margin-top:12px;">
                            <div>
                                <div style="color:#888;font-size:0.68rem;">{t("dashboard_followers")}</div>
                                <div style="font-size:1.2rem;font-weight:700;">{followers}</div>
                            </div>
                            <div>
                                <div style="color:#888;font-size:0.68rem;">{t("dashboard_posts")}</div>
                                <div style="font-size:1.2rem;font-weight:700;">{posts}</div>
                            </div>
                        </div>
                        <div style="margin-top:8px;color:#888;font-size:0.72rem;">
                            🕒 {t("dashboard_pending_count", count=pending_for_this_account)}
                        </div>
                        {limited_html}
                        {feed_html}
                        <div style="
                            width:100px; height:4px; background:#000; opacity:0.25;
                            border-radius:2px; margin:16px auto 0 auto;
                        "></div>
                    </div>
                </div>
                """
                st.markdown(phone_html, unsafe_allow_html=True)


with tab_manage:
    opcoes_contas = {f"@{acc['username']}": acc for acc in minhas_contas}
    conta_selecionada_label = st.selectbox(t("select_account_label"), options=list(opcoes_contas.keys()), key="conta_ig_selecionada")
    conta_selecionada = opcoes_contas[conta_selecionada_label]
    ig_user_id = conta_selecionada["ig_user_id"]
    IG_ACCESS_TOKEN = conta_selecionada["access_token"]

    st.subheader(t("publish_video_subheader"))
    schedule_video_file = st.file_uploader(t("video_uploader_label"), type=["mp4"], key="ig_video_uploader")
    ig_caption = st.text_area(t("reel_caption_label"), key="ig_caption_input")
    schedule_mode = st.radio(t("when_to_publish_label"), [t("publish_now_option"), t("schedule_later_option")], key="ig_schedule_mode")

    scheduled_datetime_iso = None
    if schedule_mode == t("schedule_later_option"):
        col_a, col_b = st.columns(2)
        with col_a:
            schedule_date = st.date_input(t("date_label"), key="ig_schedule_date")
        with col_b:
            schedule_time_input = st.time_input(t("time_label"), key="ig_schedule_time")
        scheduled_dt = aplicar_jitter(datetime.combine(schedule_date, schedule_time_input))
        scheduled_datetime_iso = scheduled_dt.isoformat()
        st.caption(t("jitter_caption"))

    if st.button(t("confirm_button"), key="ig_confirm_button"):
        if schedule_video_file is None:
            st.warning(t("upload_video_warning"))
        elif not supabase:
            st.error(t("supabase_unavailable_error"))
        else:
            try:
                with st.spinner(t("uploading_spinner")):
                    dest_filename = f"reel_{int(time.time())}.mp4"
                    public_video_url = upload_video_bytes_to_storage(
                        supabase, schedule_video_file.getvalue(), dest_filename
                    )

                if schedule_mode == t("publish_now_option"):
                    with st.spinner(t("publishing_spinner")):
                        media_id = publish_reel_now(ig_user_id, public_video_url, ig_caption, IG_ACCESS_TOKEN)
                    try:
                        supabase.storage.from_(IG_STORAGE_BUCKET).remove([dest_filename])
                    except Exception:
                        pass  # publicação já deu certo, falha ao limpar não é crítica
                    st.success(t("published_success", media_id=media_id))
                else:
                    create_scheduled_post(
                        supabase, current_user_id, ig_user_id, IG_ACCESS_TOKEN, public_video_url, ig_caption,
                        scheduled_datetime_iso, storage_path=dest_filename,
                    )
                    st.success(t("scheduled_success", datetime=scheduled_dt.strftime('%d/%m/%Y %H:%M')))

            except Exception as publish_err:
                st.error(t("publish_schedule_error", error=publish_err))

    st.markdown("---")
    st.subheader(t("bulk_subheader"))
    st.caption(t("bulk_caption_intro"))

    # --- Fonte dos vídeos ---
    videos_gerados_sessao = st.session_state.get("generated_videos", [])
    usar_gerados = False
    if videos_gerados_sessao:
        usar_gerados = st.checkbox(
            t("use_generated_checkbox", count=len(videos_gerados_sessao)),
            value=True,
            key="bulk_usar_gerados",
        )
    else:
        st.caption(t("no_generated_videos_caption"))

    bulk_uploaded_files = st.file_uploader(
        t("bulk_uploader_label"),
        type=["mp4"],
        accept_multiple_files=True,
        key="bulk_video_uploader",
    )

    videos_para_agendar = []
    if usar_gerados:
        videos_para_agendar.extend(videos_gerados_sessao)
    if bulk_uploaded_files:
        for f in bulk_uploaded_files:
            videos_para_agendar.append({"filename": f.name, "bytes": f.getvalue()})

    st.info(t("total_videos_ready_info", count=len(videos_para_agendar)))

    bulk_caption = st.text_area(t("bulk_caption_label"), key="bulk_caption_input")

    col1, col2 = st.columns(2)
    with col1:
        videos_por_dia = st.number_input(t("videos_per_day_label"), min_value=1, max_value=10, value=1, key="bulk_videos_por_dia")
    with col2:
        data_inicio = st.date_input(t("start_date_label"), key="bulk_data_inicio")

    st.markdown(t("time_per_video_markdown"))
    horarios_selecionados = []
    horario_cols = st.columns(min(int(videos_por_dia), 5) or 1)
    for i in range(int(videos_por_dia)):
        with horario_cols[i % len(horario_cols)]:
            horario = st.time_input(t("video_slot_label", index=i + 1), key=f"bulk_horario_{i}")
            horarios_selecionados.append(horario)

    dias_semana_opcoes = {
        t("weekday_monday"): 0, t("weekday_tuesday"): 1, t("weekday_wednesday"): 2, t("weekday_thursday"): 3,
        t("weekday_friday"): 4, t("weekday_saturday"): 5, t("weekday_sunday"): 6,
    }
    dias_semana_labels = st.multiselect(
        t("weekdays_label"),
        options=list(dias_semana_opcoes.keys()),
        default=[t("weekday_monday"), t("weekday_tuesday"), t("weekday_wednesday"), t("weekday_thursday"), t("weekday_friday")],
        key="bulk_dias_semana",
    )
    dias_semana_numeros = {dias_semana_opcoes[d] for d in dias_semana_labels}

    if st.button(t("generate_bulk_button"), key="bulk_gerar_button"):
        if not videos_para_agendar:
            st.warning(t("no_videos_available_warning"))
        elif not dias_semana_numeros:
            st.warning(t("select_weekday_warning"))
        elif not supabase:
            st.error(t("supabase_unavailable_error_plain"))
        else:
            try:
                horarios_datas = gerar_horarios_em_massa(
                    data_inicio, dias_semana_numeros, horarios_selecionados, len(videos_para_agendar)
                )

                bulk_progress = st.progress(0)
                criados = 0
                for idx, (video, quando) in enumerate(zip(videos_para_agendar, horarios_datas), 1):
                    try:
                        dest_filename = f"reel_bulk_{int(time.time())}_{idx}.mp4"
                        public_url = upload_video_bytes_to_storage(supabase, video["bytes"], dest_filename)
                        create_scheduled_post(
                            supabase, current_user_id, ig_user_id, IG_ACCESS_TOKEN, public_url, bulk_caption,
                            quando.isoformat(), storage_path=dest_filename,
                        )
                        criados += 1
                    except Exception as bulk_item_err:
                        st.warning(t("bulk_item_error", index=idx, filename=video.get('filename', ''), error=bulk_item_err))
                    bulk_progress.progress(idx / len(videos_para_agendar))

                st.success(t(
                    "bulk_success",
                    count=criados,
                    first=horarios_datas[0].strftime('%d/%m/%Y %H:%M'),
                    last=horarios_datas[-1].strftime('%d/%m/%Y %H:%M'),
                ))
                st.rerun()
            except Exception as bulk_err:
                st.error(t("bulk_error", error=bulk_err))

    st.subheader(t("pending_subheader"))
    try:
        pending_posts = list_scheduled_posts(supabase, current_user_id, status="pending") if supabase else []
        if not pending_posts:
            st.caption(t("no_pending_caption"))
        else:
            for post in pending_posts:
                st.write(t("pending_item_label", time=post['scheduled_time'], caption=post.get('caption', '')[:60] or t("no_caption_placeholder")))

            if st.button(t("check_pending_button")):
                now_iso = datetime.now().isoformat()
                published_count = 0
                for post in pending_posts:
                    if post["scheduled_time"] <= now_iso:
                        try:
                            media_id = publish_reel_now(
                                post["ig_id"], post["video_url"], post.get("caption", ""), post["access_token"]
                            )
                            update_scheduled_post_status(supabase, post["id"], "published", media_id=media_id)
                            if post.get("storage_path"):
                                try:
                                    supabase.storage.from_(IG_STORAGE_BUCKET).remove([post["storage_path"]])
                                except Exception:
                                    pass  # publicação já deu certo, falha ao limpar não é crítica
                            published_count += 1
                        except Exception as auto_publish_err:
                            update_scheduled_post_status(supabase, post["id"], "error", error_message=str(auto_publish_err))
                            st.error(t("auto_publish_error", id=post['id'], error=auto_publish_err))

                if published_count:
                    st.success(t("published_count_success", count=published_count))
                    st.rerun()
                else:
                    st.info(t("no_due_schedules_info"))
    except Exception as list_err:
        st.error(t("list_schedules_error", error=list_err))
