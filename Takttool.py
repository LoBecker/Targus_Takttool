import streamlit as st

# Muss als ALLERERSTES kommen!
st.set_page_config(page_title="Takttool – Montage- & Personalplanung", layout="wide")
# --- Passwortschutz ---
import streamlit as st
import hashlib

def check_password():
    import hashlib

   def check_password():
    import hashlib

    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()

    correct_password = hash_password("Targus2025!")

    if "auth_ok" not in st.session_state:
        st.session_state["auth_ok"] = False

    if not st.session_state["auth_ok"]:
        password = st.text_input("🔒 Bitte Passwort eingeben", type="password")

        if not password:
            st.stop()

        if hash_password(password) == correct_password:
            st.session_state["auth_ok"] = True
            st.success("✅ Login erfolgreich.")
            st.stop()  # Stoppen → nächster Reload zeigt App
        else:
            st.error("❌ Falsches Passwort")
            st.stop()

check_password()

import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import datetime, timedelta
import base64
import os
import sys
from pathlib import Path

# Ladebildschirm nur beim allerersten Start zeigen
if "geladen" not in st.session_state:
    st.markdown("""
    <style>
    /* Dark Theme + Schrift */
    html, body, [data-testid="stApp"] {
        background-color: #1a1a1a;
        color: #ffffff;
        font-family: 'Segoe UI', sans-serif;
    }
    
    /* Headline-Styling */
    h1, h2, h3 {
        color: #CC0000;
        text-align: center;
    }
    
    /* Upload-Box */
    .upload-box {
        background-color: #2a2a2a;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        text-align: right;
    }
    
    /* DataFrame-Container */
    .stDataFrameContainer {
        border-radius: 10px;
        border: 1px solid #444;
    }
    
    /* Tabs */
    div[data-baseweb="tabs"] {
        margin-top: 1rem;
    }
    
    button[data-baseweb="tab"] {
        font-size: 22px !important;
        padding: 18px 24px !important;
        margin: 0 !important;
        height: auto !important;
        border-radius: 0 !important;
        border: none !important;
        background-color: #2a2a2a !important;
        color: #ddd !important;
        transition: background-color 0.3s ease;
    }
    
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #CC0000 !important;
        color: white !important;
        font-weight: bold;
    }
    
    button[data-baseweb="tab"] + button[data-baseweb="tab"] {
        border-left: 1px solid #1a1a1a;
    }
    
    /* Entfernt dünnen Streifen ganz oben */
    [data-testid="stHeader"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        height: 0px !important;
    }
    
    /* Weitere Absicherung */
    header, .st-emotion-cache-18ni7ap {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    </style>
""", unsafe_allow_html=True)



# --- .exe-kompatibler Pfad ---
def get_abs_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_data_path():
    return os.path.join(get_exe_dir(), "daten.csv")

def speichere_daten(df):
    try:
        df.to_csv(get_data_path(), index=False)
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
        return False

