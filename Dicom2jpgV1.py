# FileNameConvV10.1.py
# -------------------------------------------------------------
# Änderungen ggü. V9.1:
#   + Neue Prozedur: DicomTojpg()
#     - Öffnet .dcm (DICOM) Dateien mit pydicom
#     - Liest Patientendaten (Vorname, Nachname, Geburtsdatum, Seite OD/OS,
#       PatID, Untersuchungsdatum/-zeit, Untersuchungstyp)
#     - Konvertiert PixelData zu JPEG
#     - Speichert JPG als:
#       Vorname_Nachname_Geburtsdatum_Seite_Untersuchungstyp_Untersuchungsdatum_Untersuchungszeit_PatID.jpg
#     - Logging-Stil kompatibel: nutzt vorhandenen 'logger' & 'email_senden', falls im Projekt definiert;
#       ansonsten werden sinnvolle Defaults gesetzt.
#
# Abhängigkeiten (bereits in Ihrer venv vorhanden laut Vorgabe):
#   pip install pydicom Pillow numpy
#
# SMB-Ziel:
#   Wenn das Zielverzeichnis als smb://... angegeben ist, wird empfohlen,
#   den Share auf dem Synology/Host zu mounten und hier als normalen Pfad zu nutzen.
#   Optionaler Support via 'smbclient' (pip install smbprotocol) ist enthalten;
#   wenn das Paket fehlt, wird ein Hinweis geloggt.
# -------------------------------------------------------------

from __future__ import annotations

import os
import io
import sys
import logging
import datetime as dt
from typing import Optional, Tuple

# NumPy 1.24 bringt OpenBLAS mit. Auf diesem Mac läuft gemm_thread_n
# über den Thread-Stack hinaus und Python stirbt mit SIGSEGV beim Import.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("GOTO_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Optional: SMB-Unterstützung nur, wenn Ziel mit "smb://" beginnt
try:
    import smbclient  # pip install smbprotocol
    _HAS_SMBCLIENT = True
except Exception:
    _HAS_SMBCLIENT = False

# DICOM + Bild
import numpy as np
import pydicom
try:
    # pydicom 3.x
    from pydicom.pixels import apply_modality_lut, apply_voi_lut, convert_color_space
except ImportError:
    # pydicom 2.4–2.x
    from pydicom.pixel_data_handlers.util import (
        apply_modality_lut,
        apply_voi_lut,
        convert_color_space,
    )
from PIL import Image

# ------------------------------------------------------------------
# Logger / Mail: Übernahme aus bestehendem Projekt, sonst Defaults
# ------------------------------------------------------------------

logger: logging.Logger
if "logger" in globals() and isinstance(globals()["logger"], logging.Logger):
    logger = globals()["logger"]
else:
    logger = logging.getLogger("FileNameConvV10.1")
    logger.setLevel(logging.INFO)
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    if not logger.handlers:
        logger.addHandler(_h)

def _noop_email(_msg: str):  # Fallback, falls in V9.1 vorhanden: email_senden(msg)
    pass

email_senden = globals().get("email_senden", _noop_email)

# Standardpfade (können von außen überschrieben werden)
CIRRUS_BILDERGALERIE_OUT = globals().get(
    "CIRRUS_BILDERGALERIE_OUT",
    "smb://192.168.131.20/Team/OCTFiles/FilesForSimed/Cirrus_Bildergalerie"
)

# Optional: SMB Credentials per Umgebungsvariablen
SMB_SERVER   = os.environ.get("SMB_SERVER", "")    # z.B. 192.168.131.20
SMB_USERNAME = os.environ.get("SMB_USERNAME", "")
SMB_PASSWORD = os.environ.get("SMB_PASSWORD", "")
SMB_DOMAIN   = os.environ.get("SMB_DOMAIN", "")    # optional


# ------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------

def _safe_text(v) -> str:
    """Bereinigt Zeichenfolgen für Dateinamen."""
    if v is None:
        return ""
    s = str(v)
    for ch in r'\/:*?"<>|':
        s = s.replace(ch, "-")
    s = s.replace("^", " ").replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    return s.strip()

def _fmt_date_yyyymmdd(d: Optional[str]) -> str:
    """Formatiert DICOM-Datum (YYYYMMDD oder YYYY-MM-DD) als YYYYMMDD, Fallback heute."""
    if not d:
        return dt.datetime.now().strftime("%Y%m%d")
    donly = "".join(ch for ch in str(d) if ch.isdigit())
    if len(donly) >= 8:
        return donly[:8]
    return dt.datetime.now().strftime("%Y%m%d")

def _fmt_time_hhmmss(t: Optional[str]) -> str:
    """Formatiert DICOM-Zeit (HHMMSS.frac) als HHMMSS, Fallback aktuelle Zeit."""
    if not t:
        return dt.datetime.now().strftime("%H%M%S")
    tonly = "".join(ch for ch in str(t) if ch.isdigit())
    if len(tonly) >= 6:
        return tonly[:6]
    return (tonly + "000000")[:6]

