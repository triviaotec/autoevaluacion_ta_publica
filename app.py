# -*- coding: utf-8 -*-
"""
Autoevaluacion Transparencia Activa · Versión para despliegue en la nube
-----------------------------------------------------------------------
• Orden de materias/ítems por ID (no alfabético)  
• Ponderaciones y % de cumplimiento ajustados  
• Validaciones: no permite guardar ítems incompletos  
• Exporta reporte Word con la plantilla «plantilla.docx» (mismo directorio)

© 2025 – Diego González
"""

from __future__ import annotations
import base64, json
from collections import defaultdict, namedtuple
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# ──────────────── Rutas relativas a este archivo ────────────────────────────
ROOT = Path(__file__).resolve().parent  # Directorio del script

P_ITEMS = ROOT / "estructura_materias_items.json"
P_ESP   = ROOT / "estructura_indicadores_especificos.json"
P_DOCX  = ROOT / "plantilla.docx"

# Logo: admite PNG o JPEG. Busca el primero que exista.
for _ext in (".png", ".jpeg", ".jpg"):
    _p = ROOT / f"TRIVIA{_ext}"
    if _p.exists():
        P_LOGO = _p
        break
else:
    P_LOGO = None

# ─────────────── Configuración de Streamlit & logo ──────────────────────────
st.set_page_config(page_title="Autoevaluación Transparencia Activa", layout="wide")

def _logo64(p: Path) -> str:
    """Devuelve la ruta data URI en base64 para el logo si existe (png o jpeg)."""
    if not p or not p.exists():
        return ""
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"

st.markdown(
    f"""
<style>
#MainMenu, header, footer{{visibility:hidden}}
#logo{{position:fixed;top:8px;right:18px;z-index:10}}
</style>
<div id="logo"><img src="{_logo64(P_LOGO)}" width="140"></div>
""",
    unsafe_allow_html=True,
)

_safe_rerun = lambda: (st.rerun if hasattr(st, "rerun") else st.experimental_rerun)()

# ──────────────── Carga y orden de la estructura ────────────────────────────
ITEMS = json.loads(P_ITEMS.read_text(encoding="utf-8"))

# Corrige un nombre mal digitado que aparece en algunos registros
df = pd.DataFrame(ITEMS)
df["Materia"] = df["Materia"].replace(
    "Actos y resoluciones que tengas efectos sobre terceros",
    "Actos y resoluciones con efectos sobre terceros",
)

ITEM_TO_MAT  = {r["Ítem"]: r["Materia"].strip() for r in ITEMS}
MAT_TO_ITEMS = defaultdict(list)
for r in ITEMS:
    MAT_TO_ITEMS[r["Materia"].strip()].append(r["Ítem"])

ORDER_MAT: list[str] = []
_seen = set()
for r in ITEMS:               # primera aparición = orden por ID ascendente
    m = r["Materia"].strip()
    if m not in _seen:
        ORDER_MAT.append(m); _seen.add(m)

# Pesos numéricos de las materias (descarta celdas con texto)
MAT_PESO = df.groupby("Materia")["Peso Materia (%)"].apply(lambda s: pd.to_numeric(s, errors="coerce").dropna().iloc[0] if not s.empty else pd.NA).to_dict()

# Indicadores específicos
IND_ESP = json.loads(P_ESP.read_text(encoding="utf-8"))

# ──────────────────────── Estado de sesión ──────────────────────────────────
ItemR = namedtuple("ItemR", "scenario gen spec")         # gen=(disp, act, comp)
st.session_state.setdefault("idx", 0)
st.session_state.setdefault("answers", {})

# ──────────────────────── Funciones auxiliares ──────────────────────────────
ESC_D = {
    1: "Organismo presenta sección con antecedentes",  
    2: "Organismo indica no tener antecedentes / no aplica",  
    3: "No se observa sección, pero no hay evidencia de infracción",  
    4: "No hay sección y hay evidencia de infracción",  
    5: "Sección/vínculo no funciona o no muestra datos",  
}

def _calcular():
    """Calcula los % de cumplimiento por materia e ítem."""
    it_sc = {}
    mat_sc = defaultdict(float)
    for it, ans in st.session_state.answers.items():
        mat = ITEM_TO_MAT[it]
        if ans.scenario == 1:  # solo estos aportan al puntaje
            disp, act, comp = ans.gen
            gen_pct = (disp + act + comp) / 3
            esp_pct = ans.spec.count("Sí") / len(ans.spec) if ans.spec else 1
            pct = gen_pct * esp_pct * 100
            it_sc[it] = pct
            mat_sc[mat] += pct * MAT_PESO.get(mat, 0) / 100
    glob = sum(mat_sc.values())
    return it_sc, mat_sc, glob

# ──────────────────────── Interfaz principal ────────────────────────────────
st.title("Autoevaluación de Transparencia Activa")

