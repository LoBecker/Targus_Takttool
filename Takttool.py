import streamlit as st 
import hashlib
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go  # bleibt für evtl. Zusatzlinien
from datetime import datetime, timedelta
import base64
import os
import sys
from pathlib import Path
import difflib  # Auto-Vorschlag für Mapping
import json
import streamlit.components.v1 as components  # für dynamische JS-Interaktion

st.set_page_config(page_title="Takttool – Montage- & Personalplanung", layout="wide")

# --- Passwortschutz ---
def check_password():
    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()

    correct_password = hash_password("Targus2025!")

    if "auth_ok" not in st.session_state:
        st.session_state["auth_ok"] = False

    if not st.session_state["auth_ok"]:
        st.markdown("## 🔐 Geschützter Bereich")
        with st.form("login_form"):
            password = st.text_input("Bitte Passwort eingeben", type="password")
            submitted = st.form_submit_button("Einloggen")
            if submitted:
                if hash_password(password) == correct_password:
                    st.session_state["auth_ok"] = True
                    st.success("✅ Bitte erneut einloggen")
                else:
                    st.error("❌ Falsches Passwort")
                    st.stop()
        st.stop()

check_password()

# Ladebildschirm nur beim allerersten Start zeigen
if "geladen" not in st.session_state:
   st.markdown("""
    <style>
    /* === Allgemeiner Dark Mode === */
    html, body, [data-testid="stApp"] {
        background-color: #1a1a1a;
        color: #ffffff;
        font-family: 'Segoe UI', sans-serif;
    }
    
    /* === Headline-Styling === */
    h1, h2, h3 {
        color: #CC0000;
        text-align: center;
    }
    
    /* === Kompakte Upload-Felder === */
    div[data-testid="stFileUploader"] > label {
        font-size: 0.8rem;
        padding-bottom: 0.25rem;
        margin-bottom: 0.25rem;
    }
    
    section[data-testid="stFileUploaderDropzone"] {
        padding: 0.2rem 0.5rem;
        background-color: #2a2a2a;
        border: 1px solid #444;
        border-radius: 6px;
        text-align: center;
    }
    
    div[data-testid="stFileUploader"] {
        margin-bottom: 0.25rem;
    }
    
    /* === Daten-Tabellen === */
    .stDataFrameContainer {
        border-radius: 10px;
        border: 1px solid #444;
    }
    
    /* === Tabs (modern und klar) === */
    div[data-baseweb="tabs"] {
        margin-top: 1rem;
    }
    
    button[data-baseweb="tab"] {
        font-size: 20px !important;
        padding: 12px 20px !important;
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
    
    /* === Header entfernen === */
    [data-testid="stHeader"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        height: 0px !important;
    }
    header, .st-emotion-cache-18ni7ap {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- Bestehende Verarbeitung (unverändert) ---
def lade_und_verarbeite_datei(uploaded_file):
    df = pd.DataFrame()
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".xlsx"):
                df = pd.read_excel(uploaded_file, engine="openpyxl")
            else:
                df = pd.read_csv(uploaded_file)

            # Spalten bereinigen
            df.columns = [col.strip() for col in df.columns]

            # --- Spalten-Mapping ---
            mapping = {
                "Baugruppe / Arbeitsgang": "Inhalt",
                "Std.": "Soll-Zeit",
                "Ebene": "Bauraum",
                "Datum \nStart (Berechnet)": "Datum",
                "Qualifikation": "Qualifikation",
                "Tag": "Tag"
            }

            df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})

            # Fehlende Spalten ergänzen
            erwartete_spalten = ["Datum", "Tag", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum"]
            for col in erwartete_spalten:
                if col not in df.columns:
                    df[col] = ""

            # --- Zeitspalte in Stunden ---
            df["Soll-Zeit"] = df["Soll-Zeit"].astype(str).str.replace(r"[^\d,\.]", "", regex=True).str.replace(",", ".", regex=False)
            df["Stunden"] = pd.to_numeric(df["Soll-Zeit"], errors="coerce")
            df = df[df["Stunden"].notna()]

            # --- Takt falls leer auf 1 setzen ---
            if "Takt" not in df.columns or df["Takt"].nunique() <= 1:
                df["Takt"] = 1

            # --- Datum in datetime und Uhrzeiten setzen ---
            df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
            df = df[df["Datum"].notna()]
            df["Start"] = df["Datum"] + pd.to_timedelta(6, unit="h")
            df["Ende"] = df["Start"] + pd.to_timedelta(df["Stunden"], unit="h")

            # --- Sicherer Fallback falls "Tag" leer ---
            if df["Tag"].isnull().all() or df["Tag"].eq("").all():
                startdatum_ref = df["Datum"].min()
                df["Tag"] = (df["Datum"] - startdatum_ref).dt.days + 1

            # --- Kombispalte für spätere Filterung ---
            df["Tag_Takt"] = df["Tag"].astype(str) + "_T" + df["Takt"].astype(str)

        except Exception as e:
            st.error(f"Fehler beim Verarbeiten: {e}")
    return df

# ========= NEU: Mapping-Setup =========
CANONICALS = ["Datum", "Tag", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum"]
for key in ["EW1", "EW2", "MW1", "MW2"]:
    st.session_state.setdefault(f"df_{key}", pd.DataFrame())
    st.session_state.setdefault(f"map_{key}", {})
    st.session_state.setdefault(f"file_{key}", None)

DEFAULT_HINTS = {
    "Inhalt": ["Baugruppe / Arbeitsgang", "Arbeitsgang", "Inhalt"],
    "Soll-Zeit": ["Std.", "Stunden", "Soll-Zeit"],
    "Bauraum": ["Ebene", "Bauraum"],
    "Datum": ["Datum", "Datum \nStart (Berechnet)", "Startdatum"],
    "Qualifikation": ["Qualifikation", "Skill"],
    "Tag": ["Tag", "MAP-Tag", "Tag (MAP)"],
    "Takt": ["Takt", "Station", "Taktnummer"]
}

def propose_for(canon, cols):
    # 1) Heuristik
    for hint in DEFAULT_HINTS.get(canon, []):
        if hint in cols:
            return hint
    # 2) Fuzzy
    m = difflib.get_close_matches(canon, cols, n=1, cutoff=0.6)
    return m[0] if m else None

def _col_as_series(df: pd.DataFrame, name: str):
    """Konvertiert ggf. doppelte Spaltennamen zu einer Series (erste nicht-leere je Zeile)."""
    if name not in df.columns:
        return pd.Series([np.nan] * len(df), index=df.index)
    data = df.loc[:, df.columns == name]
    if isinstance(data, pd.Series):
        return data
    if data.shape[1] == 1:
        return data.iloc[:, 0]
    def pick_first_valid(row):
        for x in row:
            if pd.notna(x) and str(x).strip() != "":
                return x
        return np.nan
    return data.apply(pick_first_valid, axis=1)

def lade_und_verarbeite_datei_mit_mapping(uploaded_file, mapping_canonical_to_source: dict):
    """Wie deine bestehende Verarbeitung, aber mit manuellem Mapping (Dropdowns). Robust gegen doppelte Spalten."""
    df = pd.DataFrame()
    if uploaded_file is None:
        return df
    try:
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            df = pd.read_csv(uploaded_file)
        df.columns = [str(c).strip() for c in df.columns]

        # Nur gültige Zuordnungen
        valid_map = {canon: src for canon, src in mapping_canonical_to_source.items() if src in df.columns}
        # source->canonical umbenennen (kann Duplikate erzeugen)
        df = df.rename(columns={src: canon for canon, src in valid_map.items()})

        # Canonicals als einzelne Spalten herstellen
        out = pd.DataFrame(index=df.index)
        for c in CANONICALS:
            out[c] = _col_as_series(df, c)

        # Fehlende Canonicals auffüllen
        for c in CANONICALS:
            if c not in out.columns:
                out[c] = np.nan if c in ["Datum","Tag","Takt","Soll-Zeit"] else ""

        # Stunden parsen
        out["Soll-Zeit"] = out["Soll-Zeit"].astype(str).str.replace(r"[^\d,\.]", "", regex=True).str.replace(",", ".", regex=False)
        out["Stunden"] = pd.to_numeric(out["Soll-Zeit"], errors="coerce")
        out = out[out["Stunden"].notna()].copy()

        # Takt
        out["Takt"] = pd.to_numeric(out["Takt"], errors="coerce").fillna(1).astype(int)

        # Datum/Tag
        out["Datum"] = pd.to_datetime(out["Datum"], errors="coerce")
        if out["Tag"].isna().all():
            if out["Datum"].notna().any():
                startdatum_ref = out["Datum"].min()
                out["Tag"] = (out["Datum"] - startdatum_ref).dt.days + 1
            else:
                out["Tag"] = 1
        out["Tag"] = pd.to_numeric(out["Tag"], errors="coerce").fillna(1).astype(int)

        # Start/Ende
        if out["Datum"].notna().any():
            out["Start"] = out["Datum"] + pd.to_timedelta(6, unit="h")
            out["Ende"] = out["Start"] + pd.to_timedelta(out["Stunden"].clip(upper=8), unit="h")
        else:
            out["Start"] = pd.NaT
            out["Ende"] = pd.NaT

        out["Tag_Takt"] = out["Tag"].astype(str) + "_T" + out["Takt"].astype(str)
        return out.reset_index(drop=True)

    except Exception as e:
        st.error(f"Fehler beim Verarbeiten (Mapping): {e}")
        return pd.DataFrame()

# --- Logo und Titel anzeigen ---
def zeige_logo_und_titel():
    logo_path = Path("Logo_Targus.png")
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        logo_base64 = base64.b64encode(logo_bytes).decode()
        logo_html = f'''
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: 1rem;">
                <div style="flex: 1; min-width: 100px; display: flex; align-items: center;">
                    <img src="data:image/png;base64,{logo_base64}" style="max-height: 50px; height: auto; width: auto;">
                </div>
                <div style="flex: 2; text-align: center; min-width: 250px;">
                    <h1 style="margin: 0; font-size: 2rem; color: white;">
                        Takttool: Montage- & Personalplanung
                    </h1>
                </div>
                <div style="flex: 1;"></div>
            </div>
        '''
    else:
        logo_html = '''
            <div style="text-align: center; margin: 1rem;">
                <div style="width:60px; height:60px; background:#ccc; margin: auto;"></div>
                <h1 style="color: white;">Takttool: Montage- & Personalplanung</h1>
            </div>
        '''
    st.markdown(logo_html, unsafe_allow_html=True)

zeige_logo_und_titel()

# ==============================
# Tabs inkl. neuem "Einrichtung"
# ==============================
st.divider()
tab_setup, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Einrichtung",
    "Montageplanung EW1",
    "Montageplanung EW2",
    "Montageplanung MW1",
    "Montageplanung MW2",
    "Personalplanung"
])

# --- Tab Einrichtung: Upload + Dropdown-Mapping (ohne Visualisierung) ---
with tab_setup:
    st.markdown("## Einrichtung – Upload & Spalten-Mapping")
    st.caption("Lade je Plan die Datei hoch und ordne die Quellspalten den erwarteten Spalten zu. Nutze 'Auto-Vorschlag' für eine schnelle Vorbelegung.")

    def mapping_ui(plan_key: str, title: str):
        st.subheader(title)
        up = st.file_uploader(f"Datei für {plan_key} (CSV/XLSX)", type=["csv", "xlsx"], key=f"uploader_{plan_key}")

        # Datei laden & Spalten erkennen
        if up is not None:
            st.session_state[f"file_{plan_key}"] = up
            try:
                df_prev = pd.read_excel(up, engine="openpyxl") if up.name.lower().endswith(".xlsx") else pd.read_csv(up)
                df_prev.columns = [str(c).strip() for c in df_prev.columns]
            except Exception as e:
                st.error(f"Vorschau fehlgeschlagen: {e}")
                df_prev = pd.DataFrame()
        else:
            df_prev = pd.DataFrame()

        cols = list(df_prev.columns)
        if not cols:
            st.info("Bitte eine Datei hochladen, um Spalten zu erkennen.")
            return

        with st.expander("Gefundene Spalten (Quelle)", expanded=False):
            st.write(pd.DataFrame({"Quelle": cols}))

        current_map = st.session_state.get(f"map_{plan_key}", {})
        options = ["— nicht zuordnen —"] + cols

        c1, c2 = st.columns([1,1])
        with c1:
            if st.button("Auto-Vorschlag", key=f"auto_{plan_key}"):
                auto_map = {}
                for canon in CANONICALS:
                    guess = current_map.get(canon) or propose_for(canon, cols)
                    auto_map[canon] = guess
                st.session_state[f"map_{plan_key}"] = auto_map
                current_map = auto_map
        with c2:
            if st.button("Zurücksetzen", key=f"reset_{plan_key}"):
                st.session_state[f"map_{plan_key}"] = {}
                current_map = {}

        # Dropdowns (Erwartet -> Quelle)
        new_map = {}
        left, right = st.columns(2)
        with left:
            st.markdown("**Erwartet (Canonical)**")
            for canon in CANONICALS:
                st.markdown(f"- {canon}")
        with right:
            st.markdown("**Zuordnen aus Quelle**")
            for canon in CANONICALS:
                default = current_map.get(canon) or propose_for(canon, cols) or "— nicht zuordnen —"
                sel = st.selectbox(
                    f"{canon}",
                    options,
                    index=options.index(default) if default in options else 0,
                    key=f"map_{plan_key}_{canon}"
                )
                new_map[canon] = None if sel == "— nicht zuordnen —" else sel

        # Duplicate-Check (jede Quelle nur 1x)
        used = [s for s in new_map.values() if s]
        duplicates = {x for x in used if used.count(x) > 1}
        if duplicates:
            st.error("Konflikt: mehrfach zugeordnet → " + ", ".join(sorted(duplicates)))

        # Übernehmen
        if st.button(f"Übernehmen für {plan_key}", key=f"apply_{plan_key}"):
            if st.session_state.get(f"file_{plan_key}") is None:
                st.error("Bitte zuerst eine Datei hochladen.")
            elif duplicates:
                st.error("Bitte Konflikte lösen (jede Quellspalte nur einmal verwenden).")
            else:
                final_map = {canon: src for canon, src in new_map.items() if src}
                df_proc = lade_und_verarbeite_datei_mit_mapping(st.session_state[f"file_{plan_key}"], final_map)
                st.session_state[f"map_{plan_key}"] = new_map
                st.session_state[f"df_{plan_key}"] = df_proc
                if not df_proc.empty:
                    st.success(f"✅ {plan_key}: verarbeitet & gespeichert ({len(df_proc)} Zeilen).")
                    st.rerun()
                else:
                    st.warning(f"{plan_key}: Keine verwertbaren Daten nach Verarbeitung.")

    with st.expander("EW1", expanded=True):
        mapping_ui("EW1", "EW1")
    with st.expander("EW2", expanded=False):
        mapping_ui("EW2", "EW2")
    with st.expander("MW1", expanded=False):
        mapping_ui("MW1", "MW1")
    with st.expander("MW2", expanded=False):
        mapping_ui("MW2", "MW2")

    st.info("Nach 'Übernehmen' verwenden die Montage-Tabs und die Personalplanung automatisch die gemappten Daten aus diesem Tab.")

# --- Daten aus Einrichtung ---
df_ew1 = st.session_state["df_EW1"]
df_ew2 = st.session_state["df_EW2"]
df_mw1 = st.session_state["df_MW1"]
df_mw2 = st.session_state["df_MW2"]

# --- Sicherheitsnetz für fehlende Spalten ---
minimale_spalten = ["Tag (MAP)", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum", "Stunden", "Tag_Takt", "Datum_Start"]

def ergänze_fehlende_spalten(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=minimale_spalten)
    for spalte in minimale_spalten:
        if spalte not in df.columns:
            df[spalte] = ""
    return df

df_ew1 = ergänze_fehlende_spalten(df_ew1)
df_ew2 = ergänze_fehlende_spalten(df_ew2)
df_mw1 = ergänze_fehlende_spalten(df_mw1)
df_mw2 = ergänze_fehlende_spalten(df_mw2)

# --- Dynamischer Balkenplot mit Ø-Linie, die auf Legend-Klicks reagiert ---
def bar_with_mean_dynamic(df_plot, x, y, color, title, height=300, key="plot"):
    """
    Gestapelter Balkenplot (px.bar) + dynamische Ø-Linie, die sich bei Legend-Klicks
    auf Basis der *sichtbaren* Spuren neu berechnet.
    """
    fig = px.bar(
        df_plot, x=x, y=y, color=color,
        barmode="stack", title=title, height=height
    )
    fig.update_layout(
        plot_bgcolor="#1a1a1a",
        paper_bgcolor="#1a1a1a",
        font_color="#ffffff",
        legend_title_text=None
    )

    fig_spec = json.dumps(fig.to_plotly_json())

    html = f"""
<div id="plot-{key}" style="width:100%;height:{height+120}px;"></div>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<script>
const fig = {fig_spec};
const el = document.getElementById("plot-{key}");

function numericSort(a,b){{
  const na = Number(a), nb = Number(b);
  const aNum = !isNaN(na), bNum = !isNaN(nb);
  if (aNum && bNum) return na - nb;
  return String(a).localeCompare(String(b), 'de', {{numeric:true}});
}}

function computeMeanFromVisible(gd){{
  const sums = {{}};
  const xsSet = new Set();
  (gd.data || []).forEach(tr => {{
    if (tr.type !== 'bar') return;
    const visible = (tr.visible === undefined || tr.visible === true);
    if (!visible) return;
    const X = tr.x || [], Y = tr.y || [];
    for (let i=0;i<X.length;i++) {{
      const xv = X[i];
      const yv = Number(Y[i]) || 0;
      sums[xv] = (sums[xv] || 0) + yv;
      xsSet.add(xv);
    }}
  }});
  const xs = Array.from(xsSet).sort(numericSort);
  const vals = xs.map(x => sums[x] || 0);
  const mean = vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : 0;
  return {{ xs, mean }};
}}

function upsertMean(gd){{
  const {{ xs, mean }} = computeMeanFromVisible(gd);
  const lineX = xs;
  const lineY = xs.map(() => mean);

  // Trace für Ø finden oder anlegen
  let idx = (gd.data || []).findIndex(t => t.type==='scatter' && t.name==='Ø sichtbar');
  const meanTrace = {{
    x: lineX, y: lineY, mode: 'lines', type: 'scatter', name: 'Ø sichtbar',
    line: {{ dash:'dash', width:2 }}
  }};
  if (idx === -1){{
    Plotly.addTraces(gd, [meanTrace]).then(() => {{
      annotate(gd, xs, mean);
    }});
  }} else {{
    Plotly.restyle(gd, {{ x:[lineX], y:[lineY] }}, [idx]).then(() => {{
      annotate(gd, xs, mean);
    }});
  }}
}}

function annotate(gd, xs, mean){{
  const ann = {{
    x: xs.length ? xs[xs.length-1] : null,
    y: mean,
    xanchor:'left',
    yanchor:'bottom',
    showarrow:false,
    text:'Ø '+ (Math.round(mean*10)/10),
    font: {{ color:'#FFFFFF' }},
    _isMean:true
  }};
  const others = (gd.layout.annotations||[]).filter(a => !a._isMean);
  Plotly.relayout(gd, {{ annotations: [...others, ann] }});
}}

Plotly.newPlot(el, fig.data, fig.layout, {{responsive:true}}).then(gd => {{
  // initiale Ø-Linie
  upsertMean(gd);

  // bei Legend-Klicks / Restyles neu berechnen
  el.on('plotly_legendclick', () => {{ setTimeout(()=>upsertMean(el), 0); }});
  el.on('plotly_restyle',    () => {{ setTimeout(()=>upsertMean(el), 0); }});
}});
</script>
"""
    components.html(html, height=height+140)

# --- Feiertage definieren ---
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

# --- Tab 1: Montageplanung EW1 ---
with tab1:
    df = df_ew1

    st.markdown("#### Zeitraum wählen (nach Tag)")
    if df is not None and "Tag" in df.columns:
        tag_liste = sorted(pd.to_numeric(df["Tag"], errors="coerce").dropna().astype(int).unique())
    else:
        tag_liste = []
    if not tag_liste:
        st.warning("Keine gültigen Tag-Werte vorhanden.")
        st.stop()
    tag_min, tag_max = int(min(tag_liste)), int(max(tag_liste))

    tag_range = st.slider(
        "Tag auswählen",
        min_value=tag_min,
        max_value=tag_max,
        value=(tag_min, tag_max),
        key="tag_slider_ew1"
    )

    df["Tag"] = pd.to_numeric(df["Tag"], errors="coerce").fillna(tag_min).astype(int)
    df_filtered = df[df["Tag"].between(tag_range[0], tag_range[1])].copy()

    col_table, col_gantt = st.columns([1.2, 1.8])

    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="data_editor_ew1"
        )

        import io
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        st.download_button(
            label="⬇️ Geänderte Datei herunterladen",
            data=excel_buffer,
            file_name="Montageplanung_EW1_aktualisiert.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            st.session_state["df_ew1"] = df.copy()
            st.success("Änderungen gespeichert.")

    with col_gantt:
        if not df_filtered.empty:
            fig_gantt = px.timeline(
                df_filtered,
                x_start="Start",
                x_end="Ende",
                y="Inhalt",
                color="Qualifikation",
                title="Ablaufplanung (Gantt)",
                custom_data=["Tag", "Bauraum", "Stunden"]
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_traces(
                hovertemplate=(
                    "Tag: %{customdata[0]}<br>" +
                    "Bauraum: %{customdata[1]}<br>" +
                    "Stunden: %{customdata[2]}<br>" +
                    "Inhalt: %{y}<extra></extra>"
                )
            )
            fig_gantt.update_layout(
                xaxis_title="Datum",
                yaxis_title=None,
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff",
                height=600
            )
            st.plotly_chart(fig_gantt, use_container_width=True)
        else:
            st.info("Keine Daten für Gantt-Diagramm.")

    st.divider()

    if not df_filtered.empty:
        def gruppiere(df_in, field):
            return df_in.groupby(["Tag", field])["Stunden"].sum().reset_index()

        takte = sorted(pd.to_numeric(df_filtered["Takt"], errors="coerce").dropna().unique())
        bauraum_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Bauraum") for t in takte]
        quali_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Qualifikation") for t in takte]
        titel_map = [f"Takt {int(t)}" for t in takte]

        col_bauraum, col_quali = st.columns(2)

        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Bauraum",
                    title=titel_map[i],
                    height=300,
                    key=f"ew1_bauraum_{i}"
                )

        with col_quali:
            st.markdown("### Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Qualifikation",
                    title=titel_map[i],
                    height=300,
                    key=f"ew1_quali_{i}"
                )
    else:
        st.info("Keine Daten für Statistiken vorhanden.")

# --- Tab 2: Montageplanung EW2 ---
with tab2:
    df = df_ew2

    st.markdown("#### Zeitraum wählen (nach Tag)")
    if "Tag" not in df.columns or pd.to_numeric(df["Tag"], errors="coerce").isna().all():
        st.warning("Keine gültigen Tag-Werte für EW2 verfügbar.")
        st.stop()

    tag_liste = sorted(pd.to_numeric(df["Tag"], errors="coerce").dropna().astype(int).unique())
    idx_min, idx_max = int(min(tag_liste)), int(max(tag_liste))

    tag_range = st.slider(
        "Tag auswählen",
        min_value=idx_min,
        max_value=idx_max,
        value=(idx_min, idx_max),
        key="tag_slider_ew2"
    )

    df["Tag"] = pd.to_numeric(df["Tag"], errors="coerce").fillna(idx_min).astype(int)
    df_filtered = df[df["Tag"].between(tag_range[0], tag_range[1])].copy()

    col_table, col_gantt = st.columns([1.2, 1.8])

    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="data_editor_ew2"
        )

        import io
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        st.download_button(
            label="⬇️ Geänderte Datei herunterladen",
            data=excel_buffer,
            file_name="Montageplanung_EW2_aktualisiert.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            st.session_state["df_ew2"] = df.copy()
            st.success("Änderungen gespeichert.")

    with col_gantt:
        if not df_filtered.empty:
            df_filtered["Start"] = pd.to_datetime(df_filtered["Datum"], errors="coerce") + pd.to_timedelta(6, unit='h')
            df_filtered["Ende"] = df_filtered["Start"] + pd.to_timedelta(
                df_filtered["Stunden"].where(df_filtered["Stunden"] < 8, 8), unit="h"
            )

            fig_gantt = px.timeline(
                df_filtered,
                x_start="Start",
                x_end="Ende",
                y="Inhalt",
                color="Qualifikation",
                title="Ablaufplanung EW2",
                custom_data=["Tag", "Bauraum", "Stunden"],
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_traces(
                hovertemplate=(
                    "Tag: %{customdata[0]}<br>" +
                    "Bauraum: %{customdata[1]}<br>" +
                    "Stunden: %{customdata[2]}<br>" +
                    "Inhalt: %{y}<extra></extra>"
                ),
                selector=dict(type="bar")
            )
            fig_gantt.update_layout(
                xaxis_title="Datum",
                yaxis_title=None,
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff",
                height=600
            )
            st.plotly_chart(fig_gantt, use_container_width=True, key="gantt_ew2")
        else:
            st.info("Keine Daten für Gantt-Diagramm.")

    st.divider()

    if not df_filtered.empty:
        def gruppiere(df_in, group_field):
            return df_in.groupby(["Tag", group_field])["Stunden"].sum().reset_index()

    takte = sorted(pd.to_numeric(df_filtered["Takt"], errors="coerce").dropna().unique()) if not df_filtered.empty else []
    if takte:
        bauraum_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Bauraum") for t in takte]
        quali_data   = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Qualifikation") for t in takte]
        titel_map    = [f"Takt {int(t)}" for t in takte]

        col_bauraum, col_qualifikation = st.columns(2)

        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Bauraum",
                    title=titel_map[i],
                    height=300,
                    key=f"ew2_bauraum_{i}"
                )

        with col_qualifikation:
            st.markdown("### Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Qualifikation",
                    title=titel_map[i],
                    height=300,
                    key=f"ew2_quali_{i}"
                )
    else:
        st.info("Keine Daten für Statistiken vorhanden.")

# --- Tab 3: Montageplanung MW1 ---
with tab3:
    df = df_mw1

    st.markdown("#### Zeitraum wählen (nach Tag)")
    if "Tag" not in df.columns or pd.to_numeric(df["Tag"], errors="coerce").isna().all():
        st.warning("Keine gültigen Tag-Werte für MW1 verfügbar.")
        st.stop()

    tag_liste = sorted(pd.to_numeric(df["Tag"], errors="coerce").dropna().astype(int).unique())
    idx_min, idx_max = int(min(tag_liste)), int(max(tag_liste))

    tag_range = st.slider(
        "Tag auswählen",
        min_value=idx_min,
        max_value=idx_max,
        value=(idx_min, idx_max),
        key="tag_slider_mw1"
    )

    df["Tag"] = pd.to_numeric(df["Tag"], errors="coerce").fillna(idx_min).astype(int)
    df_filtered = df[df["Tag"].between(tag_range[0], tag_range[1])].copy()

    col_table, col_gantt = st.columns([1.2, 1.8])

    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="data_editor_mw1"
        )

        import io
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        st.download_button(
            label="⬇️ Geänderte Datei herunterladen",
            data=excel_buffer,
            file_name="Montageplanung_MW1_aktualisiert.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            st.session_state["df_mw1"] = df.copy()
            st.success("Änderungen gespeichert.")

    with col_gantt:
        if not df_filtered.empty:
            df_filtered["Start"] = pd.to_datetime(df_filtered["Datum"], errors="coerce") + pd.to_timedelta(6, unit='h')
            df_filtered["Ende"] = df_filtered["Start"] + pd.to_timedelta(
                df_filtered["Stunden"].where(df_filtered["Stunden"] < 8, 8), unit="h"
            )

            fig_gantt = px.timeline(
                df_filtered,
                x_start="Start",
                x_end="Ende",
                y="Inhalt",
                color="Qualifikation",
                title="Ablaufplanung MW1",
                custom_data=["Tag", "Bauraum", "Stunden"],
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_traces(
                hovertemplate=(
                    "Tag: %{customdata[0]}<br>" +
                    "Bauraum: %{customdata[1]}<br>" +
                    "Stunden: %{customdata[2]}<br>" +
                    "Inhalt: %{y}<extra></extra>"
                ),
                selector=dict(type="bar")
            )
            fig_gantt.update_layout(
                xaxis_title="Datum",
                yaxis_title=None,
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff",
                height=600
            )
            st.plotly_chart(fig_gantt, use_container_width=True, key="gantt_mw1")
        else:
            st.info("Keine Daten für Gantt-Diagramm.")

    st.divider()

    if not df_filtered.empty:
        def gruppiere(df_in, group_field):
            return df_in.groupby(["Tag", group_field])["Stunden"].sum().reset_index()

    takte = sorted(pd.to_numeric(df_filtered["Takt"], errors="coerce").dropna().unique()) if not df_filtered.empty else []
    if takte:
        bauraum_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Bauraum") for t in takte]
        quali_data   = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Qualifikation") for t in takte]
        titel_map    = [f"Takt {int(t)}" for t in takte]

        col_bauraum, col_qualifikation = st.columns(2)

        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Bauraum",
                    title=titel_map[i],
                    height=300,
                    key=f"mw1_bauraum_{i}"
                )

        with col_qualifikation:
            st.markdown("### Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Qualifikation",
                    title=titel_map[i],
                    height=300,
                    key=f"mw1_quali_{i}"
                )
    else:
        st.info("Keine Daten für Statistiken vorhanden.")

# --- Tab 4: Montageplanung MW2 ---
with tab4:
    df = df_mw2

    st.markdown("#### Zeitraum wählen (nach Tag)")
    if "Tag" not in df.columns or pd.to_numeric(df["Tag"], errors="coerce").isna().all():
        st.warning("Keine gültigen Tag-Werte für MW2 verfügbar.")
        st.stop()

    tag_liste = sorted(pd.to_numeric(df["Tag"], errors="coerce").dropna().astype(int).unique())
    idx_min, idx_max = int(min(tag_liste)), int(max(tag_liste))

    tag_range = st.slider(
        "Tag auswählen",
        min_value=idx_min,
        max_value=idx_max,
        value=(idx_min, idx_max),
        key="tag_slider_mw2"
    )

    df["Tag"] = pd.to_numeric(df["Tag"], errors="coerce").fillna(idx_min).astype(int)
    df_filtered = df[df["Tag"].between(tag_range[0], tag_range[1])].copy()

    col_table, col_gantt = st.columns([1.2, 1.8])

    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="data_editor_mw2"
        )

        import io
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        st.download_button(
            label="⬇️ Geänderte Datei herunterladen",
            data=excel_buffer,
            file_name="Montageplanung_MW2_aktualisiert.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            st.session_state["df_mw2"] = df.copy()
            st.success("Änderungen gespeichert.")

    with col_gantt:
        if not df_filtered.empty:
            df_filtered["Start"] = pd.to_datetime(df_filtered["Datum"], errors="coerce") + pd.to_timedelta(6, unit='h')
            df_filtered["Ende"] = df_filtered["Start"] + pd.to_timedelta(
                df_filtered["Stunden"].where(df_filtered["Stunden"] < 8, 8), unit="h"
            )

            fig_gantt = px.timeline(
                df_filtered,
                x_start="Start",
                x_end="Ende",
                y="Inhalt",
                color="Qualifikation",
                title="Ablaufplanung MW2",
                custom_data=["Tag", "Bauraum", "Stunden"],
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_traces(
                hovertemplate=(
                    "Tag: %{customdata[0]}<br>" +
                    "Bauraum: %{customdata[1]}<br>" +
                    "Stunden: %{customdata[2]}<br>" +
                    "Inhalt: %{y}<extra></extra>"
                ),
                selector=dict(type="bar")
            )
            fig_gantt.update_layout(
                xaxis_title="Datum",
                yaxis_title=None,
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff",
                height=600
            )
            st.plotly_chart(fig_gantt, use_container_width=True, key="gantt_mw2")
        else:
            st.info("Keine Daten für Gantt-Diagramm.")

    st.divider()

    if not df_filtered.empty:
        def gruppiere(df_in, group_field):
            return df_in.groupby(["Tag", group_field])["Stunden"].sum().reset_index()

    takte = sorted(pd.to_numeric(df_filtered["Takt"], errors="coerce").dropna().unique()) if not df_filtered.empty else []
    if takte:
        bauraum_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Bauraum") for t in takte]
        quali_data   = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Qualifikation") for t in takte]
        titel_map    = [f"Takt {int(t)}" for t in takte]

        col_bauraum, col_qualifikation = st.columns(2)

        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Bauraum",
                    title=titel_map[i],
                    height=300,
                    key=f"mw2_bauraum_{i}"
                )

        with col_qualifikation:
            st.markdown("### Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                bar_with_mean_dynamic(
                    df_plot, x="Tag", y="Stunden",
                    color="Qualifikation",
                    title=titel_map[i],
                    height=300,
                    key=f"mw2_quali_{i}"
                )
    else:
        st.info("Keine Daten für Statistiken vorhanden.")

# --- Tab 5: Personalplanung ---
with tab5:
    # Dynamische Plan-Zuordnung je nach vorhandenen Daten aus Einrichtung
    plan_mapping = {}
    if df_ew1 is not None and not df_ew1.empty:
        plan_mapping["EW1"] = df_ew1
    if df_ew2 is not None and not df_ew2.empty:
        plan_mapping["EW2"] = df_ew2
    if df_mw1 is not None and not df_mw1.empty:
        plan_mapping["MW1"] = df_mw1
    if df_mw2 is not None and not df_mw2.empty:
        plan_mapping["MW2"] = df_mw2

    if not plan_mapping:
        st.warning("Bitte lade mindestens einen Montageplan im Tab 'Einrichtung' hoch und übernehme das Mapping.")
        st.stop()

    planungstage = st.radio("Personalplanung für 5 oder 7 Tage:", [5, 7], horizontal=True, key="planungstage_radio")

    if "fte_stunden" not in st.session_state:
        st.session_state["fte_stunden"] = 8

    fte_basis = st.number_input(
        "Wieviele Stunden arbeitet ein FTE pro Tag?",
        min_value=1,
        max_value=24,
        step=1,
        key="fte_stunden"
    )

    st.markdown("### Auswahl des Montageplans pro Wagenkasten")

    wagenkästen = [f"Wagenkasten {i}" for i in range(1, 13)]
    zugewiesene_pläne = {}

    plan_row = st.columns(len(wagenkästen))
    for i, wk in enumerate(wagenkästen):
        zugewiesene_pläne[wk] = plan_row[i].selectbox(
            f"{wk}",
            options=list(plan_mapping.keys()),
            key=f"plan_select_{wk}"
        )

    st.markdown("### Belegung der MAP-Tage über Checkbox-Matrix")

    tag_map_liste = list(range(1, 24))
    zuordnung = {tag_map: [] for tag_map in tag_map_liste}

    header_cols = st.columns([1] + [1] * len(wagenkästen))
    header_cols[0].markdown("**MAP-Tag**")
    for i, wk in enumerate(wagenkästen):
        header_cols[i + 1].markdown(f"**{wk}**")

    for tag_idx, tag_map in enumerate(tag_map_liste):
        cols = st.columns([1] + [1] * len(wagenkästen))
        cols[0].markdown(f"{tag_map}")

        for wk_idx, wk in enumerate(wagenkästen):
            key = f"wk{wk_idx}_tag{tag_map}"
            current_value = st.session_state.get(key, False)

            checkbox_clicked = cols[wk_idx + 1].checkbox("", value=current_value, key=key)

            if checkbox_clicked and not current_value:
                offset = planungstage // 2
                start = max(0, tag_idx - offset)
                end = min(len(tag_map_liste), tag_idx + offset + 1)
                for i in range(start, end):
                    st.session_state[f"wk{wk_idx}_tag{tag_map_liste[i]}"] = True
                st.rerun()

            if st.session_state.get(key, False):
                zuordnung[tag_map].append((wk_idx, wk))

    submitted = st.button("Berechne Personalbedarf")

    if submitted:
        fehler_wagen = []
        belegung_pro_wagen = {wk: 0 for wk in wagenkästen}

        for tag_map, einträge in zuordnung.items():
            for _, wk in einträge:
                belegung_pro_wagen[wk] += 1

        for wk, count in belegung_pro_wagen.items():
            if count != 0 and count != planungstage:
                fehler_wagen.append((wk, count))

        if fehler_wagen:
            fehltext = ", ".join([f"{wk} ({anzahl})" for wk, anzahl in fehler_wagen])
            st.error(f"Fehler: Die folgenden Wagenkästen haben nicht exakt {planungstage} Häkchen (oder null): {fehltext}")
            st.stop()

        df_gesamt = pd.DataFrame()

        belegte_tage = {
            f"Wagenkasten {i+1}": sorted([
                tag for tag, einträge in zuordnung.items()
                if any(w == f"Wagenkasten {i+1}" for _, w in einträge)
            ]) for i in range(12)
        }

        for wk in wagenkästen:
            if not belegte_tage[wk]:
                continue
            plan_name = zugewiesene_pläne[wk]
            df_source = plan_mapping[plan_name]
            for i, tag in enumerate(belegte_tage[wk]):
                df_part = df_source[df_source["Tag"] == tag].copy()
                if not df_part.empty:
                    df_part["Kalendertag"] = i + 1
                    df_gesamt = pd.concat([df_gesamt, df_part], ignore_index=True)

        if df_gesamt.empty:
            st.info("Keine Aufgaben für die gewählte Planung gefunden.")
        else:
            st.markdown("### Stundenbedarf pro Kalendertag")
            df_plot = df_gesamt.groupby(["Kalendertag", "Qualifikation"])["Stunden"].sum().reset_index()

            fig = px.bar(
                df_plot,
                x="Kalendertag",
                y="Stunden",
                color="Qualifikation",
                barmode="stack",
                title="Stundenbedarf pro Tag"
            )
            fig.update_layout(
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### FTE-Bedarf pro Kalendertag")
            df_fte = df_plot.copy()
            df_fte["FTE"] = df_fte["Stunden"] / fte_basis

            fig_fte = px.bar(
                df_fte,
                x="Kalendertag",
                y="FTE",
                color="Qualifikation",
                barmode="stack",
                title="FTE pro Tag",
                labels={"FTE": "FTE"}
            )
            fig_fte.update_layout(
                plot_bgcolor="#1a1a1a",
                paper_bgcolor="#1a1a1a",
                font_color="#ffffff"
            )
            st.plotly_chart(fig_fte, use_container_width=True)

            st.markdown("### Aufgerundete FTE je Tag & Qualifikation")
            df_rund = df_fte.copy()
            df_rund["Aufgerundete FTE"] = df_rund["FTE"].apply(np.ceil)
            df_rund = df_rund[["Kalendertag", "Qualifikation", "Aufgerundete FTE"]]
            df_rund.columns = ["Tag", "Qualifikation", "Aufgerundete FTE"]
            st.dataframe(df_rund)

            st.markdown("---")
            st.markdown("### Gesamtstunden & FTE je Qualifikation")
            gruppe = df_gesamt.groupby("Qualifikation")["Stunden"].sum().reset_index()
            gruppe["FTE"] = gruppe["Stunden"] / fte_basis
            st.dataframe(gruppe)

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
