"""
Script standalone (SEM Streamlit) que verifica a tabela `scheduled_posts` no
Supabase e publica no Instagram tudo que já venceu. Feito para ser chamado
periodicamente por um agendador externo (GitHub Actions, por exemplo) --
Streamlit sozinho não consegue rodar tarefas em segundo plano de forma confiável.

Depois de publicar com sucesso, o vídeo é apagado do Supabase Storage (não
faz sentido manter o arquivo depois de já ter ido pro Instagram).

Variáveis de ambiente necessárias:
  SUPABASE_URL
  SUPABASE_KEY
  IG_ACCESS_TOKEN
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
    ig_access_token = os.environ.get("IG_ACCESS_TOKEN")

    if not all([supabase_url, supabase_key, ig_access_token]):
        print("ERRO: faltam variáveis de ambiente (SUPABASE_URL, SUPABASE_KEY, IG_ACCESS_TOKEN).")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    now_iso = datetime.now(timezone.utc).isoformat()

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
        try:
            media_id = publish_reel_now(
                post["ig_id"], post["video_url"], post.get("caption", ""), ig_access_token
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
