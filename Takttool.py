import streamlit as st
import hashlib
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import base64
import os
import sys
from pathlib import Path
import difflib

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

# --- Styles (Dark) ---
st.markdown("""
    <style>
    html, body, [data-testid="stApp"] { background-color: #1a1a1a; color: #ffffff; font-family: 'Segoe UI', sans-serif; }
    h1, h2, h3 { color: #CC0000; text-align: center; }
    div[data-testid="stFileUploader"] > label { font-size: 0.8rem; padding-bottom: 0.25rem; margin-bottom: 0.25rem; }
    section[data-testid="stFileUploaderDropzone"] { padding: 0.2rem 0.5rem; background-color: #2a2a2a; border: 1px solid #444; border-radius: 6px; text-align: center; }
    div[data-testid="stFileUploader"] { margin-bottom: 0.25rem; }
    .stDataFrameContainer { border-radius: 10px; border: 1px solid #444; }
    div[data-baseweb="tabs"] { margin-top: 1rem; }
    button[data-baseweb="tab"] { font-size: 20px !important; padding: 12px 20px !important; margin: 0 !important; height: auto !important; border-radius: 0 !important; border: none !important; background-color: #2a2a2a !important; color: #ddd !important; transition: background-color 0.3s ease; }
    button[data-baseweb="tab"][aria-selected="true"] { background-color: #CC0000 !important; color: white !important; font-weight: bold; }
    button[data-baseweb="tab"] + button[data-baseweb="tab"] { border-left: 1px solid #1a1a1a; }
    [data-testid="stHeader"] { background: transparent !important; border: none !important; box-shadow: none !important; height: 0px !important; }
    header, .st-emotion-cache-18ni7ap { background: transparent !important; border: none !important; box-shadow: none !important; }
    </style>
""", unsafe_allow_html=True)

