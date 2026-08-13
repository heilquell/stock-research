#!/bin/sh
# Erzeugt .streamlit/secrets.toml aus Umgebungsvariablen und startet Streamlit.
#
# Warum nicht direkt eine secrets.toml ins Image: dann laegen Client-Secret
# und Cookie-Secret im Repo bzw. im Image-Layer. So kommen sie ueber
# /docker/research/.env (untracked) rein und existieren nur zur Laufzeit.
#
# Fehlt GOOGLE_CLIENT_ID, wird KEINE secrets.toml geschrieben -> die App
# laeuft im Lesemodus (auth.auth_konfiguriert() == False).
set -e

SECRETS_DIR=/app/.streamlit
SECRETS_FILE="$SECRETS_DIR/secrets.toml"
mkdir -p "$SECRETS_DIR"
rm -f "$SECRETS_FILE"

if [ -n "$GOOGLE_CLIENT_ID" ] && [ -n "$GOOGLE_CLIENT_SECRET" ] \
   && [ -n "$AUTH_COOKIE_SECRET" ] && [ -n "$AUTH_REDIRECT_URI" ]; then
  cat > "$SECRETS_FILE" <<EOF
[auth]
redirect_uri = "$AUTH_REDIRECT_URI"
cookie_secret = "$AUTH_COOKIE_SECRET"

[auth.google]
client_id = "$GOOGLE_CLIENT_ID"
client_secret = "$GOOGLE_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
  chmod 600 "$SECRETS_FILE"
  echo "[entrypoint] Google-Anmeldung aktiv (redirect_uri=$AUTH_REDIRECT_URI)"
else
  echo "[entrypoint] Keine Google-Zugangsdaten -> Lesemodus (keine Schreibrechte)"
fi

exec streamlit run app.py