org_in  = st.sidebar.text_input("Nombre del organismo")
eval_in = st.sidebar.text_input("Nombre del evaluador(a)")

# -------- Navegación por ítems --------

if st.session_state.idx >= len(ITEMS):
    st.success("¡Evaluación completada! Revisa los resultados en la barra lateral.")
else:
    registro = ITEMS[st.session_state.idx]
    mat = registro["Materia"].strip()
    it  = registro["Ítem"].strip()
    peso= registro["Peso Ítem (%)"]

    st.subheader(f"{mat}")
    st.markdown(f"**Ítem:** {it}  |  **Peso:** {peso:.2f} %")

    # Escenario
    st.radio("Escenario", list(ESC_D.values()), key="scenario")

    # Indicadores generales
    st.markdown("### Indicadores generales")
    cols = st.columns(3)
    gen_resp = []
    for i, col in enumerate(cols):
        gen_resp.append(col.radio([
            "Sí", "No", "No Aplica"], key=f"gen_{i}", index=2))

    # Indicadores específicos
    esp = IND_ESP.get(f"{mat} || {it}", [])
    esp_resp = []
    if esp:
        st.markdown("### Indicadores específicos")
        for idx, pregunta in enumerate(esp):
            esp_resp.append(st.radio([
                "Sí", "No", "No Aplica"], key=f"esp_{idx}", index=2))

    # Guardar respuesta
    if st.button("Guardar ítem"):
        if "No" in gen_resp and st.session_state.scenario == 1:
            st.warning("No puedes marcar 'No' en los indicadores cuando el escenario es 1.")
        else:
            st.session_state.answers[it] = ItemR(
                scenario=list(ESC_D.keys())[list(ESC_D.values()).index(st.session_state.scenario)],
                gen=tuple(1 if r=="Sí" else 0 for r in gen_resp),
                spec=esp_resp,
            )
            st.session_state.idx += 1
            _safe_rerun()

# -------- Resultados --------

if st.sidebar.button("Calcular resultados"):
    st.session_state.it_sc, st.session_state.mat_sc, st.session_state.glob_sc = _calcular()
    st.sidebar.metric("Cumplimiento global", f"{st.session_state.glob_sc:.1f} %")

st.sidebar.markdown("---")

# -------- Exportar informe --------

def _export(mat_sc, item_sc, glob, infr, org, evalua):
    doc = Document(str(P_DOCX))
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Cm(2.5)
        s.left_margin = s.right_margin = Cm(2.0)

    p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    p.clear(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("REPORTE DE AUTOEVALUACIÓN DE TRANSPARENCIA ACTIVA").bold = True
    p.runs[0].font.size = Pt(16)

    doc.add_paragraph(f"Organismo: {org}")
    doc.add_paragraph(f"Fecha: {datetime.now():%d-%m-%Y}")
    doc.add_paragraph(f"Evaluador(a): {evalua}")
    doc.add_paragraph(f"Cumplimiento TA global observado: {glob:.1f} %")

    # Tabla resumen por materia
    doc.add_heading("Puntaje por materias", level=2)
    t = doc.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    hdr = t.rows[0].cells
    hdr[0].text = "Materia"; hdr[1].text = "% Cumplimiento"
    for m in ORDER_MAT:
        r = t.add_row().cells
        r[0].text = m
        r[1].text = f"{mat_sc.get(m, 0):.1f} %"

    # Incumplimientos
    doc.add_heading("Incumplimientos detectados", level=2)
    for m, its in infr.items():
        doc.add_paragraph(f"{m}").bold = True
        for it, lst in its.items():
            doc.add_paragraph(f"- {it}", style="List Bullet")
            for l in lst:
                doc.add_paragraph(f"  • {l}")

    name = f"Reporte_TA_{org}_{datetime.now():%Y%m%d}.docx"
    doc.save(ROOT / name)
    return name

if st.sidebar.button("Exportar Word") and org_in and eval_in:
    if "mat_sc" not in st.session_state:
        st.sidebar.warning("Calcula primero los resultados.")
    else:
        infr = defaultdict(lambda: defaultdict(list))
        for it, ans in st.session_state.answers.items():
            mat = ITEM_TO_MAT[it]
            if ans.scenario in (4, 5):
                infr[mat][it].append(ESC_D[ans.scenario])
            lista = IND_ESP.get(f"{mat} || {it}", [])
            for idx, val in enumerate(ans.spec):
                if val == "No" and idx < len(lista):
                    infr[mat][it].append(f"Indicador específico «{lista[idx]}» = No")

        fname = _export(
            st.session_state.mat_sc,
            st.session_state.it_sc,
            st.session_state.glob_sc,
            infr,
            org_in, eval_in
        )
        with open(ROOT / fname, "rb") as f:
            st.sidebar.download_button("📄 Descargar informe", f, file_name=fname)
        st.sidebar.success("Informe generado.")
