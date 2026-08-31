"""
Funções puras de integração com a Instagram API (Instagram Login / tokens IGAA).
Não depende do Streamlit -- usado tanto pelo app.py quanto pelo cron_publish.py.
"""
import time
import requests

IG_GRAPH_BASE = "https://graph.instagram.com"
IG_CONTAINER_POLL_SECONDS = 5
IG_CONTAINER_MAX_WAIT_SECONDS = 180


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


def get_ig_account_stats(access_token):
    """
    Busca dados mais completos da conta para exibir num dashboard:
    seguidores, quantidade de posts, foto de perfil, nome, biografia.
    Se algum campo não estiver disponível pra esse token (permissões variam),
    cai de volta pros campos básicos em vez de quebrar.
    """
    full_fields = "user_id,username,account_type,name,media_count,followers_count,follows_count,profile_picture_url,biography"
    resp = requests.get(
        f"{IG_GRAPH_BASE}/me",
        params={"fields": full_fields, "access_token": access_token},
        timeout=30,
    )
    data = resp.json()

    if resp.status_code == 200 and "user_id" in data:
        return data

    # Fallback: alguns tokens/escopos não liberam todos os campos extras
    basic = get_ig_login_account(access_token)
    basic["_stats_limited"] = True
    return basic


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