def _fmt_date_or_empty(d: Optional[str]) -> str:
    """Formatiert ein DICOM-Datum als YYYYMMDD. Leer, wenn keins vorhanden ist."""
    if not d:
        return ""
    donly = "".join(ch for ch in str(d) if ch.isdigit())
    if len(donly) >= 8:
        return donly[:8]
    return ""

def _to_od_os(value) -> str:
    """Wandelt DICOM-Seite (R/L oder Text) in OD oder OS."""
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text in ("R", "RIGHT", "OD", "RECHTS"):
        return "OD"
    if text in ("L", "LEFT", "OS", "LINKS"):
        return "OS"
    tokens = [part for part in "".join(ch if ch.isalnum() else " " for ch in text).split() if part]
    if "OD" in tokens or "RIGHT" in tokens or "RECHTS" in tokens:
        return "OD"
    if "OS" in tokens or "LEFT" in tokens or "LINKS" in tokens:
        return "OS"
    return ""

def _extract_laterality(ds) -> str:
    """Liest die Augenseite. R wird OD, L wird OS."""
    keywords = ("ImageLaterality", "Laterality", "FrameLaterality")
    try:
        for elem in ds.iterall():
            if elem.keyword in keywords and elem.value not in (None, ""):
                side = _to_od_os(elem.value)
                if side:
                    return side
    except Exception:
        pass
    for attr in ("SeriesDescription", "StudyDescription", "ProtocolName", "ImageComments"):
        side = _to_od_os(getattr(ds, attr, ""))
        if side:
            return side
    return ""

def _extract_patient_names(pn) -> Tuple[str, str]:
    """Zerlegt PatientName in (Nachname, Vorname(n))."""
    try:
        family = getattr(pn, "family_name", None)
        given  = getattr(pn, "given_name", None)
        middle = getattr(pn, "middle_name", None)
        if family is None and given is None:
            # PN evtl. als einfache Zeichenkette mit '^' Trenner
            parts = str(pn).split("^")
            family = parts[0] if parts else str(pn)
            given = " ".join(parts[1:]) if len(parts) > 1 else ""
        if middle:
            given = (given + " " + middle).strip() if given else middle
        return _safe_text(family), _safe_text(given)
    except Exception:
        s = _safe_text(str(pn))
        parts = s.split()
        if len(parts) >= 2:
            return parts[-1], " ".join(parts[:-1])
        return s, ""

def _dicom_to_pil(ds: pydicom.dataset.FileDataset) -> Image.Image:
    """Konvertiert ein DICOM mit PixelData zu PIL.Image (8-bit L oder RGB)."""
    if "PixelData" not in ds:
        raise ValueError("DICOM enthält keine PixelData.")
    arr = ds.pixel_array
    photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)

    # JPEG-Fundus von Cirrus bleibt nach dem Dekodieren YBR_FULL_422.
    # Als RGB gespeichert wirkt das grün-violett statt orange.
    if samples == 3 and photometric in ("YBR_FULL", "YBR_FULL_422"):
        arr = convert_color_space(arr, photometric, "RGB")
        arr = np.clip(arr, 0, 255).astype("uint8")
        return Image.fromarray(arr, mode="RGB")

    if samples == 3:
        arr = np.clip(arr, 0, 255).astype("uint8")
        return Image.fromarray(arr, mode="RGB")

    # Graustufen: LUT und Spreizung auf 8 Bit
    try:
        arr = apply_modality_lut(arr, ds)
    except Exception:
        pass
    try:
        arr = apply_voi_lut(arr, ds)
    except Exception:
        pass

    if photometric == "MONOCHROME1":
        arr = arr.max() - arr

    arr = arr.astype("float32")
    min_v, max_v = float(arr.min()), float(arr.max())
    if max_v > min_v:
        arr = (arr - min_v) / (max_v - min_v) * 255.0
    arr = np.clip(arr, 0, 255).astype("uint8")
    return Image.fromarray(arr, mode="L")

def _ensure_local_dir(path: str) -> None:
    if path.startswith("smb://"):
        return
    os.makedirs(path, exist_ok=True)

def _write_bytes(dest_path: str, data: bytes) -> None:
    """Schreibt Bytes lokal oder (falls konfiguriert) via SMB."""
    if dest_path.startswith("smb://"):
        if not _HAS_SMBCLIENT:
            raise RuntimeError(
                "smbclient nicht verfügbar. Bitte Share mounten oder 'pip install smbprotocol' nutzen."
            )
        # Optionale Sessionregistrierung
        try:
            if SMB_SERVER and (SMB_USERNAME or SMB_PASSWORD):
                smbclient.register_session(
                    SMB_SERVER,
                    username=SMB_USERNAME or None,
                    password=SMB_PASSWORD or None,
                    port=445,
                )
        except Exception:
            # Falls anonymer Zugriff möglich ist, kann man es ohne Registrierung versuchen
            pass

        # Schreiben
        with smbclient.open_file(dest_path, mode="wb") as f:
            f.write(data)
    else:
        _ensure_local_dir(os.path.dirname(dest_path))
        with open(dest_path, "wb") as f:
            f.write(data)