# --- Canonicals & Session Defaults ---
CANONICALS = ["Datum", "Tag", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum"]
DEFAULT_PLAN_TYPES = ["EW1", "EW2", "MW1", "MW2"]

if "plan_types" not in st.session_state:
    st.session_state["plan_types"] = DEFAULT_PLAN_TYPES.copy()

if "num_wagen" not in st.session_state:
    st.session_state["num_wagen"] = 12

# ensure per-plan session objects exist
for key in st.session_state["plan_types"]:
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
    for hint in DEFAULT_HINTS.get(canon, []):
        if hint in cols:
            return hint
    m = difflib.get_close_matches(canon, cols, n=1, cutoff=0.6)
    return m[0] if m else None

def _col_as_series(df: pd.DataFrame, name: str):
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
    df = pd.DataFrame()
    if uploaded_file is None:
        return df
    try:
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            df = pd.read_csv(uploaded_file)
        df.columns = [str(c).strip() for c in df.columns]

        valid_map = {canon: src for canon, src in mapping_canonical_to_source.items() if src in df.columns}
        df = df.rename(columns={src: canon for canon, src in valid_map.items()})

        out = pd.DataFrame(index=df.index)
        for c in CANONICALS:
            out[c] = _col_as_series(df, c)

        for c in CANONICALS:
            if c not in out.columns:
                out[c] = np.nan if c in ["Datum", "Tag", "Takt", "Soll-Zeit"] else ""

        out["Soll-Zeit"] = out["Soll-Zeit"].astype(str).str.replace(r"[^\d,\.]", "", regex=True).str.replace(",", ".", regex=False)
        out["Stunden"] = pd.to_numeric(out["Soll-Zeit"], errors="coerce")
        out = out[out["Stunden"].notna()].copy()

        out["Takt"] = pd.to_numeric(out["Takt"], errors="coerce").fillna(1).astype(int)

        out["Datum"] = pd.to_datetime(out["Datum"], errors="coerce")
        if out["Tag"].isna().all():
            if out["Datum"].notna().any():
                startdatum_ref = out["Datum"].min()
                out["Tag"] = (out["Datum"] - startdatum_ref).dt.days + 1
            else:
                out["Tag"] = 1
        out["Tag"] = pd.to_numeric(out["Tag"], errors="coerce").fillna(1).astype(int)

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

def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Sicherheitsnetz – stelle alle erwarteten Spalten bereit."""
    need = ["Datum", "Tag", "Takt", "Soll-Zeit", "Qualifikation", "Inhalt", "Bauraum",
            "Stunden", "Start", "Ende", "Tag_Takt"]
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame({c: [] for c in need})
    for c in need:
        if c not in df.columns:
            df[c] = np.nan if c in ["Datum","Tag","Takt","Soll-Zeit","Stunden"] else ""
    return df

# --- Logo & Titel ---
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
                    <h1 style="margin: 0; font-size: 2rem; color: white;">Takttool: Montage- & Personalplanung</h1>
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

# --- Plot Helper ---
def bar_with_mean(df_plot, x, y, color, title, height=300):
    fig = px.bar(df_plot, x=x, y=y, color=color, barmode="stack", title=title, height=height)
    try:
        mean_val = df_plot.groupby(x)[y].sum().mean()
        xs = sorted(pd.Series(df_plot[x]).dropna().unique())
        if len(xs) > 0 and pd.notna(mean_val):
            fig.add_trace(go.Scatter(
                x=xs, y=[mean_val] * len(xs), mode="lines", name="Ø pro Tag",
                line=dict(dash="dash", width=2),
                hovertemplate=f"Ø: {mean_val:.2f}<extra></extra>"
            ))
            fig.add_annotation(
                x=xs[-1], y=mean_val, text=f"Ø {mean_val:.1f}",
                showarrow=False, xanchor="left", yanchor="bottom", font=dict(color="#FFFFFF")
            )
    except Exception:
        pass
    fig.update_layout(plot_bgcolor="#1a1a1a", paper_bgcolor="#1a1a1a", font_color="#ffffff", legend_title_text=None)
    return fig

# --- Montage-Tab Renderer (dynamisch für jeden Plan-Typ) ---
def render_montage_tab(df: pd.DataFrame, plan_label: str, slider_key: str, editor_key: str, gantt_key: str, bauraum_prefix: str, quali_prefix: str):
    df = ensure_columns(df)
    st.markdown("#### Zeitraum wählen (nach Tag)")
    tag_vals = pd.to_numeric(df["Tag"], errors="coerce").dropna().astype(int)
    if tag_vals.empty:
        st.warning(f"Keine gültigen Tag-Werte für {plan_label} verfügbar.")
        return
    tag_min, tag_max = int(tag_vals.min()), int(tag_vals.max())
    tag_range = st.slider("Tag auswählen", min_value=tag_min, max_value=tag_max, value=(tag_min, tag_max), key=slider_key)

    df["Tag"] = pd.to_numeric(df["Tag"], errors="coerce").fillna(tag_min).astype(int)
    df_filtered = df[df["Tag"].between(tag_range[0], tag_range[1])].copy()

    col_table, col_gantt = st.columns([1.2, 1.8])
    with col_table:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        edited_df = st.data_editor(df_filtered, use_container_width=True, num_rows="dynamic", hide_index=True, key=editor_key)

        import io
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)
        st.download_button(
            label="⬇️ Geänderte Datei herunterladen",
            data=excel_buffer,
            file_name=f"Montageplanung_{plan_label}_aktualisiert.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if not edited_df.equals(df_filtered):
            df.update(edited_df)
            st.session_state[f"df_{plan_label}"] = df.copy()
            st.success("Änderungen gespeichert.")

    with col_gantt:
        if not df_filtered.empty:
            # Falls Start/Ende fehlen -> sicherstellen
            if "Start" not in df_filtered.columns or "Ende" not in df_filtered.columns or df_filtered["Start"].isna().all():
                df_filtered["Start"] = pd.to_datetime(df_filtered["Datum"], errors="coerce") + pd.to_timedelta(6, unit="h")
                df_filtered["Ende"] = df_filtered["Start"] + pd.to_timedelta(df_filtered["Stunden"].clip(upper=8), unit="h")
            fig_gantt = px.timeline(
                df_filtered, x_start="Start", x_end="Ende", y="Inhalt", color="Qualifikation",
                title=f"Ablaufplanung {plan_label}",
                custom_data=["Tag", "Bauraum", "Stunden"]
            )
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_traces(
                hovertemplate=("Tag: %{customdata[0]}<br>Bauraum: %{customdata[1]}<br>Stunden: %{customdata[2]}<br>Inhalt: %{y}<extra></extra>")
            )
            fig_gantt.update_layout(xaxis_title="Datum", yaxis_title=None, plot_bgcolor="#1a1a1a", paper_bgcolor="#1a1a1a", font_color="#ffffff", height=600)
            st.plotly_chart(fig_gantt, use_container_width=True, key=gantt_key)
        else:
            st.info("Keine Daten für Gantt-Diagramm.")

    st.divider()

    if not df_filtered.empty:
        def gruppiere(df_in, group_field):
            return df_in.groupby(["Tag", group_field])["Stunden"].sum().reset_index()

        takte = sorted(pd.to_numeric(df_filtered["Takt"], errors="coerce").dropna().unique())
        bauraum_data = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Bauraum") for t in takte]
        quali_data   = [gruppiere(df_filtered[df_filtered["Takt"] == t], "Qualifikation") for t in takte]
        titel_map    = [f"Takt {int(t)}" for t in takte]

        col_bauraum, col_qualifikation = st.columns(2)
        with col_bauraum:
            st.markdown("### Stunden nach Bauraum")
            for i, df_plot in enumerate(bauraum_data):
                fig = bar_with_mean(df_plot, x="Tag", y="Stunden", color="Bauraum", title=titel_map[i], height=300)
                st.plotly_chart(fig, use_container_width=True, key=f"{bauraum_prefix}_{i}")
        with col_qualifikation:
            st.markdown("### Stunden nach Qualifikation")
            for i, df_plot in enumerate(quali_data):
                fig = bar_with_mean(df_plot, x="Tag", y="Stunden", color="Qualifikation", title=titel_map[i], height=300)
                st.plotly_chart(fig, use_container_width=True, key=f"{quali_prefix}_{i}")
    else:
        st.info("Keine Daten für Statistiken vorhanden.")

# ==============================
# Tabs (dynamisch)
# ==============================
labels = ["Einrichtung"] + [f"Montageplanung {p}" for p in st.session_state["plan_types"]] + ["Personalplanung"]
tabs = st.tabs(labels)
tab_setup = tabs[0]
tab_personal = tabs[-1]
montage_tabs = tabs[1:-1]  # aligns with plan_types order

# --- Einrichtung ---
with tab_setup:
    st.markdown("## Einrichtung – Upload & Spalten-Mapping")

    # Plan-Typen anpassen (dynamisch)
    st.markdown("### Plan-Typen")
    types_csv = st.text_input(
        "Plan-Typen (kommagetrennt):",
        value=", ".join(st.session_state["plan_types"]),
        help="Beispiel: EW1, EW2, MW1, MW2, MW3"
    )
    col_types_left, col_types_right = st.columns([1, 1])
    with col_types_left:
        if st.button("Plan-Typen übernehmen"):
            new_types = [t.strip() for t in types_csv.split(",") if t.strip() != ""]
            if not new_types:
                st.error("Mindestens ein Plan-Typ ist erforderlich.")
            else:
                st.session_state["plan_types"] = list(dict.fromkeys(new_types))  # unique, keep order
                # ensure session keys for new types
                for key in st.session_state["plan_types"]:
                    st.session_state.setdefault(f"df_{key}", pd.DataFrame())
                    st.session_state.setdefault(f"map_{key}", {})
                    st.session_state.setdefault(f"file_{key}", None)
                st.success("Plan-Typen aktualisiert. Seite wird neu aufgebaut…")
                st.rerun()

    st.markdown("---")
    st.caption("Lade je Plan die Datei hoch und ordne die Quellspalten den erwarteten Spalten zu. Nutze 'Auto-Vorschlag' für eine schnelle Vorbelegung.")

    def mapping_ui(plan_key: str, title: str):
        st.subheader(title)
        up = st.file_uploader(f"Datei für {plan_key} (CSV/XLSX)", type=["csv", "xlsx"], key=f"uploader_{plan_key}")

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

        c1, c2 = st.columns([1, 1])
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

        used = [s for s in new_map.values() if s]
        duplicates = {x for x in used if used.count(x) > 1}
        if duplicates:
            st.error("Konflikt: mehrfach zugeordnet → " + ", ".join(sorted(duplicates)))

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

    # Render Mapping UI expanders für alle Plan-Typen
    for pt in st.session_state["plan_types"]:
        with st.expander(pt, expanded=(pt == st.session_state["plan_types"][0])):
            mapping_ui(pt, pt)

    st.info("Nach 'Übernehmen' verwenden die Montage-Tabs und die Personalplanung automatisch die gemappten Daten aus diesem Tab.")

# --- Montage-Tabs dynamisch rendern ---
for tab_obj, plan_key in zip(montage_tabs, st.session_state["plan_types"]):
    with tab_obj:
        df_plan = ensure_columns(st.session_state.get(f"df_{plan_key}", pd.DataFrame()))
        render_montage_tab(
            df=df_plan,
            plan_label=plan_key,
            slider_key=f"tag_slider_{plan_key}",
            editor_key=f"data_editor_{plan_key}",
            gantt_key=f"gantt_{plan_key}",
            bauraum_prefix=f"bauraum_plot_{plan_key}",
            quali_prefix=f"quali_plot_{plan_key}"
        )

# --- Tab: Personalplanung (RELATIVE Ausrichtung + variable Blocklänge + variable Anzahl Wagenkästen) ---
with tab_personal:
    # Sammle verfügbare Pläne aus Einrichtung
    plan_mapping = {}
    for pt in st.session_state["plan_types"]:
        dfp = st.session_state.get(f"df_{pt}", pd.DataFrame())
        if dfp is not None and not dfp.empty:
            plan_mapping[pt] = ensure_columns(dfp)

    if not plan_mapping:
        st.warning("Bitte lade mindestens einen Montageplan im Tab 'Einrichtung' hoch und übernehme das Mapping.")
        st.stop()

    st.markdown("### Parameter")

    # Anzahl Wagenkästen variabel
    st.session_state["num_wagen"] = st.number_input(
        "Anzahl Wagenkästen",
        min_value=1, max_value=50, value=st.session_state["num_wagen"], step=1, help="Gilt für Auswahl & Matrix."
    )

    tag_map_liste = list(range(1, 24))
    max_block = len(tag_map_liste)
    blocklaenge = st.number_input(
        "Anzahl Tage pro Wagen (Blocklänge)",
        min_value=1, max_value=max_block, value=7, step=1, key="blocklaenge_var"
    )

    if "fte_stunden" not in st.session_state:
        st.session_state["fte_stunden"] = 8

    fte_basis = st.number_input(
        "Wieviele Stunden arbeitet ein FTE pro Tag?",
        min_value=1, max_value=24, step=1, key="fte_stunden"
    )

    st.markdown("### Auswahl des Montageplans pro Wagenkasten")

    wagen_count = int(st.session_state["num_wagen"])
    wagenkästen = [f"Wagenkasten {i}" for i in range(1, wagen_count + 1)]
    zugewiesene_pläne = {}

    plan_row = st.columns(len(wagenkästen))
    for i, wk in enumerate(wagenkästen):
        zugewiesene_pläne[wk] = plan_row[i].selectbox(
            f"{wk}",
            options=list(plan_mapping.keys()),
            key=f"plan_select_{wk}"
        )

    # Checkbox-Matrix im Form (kein Rerun pro Klick)
    with st.form("belegung_form", clear_on_submit=False):
        st.markdown("### Belegung der MAP-Tage über Checkbox-Matrix")
        header_cols = st.columns([1] + [1] * len(wagenkästen))
        header_cols[0].markdown("**MAP-Tag**")
        for i, wk in enumerate(wagenkästen):
            header_cols[i + 1].markdown(f"**{wk}**")

        for tag_map in tag_map_liste:
            cols = st.columns([1] + [1] * len(wagenkästen))
            cols[0].markdown(f"{tag_map}")
            for wk_idx, wk in enumerate(wagenkästen):
                key = f"wk{wk_idx}_tag{tag_map}"
                current_value = st.session_state.get(key, False)
                cols[wk_idx + 1].checkbox("", value=current_value, key=key)

        btn_autofill = st.form_submit_button("Block aus erstem Häkchen füllen")
        btn_berechne = st.form_submit_button("Berechne Personalbedarf")

    # Autofill: exakt Blocklänge ab erstem Haken je Wagen, rest löschen
    if btn_autofill:
        for wk_idx, wk in enumerate(wagenkästen):
            selected = [t for t in tag_map_liste if st.session_state.get(f"wk{wk_idx}_tag{t}", False)]
            if not selected:
                continue
            start = min(selected)
            end = min(tag_map_liste[-1], start + int(blocklaenge) - 1)
            for t in tag_map_liste:
                st.session_state[f"wk{wk_idx}_tag{t}"] = False
            for t in range(start, end + 1):
                st.session_state[f"wk{wk_idx}_tag{t}"] = True
        st.rerun()

    # Berechnung
    if btn_berechne:
        zuordnung = {tag_map: [] for tag_map in tag_map_liste}
        for wk_idx, wk in enumerate(wagenkästen):
            for tag_map in tag_map_liste:
                if st.session_state.get(f"wk{wk_idx}_tag{tag_map}", False):
                    zuordnung[tag_map].append((wk_idx, wk))

        # Sanity 1: genau 0 oder blocklaenge Häkchen pro Wagen
        fehler_wagen = []
        belegung_pro_wagen = {wk: 0 for wk in wagenkästen}
        for tag_map, einträge in zuordnung.items():
            for _, wk in einträge:
                belegung_pro_wagen[wk] += 1
        for wk, count in belegung_pro_wagen.items():
            if count != 0 and count != int(blocklaenge):
                fehler_wagen.append((wk, count))
        if fehler_wagen:
            fehltext = ", ".join([f"{wk} ({anzahl})" for wk, anzahl in fehler_wagen])
            st.error(f"Fehler: Die folgenden Wagenkästen haben nicht exakt {int(blocklaenge)} Häkchen (oder null): {fehltext}")
            st.stop()

        # Sanity 2: Kontiguität + Existenz im Plan
        tag_sets = {name: set(pd.to_numeric(df_src["Tag"], errors="coerce").dropna().astype(int).unique())
                    for name, df_src in plan_mapping.items() if df_src is not None}

        belegte_tage = {
            wk: sorted([tag for tag, einträge in zuordnung.items() if any(w == wk for _, w in einträge)])
            for wk in wagenkästen
        }

        check_rows, kontinuitäts_fehler, not_in_plan_fehler, mapping_rows = [], [], [], []

        for wk in wagenkästen:
            tags = belegte_tage[wk]
            if not tags:
                continue

            plan_name = zugewiesene_pläne[wk]
            tags_sorted = sorted(tags)
            anzahl = len(tags_sorted)
            ist_kontigu = (anzahl == int(blocklaenge)) and (tags_sorted == list(range(tags_sorted[0], tags_sorted[0] + int(blocklaenge))))
            fehlende = sorted([t for t in tags_sorted if t not in tag_sets.get(plan_name, set())])

            bereich_txt = f"{tags_sorted[0]}–{tags_sorted[-1]}" if anzahl > 0 else "-"
            check_rows.append({
                "Wagenkasten": wk,
                "Plan": plan_name,
                "Ausgewählter Bereich": bereich_txt,
                "Anz. Tage": anzahl,
                "Kontiguität OK": "✅" if ist_kontigu else "❌",
                "Fehlende Plan-Tage": ", ".join(map(str, fehlende)) if fehlende else ""
            })

            if not ist_kontigu:
                kontinuitäts_fehler.append(f"{wk} ({bereich_txt})")
            if fehlende:
                not_in_plan_fehler.append(f"{wk} → {plan_name}: {', '.join(map(str, fehlende))}")

            if ist_kontigu and not fehlende:
                for i_rel, t in enumerate(tags_sorted, start=1):
                    mapping_rows.append({
                        "Wagenkasten": wk,
                        "Plan": plan_name,
                        "RelativerTag": i_rel,
                        "Plan-Tag": t
                    })

        st.markdown("#### Sanity-Check Übersicht")
        st.dataframe(pd.DataFrame(check_rows))

        if kontinuitäts_fehler:
            st.error("Nicht zusammenhängende Bereiche gewählt bei: " + ", ".join(kontinuitäts_fehler))
        if not_in_plan_fehler:
            st.error("Ausgewählte Plan-Tage existieren nicht im zugewiesenen Plan:\n- " + "\n- ".join(not_in_plan_fehler))
        if kontinuitäts_fehler or not_in_plan_fehler:
            st.stop()

        if not mapping_rows:
            st.info("Keine validen Zuordnungen gefunden.")
            st.stop()

        df_align = pd.DataFrame(mapping_rows)
        with st.expander("Sanity-Check: Zuordnung (Wagenkasten → RelativerTag → Plan-Tag)", expanded=False):
            st.dataframe(df_align.sort_values(["RelativerTag", "Wagenkasten"]))

        # Daten aus Plänen ziehen & relativ taggen
        df_parts = []
        for _, row in df_align.iterrows():
            plan_name = row["Plan"]
            rtag = int(row["RelativerTag"])
            ptag = int(row["Plan-Tag"])
            wk = row["Wagenkasten"]
            df_src = plan_mapping[plan_name].copy()
            df_src["Tag"] = pd.to_numeric(df_src["Tag"], errors="coerce").astype("Int64")
            part = df_src[df_src["Tag"] == ptag].copy()
            if part.empty:
                continue
            part["RelativerTag"] = rtag
            part["Wagenkasten"] = wk
            df_parts.append(part)

        if not df_parts:
            st.info("Keine Aufgaben für die gewählte Planung gefunden.")
            st.stop()

        df_gesamt = pd.concat(df_parts, ignore_index=True)

        with st.expander("Sanity-Check: Beitrag je Wagenkasten×RelativerTag (Stunden gesamt)", expanded=False):
            pivot = (df_gesamt.groupby(["Wagenkasten", "RelativerTag"])["Stunden"]
                     .sum()
                     .unstack(fill_value=0)
                     .sort_index(axis=1))
            st.dataframe(pivot)

        # Plots & Kennzahlen (RELATIVE Tage)
        st.markdown("### Stundenbedarf pro Relativtag")
        df_plot = df_gesamt.groupby(["RelativerTag", "Qualifikation"])["Stunden"].sum().reset_index()
        fig = px.bar(df_plot, x="RelativerTag", y="Stunden", color="Qualifikation", barmode="stack",
                     title="Stundenbedarf pro Relativtag (parallel ausgerichtet)")
        fig.update_layout(plot_bgcolor="#1a1a1a", paper_bgcolor="#1a1a1a", font_color="#ffffff")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### FTE-Bedarf pro Relativtag")
        df_fte = df_plot.copy()
        df_fte["FTE"] = df_fte["Stunden"] / fte_basis
        fig_fte = px.bar(df_fte, x="RelativerTag", y="FTE", color="Qualifikation", barmode="stack",
                         title="FTE pro Relativtag", labels={"FTE": "FTE"})
        fig_fte.update_layout(plot_bgcolor="#1a1a1a", paper_bgcolor="#1a1a1a", font_color="#ffffff")
        st.plotly_chart(fig_fte, use_container_width=True)

        st.markdown("### Aufgerundete FTE je Relativtag & Qualifikation")
        df_rund = df_fte.copy()
        df_rund["Aufgerundete FTE"] = df_rund["FTE"].apply(np.ceil)
        df_rund = df_rund[["RelativerTag", "Qualifikation", "Aufgerundete FTE"]]
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
if __name__ == "__main__" and getattr(sys, 'frozen', False):
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:8501")
    except Exception as e:
        print(f"Fehler beim Öffnen des Browsers: {e}")
