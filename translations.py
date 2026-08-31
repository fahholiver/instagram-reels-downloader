"""
Translation strings for the app UI. English (UK-friendly) is the default;
Portuguese (Brazil) is offered as an alternative via the language switcher.

Usage in app.py:
    from translations import t
    st.button(t("login_button"))
    st.warning(t("fill_all_fields"))
    st.success(t("account_connected", username=account_info["username"]))
"""

TRANSLATIONS = {
    "en": {
        "avatar_use_error": "Couldn't use the profile photo in the template: {error}",
        "missing_secrets_error": "⚠️ The following keys are missing from Streamlit Secrets: {keys}",
        "supabase_init_error": "⚠️ Error initialising the Supabase client: {error}",

        # --- Login / Sign up ---
        "login_page_title": "🔒 Login - Instagram Reels Downloader",
        "tab_login": "Log In",
        "tab_signup": "Create Account",
        "login_subheader": "Access your account",
        "email_label": "Email",
        "password_label": "Password",
        "login_button": "Log In",
        "fill_all_fields": "Please fill in all fields.",
        "login_success": "Logged in successfully!",
        "login_error": "Login error: {error}",
        "signup_subheader": "Create a new account",
        "signup_button": "Sign Up",
        "signup_success": "Account created successfully! Log in to continue.",
        "signup_error": "Error signing up: {error}",

        # --- Sidebar ---
        "logged_in_as": "👤 Logged in as: **{email}**",
        "logout_button": "Log Out",

        # --- Main title ---
        "app_title": "📥 Instagram Reels Downloader",
        "app_subtitle": "Build your template, preview it, then fetch the Reels and download everything ready in a ZIP.",
        "ffmpeg_missing": (
            "⚠️ FFmpeg wasn't found in this environment. Add a `packages.txt` file "
            "to the repository root with the line `ffmpeg` (and restart the app) "
            "so the template can be built."
        ),

        # --- Step 1: Template ---
        "step1_header": "1️⃣ Build your template",
        "avatar_uploader_label": "Profile photo (optional):",
        "uploaded_photo_caption": "Uploaded photo",
        "zoom_slider_label": "Photo zoom:",
        "pos_x_slider_label": "Horizontal position:",
        "pos_y_slider_label": "Vertical position:",
        "avatar_preview_caption": "Cropped avatar preview",
        "avatar_process_error": "Couldn't process the uploaded image: {error}",
        "display_name_label": "Name to display in the template:",
        "display_name_placeholder": "e.g. User Here",
        "verified_checkbox_label": "Show verified badge",
        "display_handle_label": "Username to display (without @):",
        "display_handle_placeholder": "e.g. handlehere",
        "caption_input_label": "Extra text below the @ (optional):",
        "caption_input_placeholder": "e.g. Check this video out!",
        "default_display_name": "User Here",
        "default_display_handle": "handlehere",
        "template_preview_subheader": "Template preview",
        "template_preview_caption": "The white area below the header is the boundary where the video will go",

        # --- Step 2: Fetch & Download ---
        "step2_header": "2️⃣ Fetch videos and download",
        "apify_token_missing": "⚠️ The APIFY_TOKEN key hasn't been configured in Streamlit Secrets.",
        "username_field_label": "Instagram profile (without @) — used to fetch the videos:",
        "username_field_placeholder": "e.g. instagram",
        "count_field_label": "Number of videos to fetch:",
        "order_by_label": "Which videos to fetch?",
        "order_by_recent": "Most recent",
        "order_by_viral": "Most viral (views + likes + comments)",
        "fetch_button": "Fetch and Download Reels (ZIP)",
        "enter_username_warning": "Please enter the Instagram username.",
        "fetching_spinner": "Fetching Reels from @{username}...",
        "no_videos_found_error": "No public video/Reel found for this profile.",
        "videos_found_success": "Found {count} videos! Applying the template and zipping...",
        "video_process_warning": "Couldn't process video {index}: {error}",
        "zip_success": (
            "ZIP created successfully! These {count} videos are also already available "
            "in Step 3 to schedule directly, without needing to download and re-upload."
        ),
        "download_zip_button": "💾 Download all videos (.ZIP)",
        "video_preview_subheader": "Preview of videos with template:",
        "video_label": "**Video {index}**",
        "request_error": "Error processing the request: {error}",

        # --- Step 3: Instagram scheduling ---
        "step3_header": "3️⃣ Schedule/Publish to Instagram (personal use)",
        "scheduling_disabled_warning": (
            "🔒 Automatic publishing/scheduling is **disabled for now** (to avoid the "
            "risk of an account block while this is tested carefully). All the code "
            "is still here, it just doesn't run. To re-enable when you want to test "
            "again: add the secret `IG_SCHEDULING_ENABLED = \"true\"` in the Streamlit "
            "settings, and don't forget to re-enable the GitHub Actions workflow too."
        ),
        "connect_account_expander": "➕ Connect an Instagram account",
        "connect_account_caption": (
            "Paste a token generated in the Graph API Explorer (Meta for Developers) "
            "for this account. It's saved only for your login -- other users of the "
            "app can't see or use this account."
        ),
        "token_input_label": "Access token (IGAA...):",
        "connect_account_button": "Connect account",
        "paste_token_warning": "Paste the token before connecting.",
        "account_connected_success": "Account @{username} connected!",
        "connect_error": "Error connecting: {error}",
        "no_accounts_info": "No account connected yet. Use \"➕ Connect an Instagram account\" above to get started.",
        "dashboard_subheader": "📊 Connected accounts dashboard",
        "dashboard_tab_label": "📊 Dashboard",
        "manage_tab_label": "🔗 Manage & Publish",
        "dashboard_followers": "Followers",
        "dashboard_posts": "Posts",
        "dashboard_limited_stats": "Some stats aren't available for this token's permissions.",
        "dashboard_pending_count": "{count} scheduled post(s) pending",
        "dashboard_stats_error": "Couldn't load stats: {error}",
        "select_account_label": "Instagram account to post to:",
        "publish_video_subheader": "Publish a video",
        "video_uploader_label": "Video (.mp4) with the template already applied:",
        "reel_caption_label": "Reel caption:",
        "when_to_publish_label": "When to publish?",
        "publish_now_option": "Now",
        "schedule_later_option": "Schedule for later",
        "date_label": "Date:",
        "time_label": "Time:",
        "jitter_caption": "The actual publish time varies by up to 10 minutes either way (to avoid looking like a bot).",
        "confirm_button": "Confirm",
        "upload_video_warning": "Upload the video you want to publish.",
        "supabase_unavailable_error": "Supabase connection not available — can't save the video.",
        "uploading_spinner": "Uploading video to Storage...",
        "publishing_spinner": "Publishing to Instagram (this can take up to 1-2 minutes)...",
        "published_success": "Published successfully! Post ID: `{media_id}`",
        "scheduled_success": "Scheduled for around {datetime}!",
        "publish_schedule_error": "Error publishing/scheduling: {error}",

        "bulk_subheader": "📦 Bulk scheduling",
        "bulk_caption_intro": (
            "Set how many videos per day, at which times and weekdays, and starting "
            "from when — the app distributes the videos automatically into those slots."
        ),
        "use_generated_checkbox": "Use the {count} videos generated in Step 2 (this session)",
        "no_generated_videos_caption": "No videos generated in this session yet (generate them in Step 2 to see them here).",
        "bulk_uploader_label": "Upload videos manually (optional, you can select several):",
        "total_videos_ready_info": "Total videos ready to schedule: **{count}**",
        "bulk_caption_label": "Caption (applied to all videos in this batch):",
        "videos_per_day_label": "Videos per day:",
        "start_date_label": "Starting from which date:",
        "time_per_video_markdown": "**Time for each video of the day:**",
        "video_slot_label": "Video {index}",
        "weekdays_label": "Weekdays to publish on:",
        "weekday_monday": "Monday",
        "weekday_tuesday": "Tuesday",
        "weekday_wednesday": "Wednesday",
        "weekday_thursday": "Thursday",
        "weekday_friday": "Friday",
        "weekday_saturday": "Saturday",
        "weekday_sunday": "Sunday",
        "generate_bulk_button": "📅 Generate bulk schedule",
        "no_videos_available_warning": "No videos available — generate them in Step 2 or upload manually above.",
        "select_weekday_warning": "Select at least one weekday.",
        "supabase_unavailable_error_plain": "Supabase connection not available.",
        "bulk_item_error": "Error on video {index} ({filename}): {error}",
        "bulk_success": "{count} video(s) scheduled! From {first} to {last}.",
        "bulk_error": "Error generating bulk schedule: {error}",

        "pending_subheader": "📋 Pending schedules (for the account you're logged in as)",
        "no_pending_caption": "No pending schedules.",
        "pending_item_label": "🕒 **{time}** — {caption}",
        "no_caption_placeholder": "(no caption)",
        "check_pending_button": "🔄 Check and publish schedules that are already due (manual backup, the cron does this automatically)",
        "auto_publish_error": "Error publishing schedule {id}: {error}",
        "published_count_success": "{count} video(s) published!",
        "no_due_schedules_info": "No schedules were due yet.",
        "list_schedules_error": "Error listing schedules: {error}",
    },

    "pt": {
        "avatar_use_error": "Não foi possível usar a foto de perfil no template: {error}",
        "missing_secrets_error": "⚠️ As seguintes chaves estão faltando nos Secrets do Streamlit: {keys}",
        "supabase_init_error": "⚠️ Erro ao inicializar o cliente do Supabase: {error}",

        # --- Login / Cadastro ---
        "login_page_title": "🔒 Login - Instagram Reels Downloader",
        "tab_login": "Entrar",
        "tab_signup": "Criar Conta",
        "login_subheader": "Acessar sua conta",
        "email_label": "E-mail",
        "password_label": "Senha",
        "login_button": "Entrar",
        "fill_all_fields": "Preencha todos os campos.",
        "login_success": "Login realizado com sucesso!",
        "login_error": "Erro no login: {error}",
        "signup_subheader": "Criar nova conta",
        "signup_button": "Cadastrar",
        "signup_success": "Conta criada com sucesso! Faça login para continuar.",
        "signup_error": "Erro ao cadastrar: {error}",

        # --- Barra lateral ---
        "logged_in_as": "👤 Logado como: **{email}**",
        "logout_button": "Sair (Logout)",

        # --- Título principal ---
        "app_title": "📥 Instagram Reels Downloader",
        "app_subtitle": "Monte seu template, veja a prévia, depois busque os Reels e baixe tudo já pronto em um ZIP.",
        "ffmpeg_missing": (
            "⚠️ O FFmpeg não foi encontrado no ambiente. Adicione um arquivo "
            "`packages.txt` na raiz do repositório com a linha `ffmpeg` "
            "(e reinicie o app) para que a montagem do template funcione."
        ),

        # --- Etapa 1: Template ---
        "step1_header": "1️⃣ Monte seu template",
        "avatar_uploader_label": "Foto de perfil (opcional):",
        "uploaded_photo_caption": "Foto enviada",
        "zoom_slider_label": "Zoom da foto:",
        "pos_x_slider_label": "Posição horizontal:",
        "pos_y_slider_label": "Posição vertical:",
        "avatar_preview_caption": "Prévia do avatar recortado",
        "avatar_process_error": "Não foi possível processar a imagem enviada: {error}",
        "display_name_label": "Nome a exibir no template:",
        "display_name_placeholder": "ex: Usuário Aqui",
        "verified_checkbox_label": "Mostrar selo de verificado",
        "display_handle_label": "Usuário a exibir (sem @):",
        "display_handle_placeholder": "ex: arrobaaqui",
        "caption_input_label": "Texto extra abaixo do @ (opcional):",
        "caption_input_placeholder": "ex: Confira esse vídeo!",
        "default_display_name": "Usuário Aqui",
        "default_display_handle": "arrobaaqui",
        "template_preview_subheader": "Prévia do template",
        "template_preview_caption": "A área branca abaixo do header é o limite onde o vídeo vai entrar",

        # --- Etapa 2: Buscar e baixar ---
        "step2_header": "2️⃣ Buscar vídeos e baixar",
        "apify_token_missing": "⚠️ A chave APIFY_TOKEN não foi configurada nos Secrets do Streamlit.",
        "username_field_label": "Perfil do Instagram (sem @) — usado para buscar os vídeos:",
        "username_field_placeholder": "ex: instagram",
        "count_field_label": "Quantidade de vídeos para buscar:",
        "order_by_label": "Buscar quais vídeos?",
        "order_by_recent": "Mais recentes",
        "order_by_viral": "Mais virais (visualizações + curtidas + comentários)",
        "fetch_button": "Buscar e Baixar Reels (ZIP)",
        "enter_username_warning": "Por favor, digite o nome de usuário do Instagram.",
        "fetching_spinner": "Buscando Reels de @{username}...",
        "no_videos_found_error": "Nenhum vídeo/Reel público encontrado para este perfil.",
        "videos_found_success": "Encontrados {count} vídeos! Aplicando o template e compactando...",
        "video_process_warning": "Não foi possível processar o vídeo {index}: {error}",
        "zip_success": (
            "ZIP gerado com sucesso! Esses {count} vídeos também já ficaram "
            "disponíveis na Etapa 3 pra agendar direto, sem precisar baixar e reenviar."
        ),
        "download_zip_button": "💾 Baixar todos os vídeos (.ZIP)",
        "video_preview_subheader": "Pré-visualização dos vídeos com template:",
        "video_label": "**Vídeo {index}**",
        "request_error": "Erro ao processar a requisição: {error}",

        # --- Etapa 3: Agendamento no Instagram ---
        "step3_header": "3️⃣ Agendar/Publicar no Instagram (uso pessoal)",
        "scheduling_disabled_warning": (
            "🔒 Publicação/agendamento automático está **desativado por enquanto** "
            "(pra evitar risco de bloqueio de conta enquanto isso é testado com calma). "
            "O código continua todo aqui, só não roda. Pra reativar quando quiser testar de "
            "novo: adicione o secret `IG_SCHEDULING_ENABLED = \"true\"` nas configurações do "
            "Streamlit e não esqueça de reativar o workflow no GitHub Actions também."
        ),
        "connect_account_expander": "➕ Conectar uma conta do Instagram",
        "connect_account_caption": (
            "Cole um token gerado no Graph API Explorer (Meta for Developers) pra essa "
            "conta. Ele fica salvo só pro seu login -- outros usuários do app não veem "
            "nem usam essa conta."
        ),
        "token_input_label": "Token de acesso (IGAA...):",
        "connect_account_button": "Conectar conta",
        "paste_token_warning": "Cole o token antes de conectar.",
        "account_connected_success": "Conta @{username} conectada!",
        "connect_error": "Erro ao conectar: {error}",
        "no_accounts_info": "Nenhuma conta conectada ainda. Use o \"➕ Conectar uma conta do Instagram\" acima pra começar.",
        "dashboard_subheader": "📊 Painel das contas conectadas",
        "dashboard_tab_label": "📊 Painel",
        "manage_tab_label": "🔗 Gerenciar e Publicar",
        "dashboard_followers": "Seguidores",
        "dashboard_posts": "Posts",
        "dashboard_limited_stats": "Alguns dados não estão disponíveis pras permissões desse token.",
        "dashboard_pending_count": "{count} agendamento(s) pendente(s)",
        "dashboard_stats_error": "Não foi possível carregar os dados: {error}",
        "select_account_label": "Conta do Instagram para postar:",
        "publish_video_subheader": "Publicar um vídeo",
        "video_uploader_label": "Vídeo (.mp4) já com o template aplicado:",
        "reel_caption_label": "Legenda do Reels:",
        "when_to_publish_label": "Quando publicar?",
        "publish_now_option": "Agora",
        "schedule_later_option": "Agendar para depois",
        "date_label": "Data:",
        "time_label": "Hora:",
        "jitter_caption": "O horário real de publicação varia até 10 minutos pra mais ou pra menos (evita parecer bot).",
        "confirm_button": "Confirmar",
        "upload_video_warning": "Envie o vídeo que deseja publicar.",
        "supabase_unavailable_error": "Conexão com o Supabase não disponível — não dá pra guardar o vídeo.",
        "uploading_spinner": "Enviando vídeo para o Storage...",
        "publishing_spinner": "Publicando no Instagram (isso pode levar até 1-2 minutos)...",
        "published_success": "Publicado com sucesso! ID da publicação: `{media_id}`",
        "scheduled_success": "Agendado para perto de {datetime}!",
        "publish_schedule_error": "Erro ao publicar/agendar: {error}",

        "bulk_subheader": "📦 Agendamento em massa",
        "bulk_caption_intro": (
            "Define quantos vídeos por dia, em quais horários e dias da semana, "
            "e a partir de quando — o app distribui os vídeos automaticamente nesses slots."
        ),
        "use_generated_checkbox": "Usar os {count} vídeos gerados na Etapa 2 (nesta sessão)",
        "no_generated_videos_caption": "Nenhum vídeo gerado nesta sessão ainda (gere na Etapa 2 pra aparecer aqui).",
        "bulk_uploader_label": "Enviar vídeos manualmente (opcional, pode selecionar vários):",
        "total_videos_ready_info": "Total de vídeos prontos para agendar: **{count}**",
        "bulk_caption_label": "Legenda (aplicada a todos os vídeos deste lote):",
        "videos_per_day_label": "Vídeos por dia:",
        "start_date_label": "A partir de qual data:",
        "time_per_video_markdown": "**Horário de cada vídeo do dia:**",
        "video_slot_label": "Vídeo {index}",
        "weekdays_label": "Dias da semana em que deve publicar:",
        "weekday_monday": "Segunda",
        "weekday_tuesday": "Terça",
        "weekday_wednesday": "Quarta",
        "weekday_thursday": "Quinta",
        "weekday_friday": "Sexta",
        "weekday_saturday": "Sábado",
        "weekday_sunday": "Domingo",
        "generate_bulk_button": "📅 Gerar agendamento em massa",
        "no_videos_available_warning": "Nenhum vídeo disponível — gere na Etapa 2 ou envie manualmente acima.",
        "select_weekday_warning": "Selecione pelo menos um dia da semana.",
        "supabase_unavailable_error_plain": "Conexão com o Supabase não disponível.",
        "bulk_item_error": "Erro no vídeo {index} ({filename}): {error}",
        "bulk_success": "{count} vídeo(s) agendado(s)! Do dia {first} até {last}.",
        "bulk_error": "Erro ao gerar agendamento em massa: {error}",

        "pending_subheader": "📋 Agendamentos pendentes (dessa conta que você está logado)",
        "no_pending_caption": "Nenhum agendamento pendente.",
        "pending_item_label": "🕒 **{time}** — {caption}",
        "no_caption_placeholder": "(sem legenda)",
        "check_pending_button": "🔄 Verificar e publicar agendados que já venceram (backup manual, o cron faz isso sozinho)",
        "auto_publish_error": "Erro ao publicar agendamento {id}: {error}",
        "published_count_success": "{count} vídeo(s) publicado(s)!",
        "no_due_schedules_info": "Nenhum agendamento estava vencido ainda.",
        "list_schedules_error": "Erro ao listar agendamentos: {error}",
    },
}


def t(key, **kwargs):
    """
    Looks up `key` in the current language (st.session_state['lang'], default
    'en') and formats it with any kwargs. Falls back to English, then to the
    raw key itself, so a missing translation never crashes the app.
    """
    import streamlit as st
    lang = st.session_state.get("lang", "en")
    text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key)
    if text is None:
        text = TRANSLATIONS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