# ------------------------------------------------------------------
# Hauptroutine: DicomTojpg
# ------------------------------------------------------------------

def DicomTojpg(dcm_path: str,
               out_dir: Optional[str] = None) -> Optional[str]:
    """
    Öffnet eine .dcm-Datei, liest Patientendaten und speichert das Bild als JPEG.

    Gelesene Variablen (werden intern in gleichnamigen Variablen gehalten):
      - vornamen (Vorname(n))
      - name (Nachname)
      - geburtsdatum (YYYYMMDD, PatientBirthDate)
      - seite (OD oder OS)
      - pat_id (Patienten-ID)
      - untersuchungsdatum (YYYYMMDD)
      - untersuchungszeit (HHMMSS)
      - untersuchungstyp

    Der Ziel-Dateiname lautet:
      Vorname_Nachname_Geburtsdatum_Seite_Untersuchungstyp_Untersuchungsdatum_Untersuchungszeit_PatID.jpg

    Rückgabe:
      Pfad/URL zur geschriebenen JPEG-Datei oder None bei Fehler.
    """
    try:
        dcm_path = os.path.abspath(dcm_path)
        logger.info("DicomTojpg gestartet: %s", dcm_path)

        ds = pydicom.dcmread(dcm_path, force=True)

        # --- Patientendaten extrahieren ---
        pn = getattr(ds, "PatientName", "")
        name, vornamen = _extract_patient_names(pn)

        pat_id = _safe_text(getattr(ds, "PatientID", ""))
        geburtsdatum = _fmt_date_or_empty(getattr(ds, "PatientBirthDate", None))
        seite = _extract_laterality(ds)
        if not geburtsdatum:
            logger.warning("Kein Geburtsdatum in %s", dcm_path)
        if not seite:
            logger.warning("Keine Augenseite (OD/OS) in %s", dcm_path)

        study_date = (getattr(ds, "StudyDate", None) or
                      getattr(ds, "AcquisitionDate", None) or
                      getattr(ds, "ContentDate", None))
        study_time = (getattr(ds, "StudyTime", None) or
                      getattr(ds, "AcquisitionTime", None) or
                      getattr(ds, "ContentTime", None))

        untersuchungsdatum = _fmt_date_yyyymmdd(study_date)
        untersuchungszeit  = _fmt_time_hhmmss(study_time)

        untersuchungstyp = (getattr(ds, "StudyDescription", None) or
                            getattr(ds, "SeriesDescription", None) or
                            getattr(ds, "Modality", "")) or "Unbekannt"
        untersuchungstyp = _safe_text(untersuchungstyp)

        # --- Bild erzeugen ---
        img = _dicom_to_pil(ds)

        # --- Dateiname nach Vorgabe ---
        parts = [
            vornamen, name, geburtsdatum, seite, untersuchungstyp,
            untersuchungsdatum, untersuchungszeit, pat_id
        ]
        base = "_".join([p for p in parts if p]).strip("_")
        filename = f"{base}.jpg"

        # --- Zielpfad bestimmen ---
        out_base = (out_dir or CIRRUS_BILDERGALERIE_OUT).rstrip("/")
        dest_path = (f"{out_base}/{filename}" if out_base.startswith("smb://")
                     else os.path.join(out_base, filename))

        # --- JPEG schreiben ---
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, optimize=True)
        _write_bytes(dest_path, buf.getvalue())

        logger.info("DicomTojpg erfolgreich: %s", dest_path)
        return dest_path

    except Exception as e:
        logger.error("Fehler in DicomTojpg für Datei %s", dcm_path, exc_info=True)
        try:
            email_senden(f"Fehler in DicomTojpg: {e}")
        except Exception:
            pass
        return None


# ------------------------------------------------------------------
# Optionaler CLI-Einstieg zum schnellen Testen
# Aufrufbeispiele:
#   python FileNameConvV10.1.py input.dcm
#   python FileNameConvV10.1.py /pfad/zu/dcms/ --out smb://server/share/Ziel
# ------------------------------------------------------------------
def _parse_args(argv: list[str]) -> tuple[list[str], Optional[str]]:
    inputs: list[str] = []
    out_dir: Optional[str] = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "-o") and i + 1 < len(argv):
            out_dir = argv[i + 1]
            i += 2
        else:
            inputs.append(a)
            i += 1
    return inputs, out_dir

def _expand_inputs(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(".dcm"):
                        out.append(os.path.join(root, f))
        else:
            out.append(p)
    return out

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        print("Verwendung: python FileNameConvV10.1.py <dcm_or_dir> [<dcm_or_dir> ...] [--out <zielpfad>]")
        sys.exit(0)
    paths, out_dir = _parse_args(argv)
    dcm_files = [p for p in _expand_inputs(paths) if p.lower().endswith(".dcm")]
    if not dcm_files:
        print("Keine .dcm Dateien gefunden.")
        sys.exit(0)

    ok, fail = 0, 0
    for fp in dcm_files:
        res = DicomTojpg(fp, out_dir=out_dir)
        if res:
            ok += 1
        else:
            fail += 1
    print(f"Fertig. Erfolgreich: {ok}, Fehler: {fail}")
