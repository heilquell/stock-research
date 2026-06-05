FROM python:3.11-slim

# Prophet braucht build-essentials für cmdstanpy/Stan
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# cmdstan 2.33.1 an Prophets erwarteten Pfad installieren
# (Prophet 1.1.5 bundled nur einen Stub, Pfad ist hardcoded auf cmdstan-2.33.1)
RUN python -c "\
import cmdstanpy, shutil; \
from pathlib import Path; \
import prophet; \
stan_dir = Path(prophet.__file__).parent / 'stan_model'; \
shutil.rmtree(stan_dir / 'cmdstan-2.33.1', ignore_errors=True); \
cmdstanpy.install_cmdstan(version='2.33.1', dir=str(stan_dir))"

COPY . .

# Volume-Mount-Pfad — wird via docker-compose gemounted
ENV STOCKS_DB=/data/stocks.db

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py"]
