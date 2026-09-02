"""
Script standalone (SEM Streamlit) que verifica a tabela `scheduled_posts` no
Supabase e publica no Instagram tudo que já venceu. Feito para ser chamado
periodicamente por um agendador externo (GitHub Actions, por exemplo) --
Streamlit sozinho não consegue rodar tarefas em segundo plano de forma confiável.

Cada linha da tabela já guarda o próprio access_token (snapshot de quando foi
agendado) -- isso é o que permite vários usuários/contas diferentes conviverem
na mesma tabela, cada um com o token da conta que ele mesmo conectou.

Depois de publicar com sucesso, o vídeo é apagado do Supabase Storage (não
faz sentido manter o arquivo depois de já ter ido pro Instagram).

Variáveis de ambiente necessárias:
  SUPABASE_URL
  SUPABASE_KEY
  IG_STORAGE_BUCKET   (opcional, default "reels-videos")
"""
import os
import sys
from datetime import datetime, timezone

from supabase import create_client
from ig_publisher import publish_reel_now

IG_STORAGE_BUCKET = os.environ.get("IG_STORAGE_BUCKET", "reels-videos")


def main():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not all([supabase_url, supabase_key]):
        print("ERRO: faltam variáveis de ambiente (SUPABASE_URL, SUPABASE_KEY).")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    # Sem tzinfo de propósito -- a coluna é "timestamp" (sem fuso) e agora o
    # app sempre salva em UTC "ingênuo". Comparar um valor com "+00:00" contra
    # uma coluna sem fuso é justamente o que causava agendamentos "vencidos"
    # que nunca eram detectados como vencidos.
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    pending = (
        supabase.table("scheduled_posts")
        .select("*")
        .eq("status", "pending")
        .lte("scheduled_time", now_iso)
        .execute()
        .data
    )

    if not pending:
        print(f"[{now_iso}] Nada vencido pra publicar agora.")
        return

    print(f"[{now_iso}] {len(pending)} agendamento(s) vencido(s). Publicando...")

    for post in pending:
        post_id = post["id"]
        access_token = post.get("access_token")

        if not access_token:
            supabase.table("scheduled_posts").update({
                "status": "error",
                "error_message": "Post sem access_token salvo (agendado antes da migração de contas por usuário?).",
            }).eq("id", post_id).execute()
            print(f"  ✖ Post {post_id} sem access_token -- pulado.")
            continue

        try:
            media_id = publish_reel_now(
                post["ig_id"], post["video_url"], post.get("caption", ""), access_token
            )

            supabase.table("scheduled_posts").update({
                "status": "published",
                "published_media_id": media_id,
            }).eq("id", post_id).execute()

            # Vídeo já publicado -- não precisa mais ocupar espaço no Storage.
            storage_path = post.get("storage_path")
            if storage_path:
                try:
                    supabase.storage.from_(IG_STORAGE_BUCKET).remove([storage_path])
                    print(f"  ✔ Post {post_id} publicado ({media_id}) e vídeo apagado do Storage.")
                except Exception as cleanup_err:
                    print(f"  ⚠ Post {post_id} publicado, mas falhou ao apagar do Storage: {cleanup_err}")
            else:
                print(f"  ✔ Post {post_id} publicado ({media_id}).")

        except Exception as publish_err:
            supabase.table("scheduled_posts").update({
                "status": "error",
                "error_message": str(publish_err),
            }).eq("id", post_id).execute()
            print(f"  ✖ Erro ao publicar post {post_id}: {publish_err}")


if __name__ == "__main__":
    main()