def lade_und_verarbeite_datei(uploaded_file):
    df = pd.DataFrame()
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".xlsx"):
                df = pd.read_excel(uploaded_file, engine="openpyxl")
            else:
                df = pd.read_csv(uploaded_file)

            df.columns = [col.strip() for col in df.columns]

            erwartete_spalten = ["Tag (MAP)", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum"]
            fehlende = [col for col in erwartete_spalten if col not in df.columns]
            if fehlende:
                st.error(f"Fehlende Spalten: {', '.join(fehlende)}")
                return pd.DataFrame(columns=erwartete_spalten)

            df["Tag (MAP)"] = pd.to_numeric(df["Tag (MAP)"], errors="coerce").fillna(0).astype(int)
            df["Takt"] = pd.to_numeric(df["Takt"], errors="coerce").fillna(0).astype(int)
            df["Stunden"] = pd.to_numeric(df["Soll-Zeit"], errors="coerce").fillna(0)
            df["Stunden"] = df["Stunden"].apply(lambda x: max(x, 0.1))
            df["Tag_Takt"] = df["Tag (MAP)"].astype(str) + "_T" + df["Takt"].astype(str)

            speichere_daten(df)
            st.success("Datei erfolgreich hochgeladen und verarbeitet.")
        except Exception as e:
            st.error(f"Fehler beim Verarbeiten: {e}")
    else:
        st.info("⬆️ Lade eine Datei hoch, um zu starten.")
    return df

# --- Upload UI ---
def zeige_header_mit_upload():
    logo_path = Path(get_abs_path("Logo_Targus.png"))
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        logo_base64 = base64.b64encode(logo_bytes).decode()
        logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="height:60px;">'
    else:
        logo_html = '<div style="width:60px; height:60px; background:#ccc;"></div>'

    col_logo, col_title, col_upload = st.columns([1, 2, 1])

    with col_logo:
        st.markdown(logo_html, unsafe_allow_html=True)

    with col_title:
        st.markdown("<h1>Takttool | Montage- & Personalplanung</h1>", unsafe_allow_html=True)

    with col_upload:
        uploaded_file = st.file_uploader("", type=["csv", "xlsx"], label_visibility="collapsed")
        return uploaded_file

# --- App Start ---
uploaded_file = zeige_header_mit_upload()
df = lade_und_verarbeite_datei(uploaded_file)

# Sicherheitsnetz: fehlende Spalten ergänzen
minimale_spalten = ["Tag (MAP)", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum", "Stunden", "Tag_Takt"]
for spalte in minimale_spalten:
    if spalte not in df.columns:
        df[spalte] = ""

# Tabs vorbereiten – egal ob Daten oder nicht
st.divider()

# --- Tabs erstellen ---
tab1, tab2 = st.tabs(["Montageplanung", "Personalplanung"])

# --- Feiertage (als date-Objekte) ---
FEIERTAGE = [
    datetime(2025, 1, 1).date(),
    datetime(2025, 5, 1).date(),
    datetime(2025, 10, 3).date(),
    datetime(2025, 12, 25).date()
]

def ist_arbeitstag(d: datetime.date):
    return d.weekday() < 5 and d not in FEIERTAGE

def arbeitstag_ab(start: datetime.date, tage: int):
    tag_count = 0
    current = start
    while tag_count < tage:
        current += timedelta(days=1)
        if ist_arbeitstag(current):
            tag_count += 1
    return current


# --- Tab 1: Montageplanung ---

with tab1:
    
    # --- Startdatum und Zeitraum nebeneinander ---
    col_links, col_rechts = st.columns([1, 3])

    with col_links:
        st.markdown("#### Startdatum der Planung ")
        startdatum = st.date_input("Startdatum", value=datetime.today(), key="startdatum_input")

    with col_rechts:
        st.markdown("#### Zeitraum wählen")
        tag_takt_list = sorted(df["Tag_Takt"].unique(), key=lambda x: (int(x.split("_T")[0]), int(x.split("_T")[1])))
        idx_min, idx_max = 0, len(tag_takt_list) - 1

        takt_range = st.slider(
            "Tag_Takt auswählen",
            min_value=idx_min,
            max_value=idx_max,
            value=(idx_min, idx_max),
            key="montage_slider"
        )

    selected_tag_takte = tag_takt_list[takt_range[0]:takt_range[1] + 1]

    # --- Zeitzuordnung (Start/Ende berechnen) ---
    df["Tag (MAP)"] = df["Tag (MAP)"].astype(int)
    tag_mapping = {
        tag: arbeitstag_ab(startdatum, tag - 1)
        for tag in sorted(df["Tag (MAP)"].unique())
    }
    df["Start_Datum"] = df["Tag (MAP)"].map(tag_mapping)
    df["Start"] = pd.to_datetime(df["Start_Datum"]) + pd.to_timedelta(6, unit='h')
    df["Ende"] = df["Start"] + pd.to_timedelta(df["Stunden"], unit="h")

    # --- Filter auf Auswahl anwenden ---
    df_filtered = df[df["Tag_Takt"].isin(selected_tag_takte)].copy()
    # --- Tabelle und Gantt nebeneinander ---
    
    col_table, col_gantt = st.columns([1.2, 1.8])

    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            speichere_daten(df)
            st.success("Änderungen gespeichert.")

    with col_gantt:
        
        if not df_filtered.empty:
            fig_gantt = px.timeline(
                df_filtered,
                x_start="Start",
                x_end="Ende",
                y="Inhalt",
                color="Qualifikation",
                title="Ablaufplanung"
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_layout(
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff",
                height=600
            )
            st.plotly_chart(fig_gantt, use_container_width=True)
        else:
            st.info("Keine Daten für Gantt-Diagramm.")
    
        # --- Statistiken und Diagramme ---
    st.divider()
    

    if not df_filtered.empty:
        df_filtered["Tag (MAP)"] = df_filtered["Tag (MAP)"].astype(int)

        # Datenbereiche definieren
        bereich_1 = df_filtered[df_filtered["Tag (MAP)"].between(0, 7)]
        bereich_2 = df_filtered[df_filtered["Tag (MAP)"].between(8, 14)]
        bereich_3 = df_filtered[df_filtered["Tag (MAP)"].between(15, 21)]

        # Gruppierung
        def gruppiere(df, group_field):
            return df.groupby(["Tag (MAP)", group_field])["Stunden"].sum().reset_index()

        bauraum_data = [gruppiere(bereich_1, "Bauraum"), gruppiere(bereich_2, "Bauraum"), gruppiere(bereich_3, "Bauraum")]
        quali_data   = [gruppiere(bereich_1, "Qualifikation"), gruppiere(bereich_2, "Qualifikation"), gruppiere(bereich_3, "Qualifikation")]
        titel_map = ["Takt 1", "Takt 2", "Takt 3"]


        col_bauraum, col_qualifikation = st.columns(2)

        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                fig = px.bar(
                    df_plot, x="Tag (MAP)", y="Stunden", color="Bauraum",
                    barmode="stack", title=titel_map[i], height=300
                )
                fig.update_layout(
                    plot_bgcolor="#1a1a1a",
                    paper_bgcolor="#1a1a1a",
                    font_color="#ffffff"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_qualifikation:
            st.markdown("###  Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                fig = px.bar(
                    df_plot, x="Tag (MAP)", y="Stunden", color="Qualifikation",
                    barmode="stack", title=titel_map[i], height=300
                )
                fig.update_layout(
                    plot_bgcolor="#1a1a1a",
                    paper_bgcolor="#1a1a1a",
                    font_color="#ffffff"
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Keine Daten für Statistiken vorhanden.")


with tab2:

    if not df.empty:
        # --- Auswahl: 5 oder 7 Tage Planung ---
        planungstage = st.radio("Personalplanung für 5 oder 7 Tage:", [5, 7], horizontal=True)

        # --- Eingabefeld für FTE-Stunden vor die Matrix ziehen ---
        if "fte_stunden" not in st.session_state:
            st.session_state["fte_stunden"] = 8

        fte_basis = st.number_input(
            "Wieviele Stunden arbeitet ein FTE pro Tag?",
            min_value=1,
            max_value=24,
            step=1,
            key="fte_stunden"
        )

        # --- Alle MAP-Tage aus Datei extrahieren ---
        tag_map_liste = sorted(df["Tag (MAP)"].dropna().unique().astype(int).tolist())

        # --- Feste Wagenkasten-Labels ---
        wagenkästen = [f"Wagenkasten {i}" for i in range(1, 13)]

        zuordnung = {tag_map: [] for tag_map in tag_map_liste}

        # --- Hilfsfunktion: angrenzende Checkboxen berechnen ---
        def berechne_automatische_auswahl(tag_idx, planungstage, tag_map_liste):
            offset = planungstage // 2
            start = max(0, tag_idx - offset)
            end = min(len(tag_map_liste), tag_idx + offset + 1)
            return tag_map_liste[start:end]




        st.markdown("### Zuordnung der Wagenkästen zu MAP-Tagen")

        header_cols = st.columns([1] + [1]*len(wagenkästen))
        header_cols[0].markdown("**MAP-Tag**")
for tag_idx, tag_map in enumerate(tag_map_liste):
    cols = st.columns([1] + [1]*len(wagenkästen))
    cols[0].markdown(f"Tag {tag_map}")

    for wk_idx, wk in enumerate(wagenkästen):
        key = f"{wk}_{tag_map}"
        current_value = st.session_state.get(key, False)

        checkbox_clicked = cols[wk_idx + 1].checkbox("", value=current_value, key=key)

        if checkbox_clicked and not current_value:
            # Automatisch benachbarte MAP-Tage (gleiche Spalte/Wagenkasten)
            offset = planungstage // 2
            start = max(0, tag_idx - offset)
            end = min(len(tag_map_liste), tag_idx + offset + 1)
            for i in range(start, end):
                st.session_state[f"{wk}_{tag_map_liste[i]}"] = True
            st.rerun()

        if st.session_state.get(key, False):
            zuordnung[tag_map].append(wk)


        # Separate Submit-Schaltfläche unterhalb
        submitted = st.button("Berechne Personalbedarf")


        if submitted:
            fehler_wagen = []
            belegung_pro_wagen = {wk: 0 for wk in wagenkästen}

            for tag_map, wagenliste in zuordnung.items():
                for wk in wagenliste:
                    belegung_pro_wagen[wk] += 1

            for wk, count in belegung_pro_wagen.items():
                if count != 0 and count != planungstage:
                    fehler_wagen.append((wk, count))

            if fehler_wagen:
                fehltext = ", ".join([f"{wk} ({anzahl})" for wk, anzahl in fehler_wagen])
                st.error(f"Fehler: Die folgenden Wagenkästen haben nicht exakt {planungstage} Häkchen (oder null): {fehltext}")
                st.stop()

            map_counter = {tag_map: len(wagenliste) for tag_map, wagenliste in zuordnung.items() if wagenliste}

            df_gesamt = pd.DataFrame()
            for tag_map, faktor in map_counter.items():
                df_part = df[df["Tag (MAP)"] == tag_map].copy()
                if not df_part.empty:
                    df_part["Stunden"] *= faktor
                    df_gesamt = pd.concat([df_gesamt, df_part], ignore_index=True)

            if df_gesamt.empty:
                st.info("Keine Aufgaben für die gewählte Planung gefunden.")
            else:
                st.subheader("Personalbedarf gesamt")
                gruppe = df_gesamt.groupby("Qualifikation")["Stunden"].sum().reset_index()
                gruppe["FTE"] = gruppe["Stunden"] / st.session_state["fte_stunden"]
                st.dataframe(gruppe)

                st.markdown("### Taktbasierter Stundenbedarf pro Kalendertag")

                wagenkasten_to_map = {wk: [] for wk in wagenkästen}
                for tag_map, wks in zuordnung.items():
                    for wk in wks:
                        wagenkasten_to_map[wk].append(tag_map)

                einträge = []
                for wk, map_tage in wagenkasten_to_map.items():
                    if not map_tage:
                        continue
                    map_tage_sorted = sorted(map_tage)
                    tag_pos_map = {map_tag: i for i, map_tag in enumerate(map_tage_sorted)}
                    df_subset = df[df["Tag (MAP)"].isin(map_tage_sorted)].copy()
                    if df_subset.empty:
                        continue
                    for _, row in df_subset.iterrows():
                        map_tag = int(row["Tag (MAP)"])
                        if map_tag not in tag_pos_map:
                            continue
                        kalender_tag = tag_pos_map[map_tag] + 1
                        einträge.append({
                            "Kalendertag": kalender_tag,
                            "Qualifikation": row["Qualifikation"],
                            "Stunden": row["Stunden"]
                        })

                if einträge:
                    df_plot = pd.DataFrame(einträge)
                    df_plot = df_plot.groupby(["Kalendertag", "Qualifikation"])["Stunden"].sum().reset_index()

                    fig = px.bar(
                        df_plot,
                        x="Kalendertag",
                        y="Stunden",
                        color="Qualifikation",
                        title="Stundenbedarf pro Kalendertag (gestapelt)",
                        barmode="stack"
                    )
                    fig.update_layout(
                        plot_bgcolor="#1a1a1a",
                        paper_bgcolor="#1a1a1a",
                        font_color="#ffffff"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # FTE-Plot direkt im Anschluss
                    df_fte = df_plot.copy()
                    df_fte["FTE"] = df_fte["Stunden"] / st.session_state["fte_stunden"]

                    st.markdown("### FTE-Bedarf pro Kalendertag")
                    fig_fte = px.bar(
                        df_fte,
                        x="Kalendertag",
                        y="FTE",
                        color="Qualifikation",
                        title="FTE-Bedarf pro Kalendertag (gestapelt)",
                        barmode="stack",
                        labels={"FTE": "FTE"}
                    )
                    fig_fte.update_layout(
                        plot_bgcolor="#1a1a1a",
                        paper_bgcolor="#1a1a1a",
                        font_color="#ffffff"
                    )
                    st.plotly_chart(fig_fte, use_container_width=True)

                    # Tabelle: Aufgerundete FTE pro Kalendertag pro Qualifikation
                    df_rund = df_fte.copy()
                    df_rund["Aufgerundete FTE"] = df_rund["FTE"].apply(np.ceil)
                    df_rund = df_rund[["Kalendertag", "Qualifikation", "Aufgerundete FTE"]]
                    df_rund.columns = ["Tag", "Qualifikation", "Aufgerundete FTE"]
                    st.markdown("### Aufgerundete FTE je Tag und Qualifikation")
                    st.dataframe(df_rund)
                else:
                    st.info("Keine Daten für taktbasierte Darstellung vorhanden.")

    else:
        st.warning("Keine Daten geladen.")


# --- Footer / Info für .exe-Nutzung ---
st.markdown("""---""")
st.markdown(
    """
    <div style='text-align: center; font-size: 0.9rem; color: #888;'>
        Entwickelt für Stadlerrail | Urheber: Targus Management Consulting <br>
        For Support contact louis.becker@targusmc.de
        
    </div>
    """,
    unsafe_allow_html=True
)
import webbrowser
import time

if __name__ == "__main__" and getattr(sys, 'frozen', False):
    time.sleep(2)  # Kurze Wartezeit, damit der Server sicher läuft
    try:
        webbrowser.open("http://localhost:8501")
    except Exception as e:
        print(f"Fehler beim Öffnen des Browsers: {e}")
