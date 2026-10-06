# Anwendungs-Image: nur noch der Code. Alles Schwere steckt im Basis-Image.
#
# Die Abhaengigkeiten (Prophet, cmdstan, Streamlit) liegen in
# research-base:1, gebaut aus Dockerfile.base. Dadurch kostet eine Aenderung
# an einer Streamlit-Seite einen Build von Sekunden statt einer Viertelstunde
# -- auch dann, wenn der woechentliche `docker builder prune` den Cache
# zwischendurch geleert hat.
#
# Aendert sich requirements.txt, muss ZUERST das Basis-Image neu gebaut
# werden, sonst laeuft die Anwendung mit alten Paketversionen weiter:
#
#     docker build -f Dockerfile.base -t research-base:1 .
#
# Siehe Kopf von Dockerfile.base.
FROM research-base:1

WORKDIR /app

COPY . .

# Volume-Mount-Pfad — wird via docker-compose gemounted
ENV STOCKS_DB=/data/stocks.db

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
