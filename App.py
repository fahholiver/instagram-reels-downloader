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
HEADER_HEIGHT = 340          # Altura da faixa com avatar + nome + @ + legenda
BOX_TOP_MARGIN = 90          # Espaço entre o header e a caixa do vídeo
BOX_HEIGHT = 1500            # Altura máxima da caixa = o "limite" do vídeo
BOX_BOTTOM_MARGIN = 60       # Espaço em branco abaixo da caixa (antes faltava)
CANVAS_HEIGHT = HEADER_HEIGHT + BOX_TOP_MARGIN + BOX_HEIGHT + BOX_BOTTOM_MARGIN
# Com os valores acima o canvas fica 1080x1920 (proporção 9:16, padrão Reels)

AVATAR_SIZE = 110
AVATAR_MARGIN_LEFT = 40
AVATAR_MARGIN_TOP = 180       # header mais para baixo (era 55)

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

    # --- Avatar ---
    avatar_pasted = False
    if avatar_bytes:
        try:
            avatar = make_circular_avatar(avatar_bytes, AVATAR_SIZE)
            canvas.paste(avatar, (AVATAR_MARGIN_LEFT, AVATAR_MARGIN_TOP), avatar)
            avatar_pasted = True
        except Exception as avatar_err:
            avatar_pasted = False
            st.warning(f"Não foi possível usar a foto de perfil no template: {avatar_err}")

    if not avatar_pasted:
        draw.ellipse(
            (
                AVATAR_MARGIN_LEFT,
                AVATAR_MARGIN_TOP,
                AVATAR_MARGIN_LEFT + AVATAR_SIZE,
                AVATAR_MARGIN_TOP + AVATAR_SIZE,
            ),
            fill=(210, 210, 210),
        )

    # --- Nome + selo verificado ---
    text_x = AVATAR_MARGIN_LEFT + AVATAR_SIZE + 30
    name_font = load_font(FONT_BOLD_PATH, 46)
    handle_font = load_font(FONT_REGULAR_PATH, 36)

    name_y = AVATAR_MARGIN_TOP + 2
    display_name = full_name or username
    draw.text((text_x, name_y), display_name, font=name_font, fill=TEXT_COLOR)

    if verified:
        name_w = draw.textlength(display_name, font=name_font)
        draw_verified_badge(draw, text_x + name_w + 14, name_y + 6, size=36)

    handle_y = name_y + 58
    draw.text((text_x, handle_y), f"@{username}", font=handle_font, fill=HANDLE_COLOR)

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
