"""Multi-Page Entry-Point: ueberschreibt die file-based Sidebar-Navigation
mit st.navigation, damit der Home-Eintrag nicht mehr „main" heisst und
mit Icon + groesserer Schrift erscheint.
"""
import os

import streamlit as st

st.markdown(
    """
    <style>
    /* Groessere Schrift fuer die Sidebar-Navigation */
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {
        font-size: 1.15rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
        padding: 0.5rem 0.75rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# (Pfad, Titel, Icon) -- die Reihenfolge hier ist die Reihenfolge in der Leiste.
SEITEN = [
    ("main.py", "Home", "🏠"),
    ("pages/1_📊_Crossover.py", "Crossover", "📊"),
    ("pages/2_🧮_Optionen.py", "Optionen", "🧮"),
    ("pages/3_🤖_Agent.py", "Agent", "🤖"),
]

# Wer st.navigation benutzt, schaltet die dateibasierte Navigation ab: eine
# Datei unter pages/ existiert fuer Streamlit dann nur, wenn sie oben steht.
# Fehlt sie, merkt man es erst, wenn jemand den Link anklickt -- als
# Traceback mitten auf der Seite. Deshalb der Abgleich beim Start.
_ordner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")
_vorhanden = {"pages/" + n for n in os.listdir(_ordner) if n.endswith(".py")}
_nicht_registriert = sorted(_vorhanden - {pfad for pfad, _, _ in SEITEN})
if _nicht_registriert:
    st.error(
        "Nicht in app.py registriert und deshalb nicht erreichbar: "
        + ", ".join(_nicht_registriert)
    )

pages = [st.Page(pfad, title=titel, icon=icon, default=(pfad == "main.py"))
         for pfad, titel, icon in SEITEN]
pg = st.navigation(pages)
pg.run()
