"""Google-Anmeldung und Rechte fuer das Research-Tool.

Streamlit bringt seit 1.42 OIDC eingebaut mit (``st.login`` / ``st.user``),
deshalb braucht es keinen oauth2-proxy davor. Die Zugangsdaten stehen in
``.streamlit/secrets.toml``, die der Entrypoint aus Umgebungsvariablen
erzeugt — sie liegen NICHT im Repo.

**Sicherer Rueckfall:** Sind keine Zugangsdaten hinterlegt, laeuft die App im
Lesemodus. Kein Hinzufuegen, kein Loeschen, Favoriten nur ansehen. Das ist
Absicht: vorher lag unter der oeffentlichen URL ein Button, der die
Kurshistorie aus ``stock_data`` loeschen konnte — ohne jede Anmeldung. Lieber
eine App, die weniger kann, als eine, die jeder leerraeumen kann.

Rechte-Modell (Entscheidung Georg, 13.08.2026):
* **Jeder mit Google-Konto** darf sich anmelden und hat eigene Favoriten.
* **Titel hinzufuegen** darf jeder Angemeldete — die Liste waechst nur.
* **Titel loeschen** darf nur der Admin. ``stock_data`` ist geteilt und
  haengt am naechtlichen Cron; geloeschte Historie delisteter Titel ist
  ueber yfinance nicht wiederherstellbar.
"""
from __future__ import annotations

import os

import streamlit as st


def authlib_vorhanden() -> bool:
    """Streamlit laedt Authlib erst beim Aufruf von ``st.login`` nach.

    Fehlt es, laeuft der Start sauber durch und die Seite stirbt erst beim
    Klick auf "Anmelden" mit einem Traceback. Deshalb hier vorab pruefen und
    lieber in den Lesemodus gehen als die Seite zu zerlegen.
    """
    try:
        import authlib  # noqa: F401
        return True
    except ImportError:
        return False


def auth_konfiguriert() -> bool:
    """True, wenn Google-Zugangsdaten hinterlegt sind UND Authlib da ist.

    Achtung auf die Struktur: bei der Mehr-Anbieter-Form steht ``client_id``
    unter ``[auth.google]``, nicht unter ``[auth]`` — genau das erzeugt der
    Entrypoint, weil ``st.login("google")`` diese Form erwartet.
    """
    if not authlib_vorhanden():
        return False
    try:
        return bool(st.secrets["auth"]["google"]["client_id"])
    except Exception:  # noqa: BLE001 - secrets.toml fehlt komplett
        return False


def user_email() -> str | None:
    """E-Mail des angemeldeten Nutzers, sonst None."""
    if not auth_konfiguriert():
        return None
    try:
        if getattr(st.user, "is_logged_in", False):
            return (st.user.get("email") or "").lower() or None
    except Exception:  # noqa: BLE001
        return None
    return None


def admin_email() -> str:
    return (os.environ.get("ADMIN_EMAIL") or "").strip().lower()


def ist_admin() -> bool:
    mail = user_email()
    return bool(mail) and mail == admin_email()


def darf_hinzufuegen() -> bool:
    """Titel ins gemeinsame Universum aufnehmen — jeder Angemeldete."""
    return user_email() is not None


def darf_loeschen() -> bool:
    """Titel samt Kurshistorie loeschen — nur Admin."""
    return ist_admin()


# Obergrenze je Nutzer und Sitzung. Das Universum ist geteilt und der
# naechtliche Cron arbeitet es ab (aktuell ~9,5 min fuer 3.238 Titel) —
# ohne Deckel koennte ein einzelner Nutzer den Lauf beliebig verlaengern.
MAX_NEUE_TITEL_PRO_MAL = 20


def sidebar_login() -> str | None:
    """Zeichnet den Anmelde-Block in die Sidebar. Returns E-Mail oder None."""
    if not auth_konfiguriert():
        grund = ("das Paket Authlib fehlt im Image"
                 if not authlib_vorhanden()
                 else "es sind keine Google-Zugangsdaten hinterlegt")
        st.sidebar.info(
            f"🔒 **Lesemodus** — {grund}. "
            "Favoriten und Aktienliste sind schreibgeschuetzt."
        )
        return None

    mail = user_email()
    if mail:
        st.sidebar.success(f"angemeldet als **{mail}**"
                           + ("  ·  Admin" if ist_admin() else ""))
        if st.sidebar.button("Abmelden"):
            st.logout()
        return mail

    st.sidebar.write("Mit Google anmelden, um eigene Favoriten zu speichern.")
    if st.sidebar.button("🔑 Mit Google anmelden"):
        st.login("google")
    return None
