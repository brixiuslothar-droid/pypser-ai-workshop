# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Build the group's final presentation from workshop/presentation/deck.yaml.

Rules and slide plan: workshop/presentation/README.md; agent workflow: skill
``presentation`` (.claude/skills/presentation/SKILL.md).

- numbers come only from placeholders that are filled from the results
  pipeline (workshop/results/metrics.csv, comparisons.csv, status.csv) or from
  role deliveries under results/ and data/ (never from workshop/inputs/, E7);
- a slide whose runs are not complete, whose figure is missing or whose
  placeholder cannot be filled is built as "ausstehend" with the reason;
- the design carries the workshop plot style (workshop/plotstyle) over to the
  slides: Libre Franklin, ink #222222, no frames, quiet rules, fixed group
  colours, vermilion only for the Brazil cable;
- at the end the slide text is scanned against workshop/inputs/ at runtime;
  only slide ids and hit counts are printed, never a value.

    uv run --no-project --with python-pptx --with pandas --with pyyaml --with matplotlib \
        python workshop/presentation/build_deck.py [--final] [--short] [--font Arial]
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = next(p for p in [Path(__file__).resolve(), *Path(__file__).resolve().parents]
            if (p / "workshop/plotstyle").is_dir())
sys.path.insert(0, str(ROOT / "workshop/plotstyle"))
import studystyle as st  # noqa: E402  colours and groups of the workshop plot style

DECK = ROOT / "workshop/presentation/deck.yaml"
SETTINGS = ROOT / "workshop/presentation/settings.yaml"
REGISTER = ROOT / "workshop/presentation/register.yaml"
ANSWERS = ROOT / "results/presentation/answers.yaml"     # per workspace, not committed
RUNS = ROOT / "workshop/analysis/runs.yaml"
RES = ROOT / "workshop/results"
INPUTS = ROOT / "workshop/inputs"
OUT = ROOT / "results/presentation"
# public documents: a number that appears there is not attributed to the NDA files
PUBLIC_DOCS = [ROOT / "workshop/decisions.md", ROOT / "workshop/BASELINE.md", ROOT / "workshop/README.md",
               *sorted((ROOT / "workshop/roles").glob("*.md"))]

# --------------------------------------------------------------------------- design tokens (plot style)
W, H = Inches(13.333), Inches(7.5)
MX = Inches(0.6)                       # left/right margin
CW = W - 2 * MX                        # content width
TOP = Inches(1.75)                     # content top
BOTTOM = Inches(6.8)                   # content bottom
INK, LABEL, TICK, GRID, FAINT = st.TEXT, st.LABEL, st.TICK, st.GRID, st.FAINT
SIZE = dict(title=26, subtitle=13, body=16, small=12, footer=9, kpi=44, section=40, cover=36)


def rgb(hex_):
    return RGBColor.from_string(hex_.lstrip("#").upper())


# --------------------------------------------------------------------------- data and placeholders

class Data:
    def __init__(self):
        self.spec = yaml.safe_load(RUNS.read_text())
        self.horizons = self.spec["horizons"]
        self.m = pd.read_csv(RES / "metrics.csv") if (RES / "metrics.csv").exists() else pd.DataFrame(
            columns=["run", "horizon", "section", "metric", "unit", "value"])
        self.c = pd.read_csv(RES / "comparisons.csv") if (RES / "comparisons.csv").exists() else pd.DataFrame(
            columns=["run", "reference", "horizon", "section", "metric", "unit", "value"])
        self.status = pd.read_csv(RES / "status.csv") if (RES / "status.csv").exists() else pd.DataFrame(
            columns=["run", "horizon", "status", "solve_min", "peak_gb"])
        self._csv = {}

    def run_state(self, run):
        done = set(self.m[self.m.run == run].horizon.unique())
        if len(done) == len(self.horizons):
            return "fertig"
        return "teilweise" if done else "geplant"

    def _safe(self, path):
        p = (ROOT / path).resolve()
        if INPUTS.resolve() in p.parents or p == INPUTS.resolve():
            raise PermissionError(f"{path}: workshop/inputs/ ist unter NDA und keine Quelle für Folien (E7)")
        if not p.exists():
            raise FileNotFoundError(f"Datei fehlt: {path}")
        return p

    def cfg(self, path):
        p = self._safe(path)
        if p not in self._csv:
            self._csv[p] = yaml.safe_load(p.read_text())
        return self._csv[p]

    def md_cell(self, path, heading, row, col):
        """Cell of the first Markdown table below a heading (heading text contains HEADING; '' = whole file).
        ROW matches the first cell (after removing ** and backticks, prefix match); COLUMN the header."""
        p = self._safe(path)
        lines = p.read_text().splitlines()
        if heading:
            idx = next((i for i, ln in enumerate(lines) if ln.startswith("#") and heading in ln), None)
            if idx is None:
                raise LookupError(f"{path}: keine Überschrift '{heading}'")
            lines = lines[idx + 1:]
        clean = lambda c: re.sub(r"[*`]", "", c).strip()  # noqa: E731
        start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")), None)
        if start is None:
            raise LookupError(f"{path}: keine Tabelle unter '{heading}'")
        tab = []
        for ln in lines[start:]:
            if not ln.lstrip().startswith("|"):
                break
            tab.append([clean(c) for c in ln.strip().strip("|").split("|")])
        header, body = tab[0], [r for r in tab[1:] if not set("".join(r)) <= set("-: ")]
        if col not in header:
            raise LookupError(f"{path}: keine Spalte '{col}' unter '{heading}'")
        j = header.index(col)
        for r in body:
            if r[0].startswith(row) and j < len(r):
                return r[j]
        raise LookupError(f"{path}: keine Zeile '{row}' unter '{heading}'")

    def csv(self, path):
        p = (ROOT / path).resolve()
        if INPUTS.resolve() in p.parents or p == INPUTS.resolve():
            raise PermissionError(f"{path}: workshop/inputs/ ist unter NDA und keine Quelle für Folien (E7)")
        if p not in self._csv:
            if not p.exists():
                raise FileNotFoundError(f"Datei fehlt: {path}")
            self._csv[p] = pd.read_csv(p)
        return self._csv[p]


def years(spec):
    if "-" in spec:
        a, b = map(int, spec.split("-"))
        return lambda h: (h >= a) & (h <= b)
    return lambda h: h == int(spec)


def fmt(v, dec, sign=False):
    s = f"{v:+,.{dec}f}" if sign else f"{v:,.{dec}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s.replace("-", "−")


def resolve(token, data):
    """Value of one placeholder as text; raises with a reason if it cannot be filled."""
    parts = token.split("|")
    kind = parts[0].strip()
    if kind == "date":
        return date.today().strftime("%d.%m.%Y")
    if kind == "status":
        states = [data.run_state(r) for r in data.spec["runs"]]
        return f"{states.count('fertig')} von {len(states)} Läufen fertig"
    if kind == "m":
        _, run, yrs, key, dec = parts
        sec, met = key.split("/", 1)
        d = data.m[(data.m.run == run) & (data.m.section == sec) & (data.m.metric == met)]
        d = d[years(yrs)(d.horizon)]
        if d.empty:
            raise LookupError(f"keine Kennzahl {run} {yrs} {key}")
        return fmt(d.value.mean(), int(dec))
    if kind == "share":
        # ratio of two metrics in percent: {{share|RUN|JAHRE|Sektion/Zähler|Sektion/Nenner|DEZ}}
        _, run, yrs, num, den, dec = parts
        vals = []
        for key in (num, den):
            sec, met = key.split("/", 1)
            d = data.m[(data.m.run == run) & (data.m.section == sec) & (data.m.metric == met)]
            d = d[years(yrs)(d.horizon)]
            if d.empty:
                raise LookupError(f"keine Kennzahl {run} {yrs} {key}")
            vals.append(d.value.mean())
        return fmt(100 * vals[0] / vals[1], int(dec)) + " %"
    if kind == "c":
        _, run, ref, yrs, key, dec = parts
        sec, met = key.split("/", 1)
        d = data.c[(data.c.run == run) & (data.c.reference == ref) & (data.c.section == sec) & (data.c.metric == met)]
        d = d[years(yrs)(d.horizon)]
        if d.empty:
            raise LookupError(f"kein Vergleich {run} − {ref} {yrs} {key}")
        return fmt(d.value.mean(), int(dec), sign=True)
    if kind == "md":
        # cell of a Markdown table in a role's handover: {{md|PATH|HEADING|ROW|COLUMN[|OPTION...]}}
        # options: an integer picks one value of a chain "a → b → c" (0, 1, ... or -1 for the last);
        # "en" marks an English source: numbers are converted to German format (4,400 → 4.400; 96.5 → 96,5).
        # Remarks in parentheses ("(lowest)") are always dropped: the slide states the value only.
        path, heading, row, col = parts[1:5]
        v = data.md_cell(path, heading, row, col)
        opts = parts[5:]
        for o in opts:
            if re.fullmatch(r"-?\d+", o):
                v = [x.strip() for x in v.split("→")][int(o)]
        v = re.sub(r"\s*\([^)]*\)", "", v).strip()
        if "en" in opts:
            v = re.sub(r"\d[\d,]*\.?\d*", lambda mo: mo.group(0).replace(",", "§").replace(".", ",").replace("§", "."), v)
        return v
    if kind == "src":
        # literal text that must appear in the cited file: {{src|PATH|TEXT}}
        _, path, txt = parts
        body = re.sub(r"\s+", " ", data._safe(path).read_text())
        if re.sub(r"\s+", " ", txt) not in body:
            raise LookupError(f"{path}: '{txt}' nicht belegt (Übergabe geändert?)")
        return txt
    if kind == "cfg":
        # value from a config file: {{cfg|PATH|key.sub.key}}
        _, path, key = parts
        v = data.cfg(path)
        for k in key.split("."):
            if not isinstance(v, dict) or (k not in v and (not k.isdigit() or int(k) not in v)):
                raise LookupError(f"{path}: kein Schlüssel {key}")
            v = v[k] if k in v else v[int(k)]
        if isinstance(v, float):
            return fmt(v, 0 if v.is_integer() else 2)
        if isinstance(v, int) and not isinstance(v, bool):
            return fmt(v, 0)
        return "–" if v is None else str(v)
    if kind == "csv":
        _, path, row, col, dec = parts
        df = data.csv(path)
        if "=" in row:
            mask = pd.Series(True, index=df.index)
            for cond in row.split(";"):
                k, v = cond.split("=", 1)
                mask &= df[k].astype(str) == v
            sel = df.loc[mask, col]
        else:
            sel = df.loc[df.iloc[:, 0].astype(str) == row, col]
        if sel.empty:
            raise LookupError(f"{path}: keine Zeile {row}")
        v = sel.iloc[0]
        try:
            return fmt(float(v), int(dec))
        except ValueError:
            return str(v)
    raise ValueError(f"unbekannter Platzhalter {{{{{token}}}}}")


PH = "▢"  # marks a placeholder for missing content on a slide


def marker(token):
    """Short visible placeholder for a value that cannot be filled yet: what it waits for."""
    parts = token.split("|")
    kind = parts[0].strip()
    if kind in ("m", "share"):
        return f"{PH} {parts[1]}"
    if kind == "c":
        return f"{PH} {parts[1]}−{parts[2]}"
    if kind in ("md", "csv", "cfg", "src") and len(parts) > 1:
        return f"{PH} {Path(parts[1]).name}"
    return PH


def fill(text, data, problems):
    def sub(mo):
        try:
            return resolve(mo.group(1), data)
        except PermissionError:
            raise
        except Exception as e:  # collected; the slide keeps its layout and shows a placeholder
            problems.append(str(e))
            return marker(mo.group(1))
    return re.sub(r"\{\{(.*?)\}\}", sub, str(text))


def is_open(txt):
    """Text that is still a placeholder or a TODO: drawn grey and italic."""
    return str(txt).startswith("TODO") or PH in str(txt)


# --------------------------------------------------------------------------- settings and questions

def e4_runs():
    return yaml.safe_load(SETTINGS.read_text())["fest"]["e4_laeufe"]


def context(data, deck):
    """Facts the questions depend on."""
    done = sorted(r for r in data.spec["runs"] if data.run_state(r) == "fertig")
    needs = {r for s in deck["slides"] for r in s.get("requires", [])}
    return {
        "laeufe": done,
        "ausstehende_folien": any(data.run_state(r) != "fertig" for r in needs if r in data.spec["runs"]),
        "testlaeufe_fertig": any(r not in e4_runs() and r != "BASE" for r in done),
        "nda_vorhanden": INPUTS.is_dir(),
    }


def load_answers():
    return yaml.safe_load(ANSWERS.read_text()) or {} if ANSWERS.exists() else {}


def open_questions(data, deck):
    """Questions the skill has to ask now: condition true and no valid stored answer."""
    cfg, ans, ctx = yaml.safe_load(SETTINGS.read_text()), load_answers(), context(data, deck)
    out = []
    for q in cfg["fragen"]:
        if q["wenn"] != "immer" and not ctx.get(q["wenn"]):
            continue
        a = ans.get(q["key"])
        if a is not None:
            dep = q.get("neu_fragen_wenn")
            if not dep or a.get("kontext") == ctx.get(dep):
                continue
        out.append(q)
    return out


def settings(data, deck, overrides):
    """Effective settings: fixed values, then stored answers, then defaults; overrides win."""
    cfg, ans = yaml.safe_load(SETTINGS.read_text()), load_answers()
    eff = dict(cfg["fest"])
    for q in cfg["fragen"]:
        eff[q["key"]] = ans[q["key"]]["wert"] if q["key"] in ans else q["default"]
    eff.update(overrides)
    return eff


def save_answers(overrides, data, deck):
    cfg, ans, ctx = yaml.safe_load(SETTINGS.read_text()), load_answers(), context(data, deck)
    keys = {q["key"]: q for q in cfg["fragen"]}
    for k, v in overrides.items():
        if k not in keys:
            sys.exit(f"--set {k}: keine Frage in settings.yaml (feste Werte werden nicht gefragt)")
        dep = keys[k].get("neu_fragen_wenn")
        ans[k] = {"wert": v, "am": date.today().isoformat(), **({"kontext": ctx[dep]} if dep else {})}
    ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    ANSWERS.write_text(yaml.dump(ans, Dumper=type("D", (yaml.SafeDumper,), {"ignore_aliases": lambda *_: True}),
                                 allow_unicode=True, sort_keys=False))


# --------------------------------------------------------------------------- register (data, assumptions, decisions)

NDA_SOURCE = "vertrauliche Projektdaten (NDA)"


def load_register():
    reg = yaml.safe_load(REGISTER.read_text())
    for kind, items in reg.items():
        for it in items:
            if not it.get("nda"):
                continue
            # E7: an NDA entry names only the kind of source before processing, never a value
            bad = [f for f in ("wert", "ergebnis", "wirkung", "jahr") if it.get(f)]
            bad += [f for f, v in it.items() if isinstance(v, str) and ("{{" in v or "workshop/inputs" in v)]
            if bad or it.get("quelle") != NDA_SOURCE + ", vor der Verarbeitung":
                sys.exit(f"register.yaml {it['id']}: NDA-Eintrag darf nur Quelle '{NDA_SOURCE}, vor der "
                         f"Verarbeitung', Verarbeitung und Verwendung nennen (E7); unzulässig: {bad or ['quelle']}")
    return reg


def handover_changes():
    """Handovers listed in register.yaml whose content changed since they were worked in (sha256 prefix)."""
    import hashlib
    out = []
    for h in (load_register().get("uebergaben") or []):
        p = ROOT / h["pfad"]
        if not p.exists():
            out.append(f"{h['pfad']} fehlt")
            continue
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        if sha != str(h.get("sha", "")):
            out.append(f"{h['pfad']} (Rolle {h.get('rolle', '?')}) geändert seit {h.get('eingearbeitet', '?')}, jetzt sha {sha}")
    return out


def _role_ok(entry, rollen):
    if not rollen:
        return True
    who = str(entry.get("rolle", entry.get("wer", "")))
    return any(str(r) in who for r in rollen)


def register_table(kind, data, problems, eff, filt=None, rollen=None, ids=None):
    reg = load_register()
    reg = {k: [e for e in v if _role_ok(e, rollen)] if k != "uebergaben" else v for k, v in reg.items()}
    if ids:
        reg = {k: [e for e in v if e.get("id") in ids] if k != "uebergaben" else v for k, v in reg.items()}
    if kind == "daten":
        header = ["", "Daten", "Quelle (vor der Verarbeitung)", "Jahr", "Verarbeitung → Ergebnis", "Rolle"]
        rows = []
        for d in reg["daten"]:
            res = d.get("verwendung") if d.get("nda") else d.get("ergebnis", "")
            rows.append([d["id"], d["name"], d["quelle"], str(d.get("jahr", "–")),
                         fill(f"{d.get('verarbeitung', '')} → {res}", data, problems), str(d.get("rolle", ""))])
        return header, rows
    if kind == "annahmen":
        header = ["", "Annahme", "Wert", "Quelle", "Wirkung auf den Kabelwert"]
        return header, [[a["id"], a["name"], fill(a.get("wert", ""), data, problems), a.get("quelle", ""),
                         a.get("wirkung", "")] for a in reg["annahmen"]]
    if kind == "entscheidungen":
        header = ["Phase", "Entscheidung (wer)", "Zwischenschritt", "Wirkung"]
        rows = []
        for e in reg["entscheidungen"]:
            if filt and not str(e["wann"]).startswith(tuple(filt)):
                continue
            if e.get("test") and eff.get("testlaeufe") == "weglassen":
                continue
            missing = [r for r in e.get("requires", []) if data.run_state(r) != "fertig"]
            eff_txt = ("ausstehend: " + ", ".join(missing)) if missing else fill(e.get("wirkung", ""), data, problems)
            rows.append([e["wann"], f"{e['id']} {e['entscheidung']} ({e['wer']})", e.get("schritt", ""), eff_txt])
        rows.sort(key=lambda r: r[0])
        return header, rows
    raise ValueError(kind)


# --------------------------------------------------------------------------- drawing helpers

def text(slide, x, y, w, h, lines, size, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         font=None, space_after=0):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate([lines] if isinstance(lines, str) else lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, rgb(color), font
    return box


def bullets(slide, x, y, w, h, items, font, size=SIZE["body"]):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        mark = p.add_run()                       # flat square as bullet, as in legend_squares
        mark.text = "■  "
        mark.font.size, mark.font.color.rgb, mark.font.name = Pt(size * 0.55), rgb(st.NEUTRAL), font
        todo = is_open(item)
        r = p.add_run()
        r.text = item
        r.font.size, r.font.name = Pt(size), font
        r.font.color.rgb = rgb(TICK if todo else INK)
        r.font.italic = todo
    return box


def rule(slide, x1, y, x2, color, width_pt):
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y, x2, y)
    ln.line.color.rgb = rgb(color)
    ln.line.width = Pt(width_pt)
    return ln


def square(slide, x, y, size, color):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, size, size)
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(color)
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def picture(slide, path, x, y, w, h):
    """Insert an image unstretched, fitted into the box, top-left aligned."""
    from PIL import Image
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    return slide.shapes.add_picture(str(path), x, y, Emu(int(iw * scale)), Emu(int(ih * scale)))


def _border(cell, side, color, width_pt):
    tcPr = cell._tc.get_or_add_tcPr()
    tag = {"L": "a:lnL", "R": "a:lnR", "T": "a:lnT", "B": "a:lnB"}[side]
    for old in tcPr.findall(qn(tag)):
        tcPr.remove(old)
    ln = tcPr.makeelement(qn(tag), {"w": str(int(Pt(width_pt))) if color else "0"})
    if color:
        fill = ln.makeelement(qn("a:solidFill"), {})
        fill.append(fill.makeelement(qn("a:srgbClr"), {"val": color.lstrip("#").upper()}))
        ln.append(fill)
    else:
        ln.append(ln.makeelement(qn("a:noFill"), {}))
    tcPr.append(ln)


EFF = {}  # effective settings, set in main()
OVERFLOW = []  # layout warnings of the current slide


def table(slide, x, y, w, header, rows, font, size=SIZE["small"] + 1):
    """Table in plot style: no fills, no vertical lines, bold header over an ink rule, grey row rules."""
    nr, nc = len(rows) + 1, len(header)
    if nr > 8:
        size = max(9, size - (nr - 8) // 2 - 1)
    row_h = Inches(0.42) if nr <= 8 else Inches(0.3)
    shape = slide.shapes.add_table(nr, nc, x, y, w, row_h * nr)
    tbl = shape.table
    tbl._tbl.tblPr.find(qn("a:tableStyleId")).text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # no style
    tbl.first_row = tbl.horz_banding = False
    # column widths by content length (bounded), so long text columns get the room
    lens = [max(6, min(60, max(len(str(r[j])) for r in [header, *rows]))) for j in range(nc)]
    for j, ln in enumerate(lens):
        tbl.columns[j].width = Emu(int(w * ln / sum(lens)))
    # rough height check: characters per line from column width and font size
    est = 0
    for r in [header, *rows]:
        lines = max(1 + len(str(v)) // max(1, int(tbl.columns[j].width / Pt(size) * 1.9)) for j, v in enumerate(r))
        est += max(row_h, Pt(size) * 1.25 * lines + Inches(0.08))
    if y + est > BOTTOM:
        OVERFLOW.append(f"Tabelle zu lang (ca. {est / 914400:.1f} in)")
    numeric = [all(re.fullmatch(r"[−+\d.,% ]+|n/v|" + PH + r".*", str(r[j])) for r in rows) for j in range(nc)]
    for i, row in enumerate([header, *rows]):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.background()
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if numeric[j] and j > 0 else PP_ALIGN.LEFT
            r = p.add_run()
            r.text = str(val)
            todo = is_open(val)
            r.font.size, r.font.name, r.font.bold = Pt(size), font, i == 0
            r.font.color.rgb = rgb(LABEL if i == 0 else (TICK if todo else INK))
            r.font.italic = todo
            for side in "LRT":
                _border(cell, side, None, 0)
            _border(cell, "B", INK if i == 0 else GRID, 0.8 if i == 0 else 0.5)
    return shape


# --------------------------------------------------------------------------- slide layouts

def frame(prs, s, page, font, data, problems):
    """Common parts: part tag, title, subtitle, footer with source and page number."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    part = {"A": "A  Was eingeht", "B": "B  Wie gerechnet wird", "C": "C  Was herauskommt",
            "D": "D  Wie belastbar das ist", "Anhang": "Anhang"}.get(s.get("part"), "")
    if part:
        text(slide, MX, Inches(0.25), CW, Inches(0.25), part.upper(), SIZE["footer"], TICK, font=font)
    title = fill(s.get("title", ""), data, problems)
    box = text(slide, MX, Inches(0.5), CW, Inches(0.7), title, SIZE["title"], TICK if is_open(title) else INK,
               bold=True, font=font)
    if is_open(title):
        box.text_frame.paragraphs[0].runs[0].font.italic = True
    if s.get("subtitle"):
        text(slide, MX, Inches(1.2), CW, Inches(0.35), fill(s["subtitle"], data, problems), SIZE["subtitle"], TICK,
             font=font)
    rule(slide, MX, Inches(6.95), W - MX, GRID, 0.5)
    src = s.get("source")
    if src:
        text(slide, MX, Inches(7.02), CW - Inches(0.8), Inches(0.3), "Quelle: " + fill(src, data, problems),
             SIZE["footer"], FAINT, font=font)
    text(slide, W - MX - Inches(0.6), Inches(7.02), Inches(0.6), Inches(0.3), str(page), SIZE["footer"], FAINT,
         align=PP_ALIGN.RIGHT, font=font)
    return slide


def figure_placeholder(slide, x, y, w, h, name, reasons, font):
    """Grey area where a figure will go, with its file name and what it waits for."""
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    box.fill.solid()
    box.fill.fore_color.rgb = rgb(st.LAND)
    box.line.fill.background()
    box.shadow.inherit = False
    lines = [f"{PH} Abbildung folgt", name] + [f"– {r}" for r in dict.fromkeys(reasons)]
    text(slide, x + Inches(0.3), y + Inches(0.3), w - Inches(0.6), h - Inches(0.6), lines, SIZE["small"], TICK,
         font=font, space_after=4)


def pending(slide, reasons, font):
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MX, TOP, CW, BOTTOM - TOP)
    box.fill.solid()
    box.fill.fore_color.rgb = rgb(st.LAND)
    box.line.fill.background()
    box.shadow.inherit = False
    lines = ["ausstehend"] + [f"– {r}" for r in dict.fromkeys(reasons)]
    text(slide, MX + Inches(0.4), TOP + Inches(0.4), CW - Inches(0.8), BOTTOM - TOP - Inches(0.8), lines,
         SIZE["small"], TICK, font=font, space_after=4)


def build_cover(prs, s, meta, font, data, problems):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    text(slide, MX, Inches(2.3), CW, Inches(1.4), meta["title"], SIZE["cover"], INK, bold=True, font=font,
         anchor=MSO_ANCHOR.BOTTOM)
    text(slide, MX, Inches(3.85), CW, Inches(0.5), meta.get("subtitle", ""), 18, TICK, font=font)
    rule(slide, MX, Inches(4.6), MX + Inches(4), INK, 0.8)
    lines = [x for x in [meta.get("gruppe", ""), meta.get("authors", "")] if x]
    lines += [fill(b, data, problems) for b in s.get("bullets", [])]
    text(slide, MX, Inches(4.8), CW, Inches(1.2), lines, SIZE["small"], LABEL, font=font, space_after=4)
    return slide


def build_section(prs, s, font, data, problems):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    text(slide, MX, Inches(2.6), CW, Inches(1.0), s["title"], SIZE["section"], INK, bold=True, font=font,
         anchor=MSO_ANCHOR.BOTTOM)
    rule(slide, MX, Inches(3.8), MX + Inches(4), INK, 0.8)
    if s.get("subtitle"):
        text(slide, MX, Inches(4.0), CW, Inches(0.6), s["subtitle"], 18, TICK, font=font)
    return slide


def status_rows(data):
    rows = []
    for name, r in data.spec["runs"].items():
        d = data.status[data.status.run == name]
        state = data.run_state(name)
        if state == "geplant" and r.get("missing"):
            state = "geplant, Config fehlt"
        rows.append([name, r["run_name"], state, ", ".join(sorted(set(d.status))) or "–",
                     fmt(d.peak_gb.max(), 1) if len(d) else "–"])
    return ["Lauf", "Run-Name", "Status", "Solver", "Spitzenspeicher GB"], rows


def build_body(slide, s, font, data, problems):
    lay = s["layout"]
    items = [fill(b, data, problems) for b in s.get("bullets", [])]
    if lay == "bullets":
        bullets(slide, MX, TOP, Inches(10.5), BOTTOM - TOP, items, font)
    elif lay == "figure":
        fig = ROOT / s["figure"]
        if INPUTS.resolve() in fig.resolve().parents:
            raise PermissionError("Abbildung aus workshop/inputs/ (E7)")
        fw = Inches(7.7) if items else CW
        missing_runs = [r for r in s.get("requires", []) if data.run_state(r) != "fertig"]
        if not fig.exists() or missing_runs:
            why = [f"Lauf {r} fehlt" for r in missing_runs] or [f"Datei fehlt: {s['figure']}"]
            problems.extend(why)
            figure_placeholder(slide, MX, TOP, fw, BOTTOM - TOP, s["figure"], why, font)
        else:
            picture(slide, fig, MX, TOP, fw, BOTTOM - TOP)
        if items:
            bullets(slide, MX + Inches(8.0), TOP, CW - Inches(8.0), BOTTOM - TOP, items, font, SIZE["small"] + 2)
    elif lay == "table":
        t = s["table"]
        if t.get("auto") == "status":
            header, rows = status_rows(data)
        elif t.get("auto") in ("daten", "annahmen", "entscheidungen"):
            header, rows = register_table(t["auto"], data, problems, EFF, t.get("phasen"), t.get("rollen"),
                                          t.get("ids"))
        else:
            header = [fill(h, data, problems) for h in t["header"]]
            rows = [[fill(v, data, problems) for v in r] for r in t["rows"]]
        tw = CW if not items else Inches(8.2)
        shp = table(slide, MX, TOP, tw, header, rows, font)
        if items:
            bullets(slide, MX + Inches(8.5), TOP, CW - Inches(8.5), BOTTOM - TOP, items, font, SIZE["small"] + 2)
        _ = shp
    elif lay == "kpi":
        kp = s["kpis"]
        cw = CW / len(kp)
        for i, k in enumerate(kp):
            x = MX + int(cw * i)
            col = st.GROUPS.get(k.get("group", "Other"), st.NEUTRAL)
            square(slide, x, TOP + Inches(0.75), Inches(0.2), col)
            val = fill(k["value"], data, problems)
            text(slide, x + Inches(0.35), TOP + Inches(0.3), int(cw) - Inches(0.4), Inches(1.0),
                 val, SIZE["kpi"] if not is_open(val) else SIZE["title"], TICK if is_open(val) else INK,
                 bold=True, font=font)
            text(slide, x + Inches(0.35), TOP + Inches(1.4), int(cw) - Inches(0.4), Inches(0.5),
                 fill(k["label"], data, problems), SIZE["subtitle"], TICK, font=font)
        if items:
            bullets(slide, MX, TOP + Inches(2.4), CW, BOTTOM - TOP - Inches(2.4), items, font)
    else:
        raise ValueError(f"unbekanntes Layout {lay}")


# --------------------------------------------------------------------------- checks

def nda_scan(slide_texts):
    """Runtime scan of slide text against workshop/inputs/. Returns {slide_id: hits}; never the values."""
    if not INPUTS.is_dir():
        return None
    num = re.compile(r"\d[\d.,]*\d|\d")

    def norm(tok, german):
        t = tok.replace(".", "").replace(",", ".") if german else tok.replace(",", "")
        try:
            return round(float(t), 6)
        except ValueError:
            return None

    public = set()
    for p in PUBLIC_DOCS:
        if p.exists():
            public |= {norm(t, g) for t in num.findall(p.read_text()) for g in (True, False)}
    secret_nums, secret_words = set(), set()
    for f in INPUTS.rglob("*"):
        if f.is_file():
            raw = f.read_text(errors="ignore")
            for t in num.findall(raw):
                v = norm(t, False)
                if v is None or v in public or (v.is_integer() and 1900 <= v <= 2100) or len(t.strip(".,")) < 2:
                    continue
                secret_nums.add(v)
            secret_words |= set(re.findall(r"\b[A-Z][A-Z0-9]*-[A-Z0-9-]*\d[A-Z0-9-]*\b", raw))
    def strong(t):
        # one- and two-digit integers (years of life, percent steps, counts) match almost any file:
        # counted only if the number carries at least three significant digits or a decimal part
        v = norm(t, True)
        return v is not None and v in secret_nums and (not float(v).is_integer() or abs(v) >= 100)

    hits = {}
    for sid, txt in slide_texts.items():
        n = sum(1 for t in num.findall(txt) if strong(t))
        n += sum(1 for w in secret_words if w in txt)
        if n:
            hits[sid] = n
    return hits


def blockers():
    reports = sorted((ROOT / "results/review").glob("report-*.md"))
    if not reports:
        return None, 0
    rows = [ln for ln in reports[-1].read_text().splitlines() if re.match(r"\|\s*[\w-]+\s*\|\s*R\d\s*\|\s*Blocker", ln)]
    return reports[-1].name, len(rows)


def slide_text(slide):
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if sh.has_table:
            out += [c.text for r in sh.table.rows for c in r.cells]
    if slide.has_notes_slide:
        out.append(slide.notes_slide.notes_text_frame.text)
    return "\n".join(out)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--deck", type=Path, default=DECK)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--final", action="store_true", help="abort on TODO, pending slides or NDA hits")
    ap.add_argument("--short", action="store_true", help="drop slides marked optional")
    ap.add_argument("--font", default=None, help="font family (overrides the answer 'schrift')")
    ap.add_argument("--questions", action="store_true",
                    help="print the questions the skill must ask now (YAML) and exit")
    ap.add_argument("--nda-ok", nargs="+", default=[], metavar="FOLIE",
                    help="acknowledge checked NDA-scan hits of these slides (valid while their text is unchanged)")
    ap.add_argument("--set", nargs="+", default=[], metavar="KEY=VALUE",
                    help="store answers in results/presentation/answers.yaml, then build")
    a = ap.parse_args()

    deck = yaml.safe_load(a.deck.read_text())
    meta = deck["meta"]
    data = Data()
    load_register()                                   # fails early on an NDA entry that holds too much

    if a.questions:
        qs = open_questions(data, deck)
        print(yaml.safe_dump({"offene_fragen": qs, "kontext": context(data, deck)}, allow_unicode=True,
                             sort_keys=False) if qs else "keine offenen Fragen")
        return
    overrides = dict(kv.split("=", 1) for kv in a.set)
    if overrides:
        save_answers(overrides, data, deck)
    eff = settings(data, deck, {})
    if a.short:
        eff["umfang"] = "kurz"
    EFF.update(eff)
    font = a.font or eff.get("schrift") or meta.get("font", "Libre Franklin")
    meta = dict(meta, gruppe=eff.get("gruppe", ""))
    print("Einstellungen: " + ", ".join(f"{k}={eff[k]}" for k in
                                       ("gruppe", "umfang", "ausstehend", "testlaeufe", "nda_hinweis") if k in eff)
          + f", schrift={font}")

    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    report, texts, page = [], {}, 0
    for s in deck["slides"]:
        if eff["umfang"] == "kurz" and s.get("optional"):
            continue
        if s.get("test") and eff.get("testlaeufe") == "weglassen":
            continue
        if s.get("nda_hinweis") and eff.get("nda_hinweis") != "qualitativ":
            continue
        problems = []
        for run in s.get("requires", []):
            state = data.run_state(run) if run in data.spec["runs"] else "unbekannt"
            if state != "fertig":
                problems.append(f"Lauf {run} ist {state}")
        if problems and eff.get("ausstehend") == "weglassen" and s["layout"] not in ("title", "section"):
            continue
        page += 1
        if s["layout"] == "title":
            slide = build_cover(prs, s, meta, font, data, problems)
        elif s["layout"] == "section":
            slide = build_section(prs, s, font, data, problems)
        else:
            slide = frame(prs, s, page, font, data, problems)
            if eff.get("ausstehend") == "platzhalter":
                # full layout; every value that is missing shows as a placeholder where it belongs
                build_body(slide, s, font, data, problems)
            elif problems:        # runs missing: grey box instead of the slide body
                pending(slide, problems, font)
            else:
                build_body(slide, s, font, data, problems)
                if problems:      # a placeholder or figure failed: rebuild as pending
                    sp = slide.shapes._spTree
                    for shp in list(slide.shapes)[(4 if s.get("source") else 3) + bool(s.get("part")):]:
                        sp.remove(shp._element)
                    pending(slide, problems, font)
        if OVERFLOW:
            problems_layout = list(OVERFLOW)
            OVERFLOW.clear()
        else:
            problems_layout = []
        notes = [s.get("notes", "")]
        if s.get("owner"):
            notes.append(f"Folie gehört Rolle {s['owner']}.")
        if s.get("source"):
            notes.append("Quelle: " + fill(s["source"], data, []))
        if problems:
            notes.append("Ausstehend: " + "; ".join(dict.fromkeys(problems)))
        slide.notes_slide.notes_text_frame.text = "\n".join(n for n in notes if n)
        txt = slide_text(slide)
        texts[s["id"]] = txt
        n_ph = txt.count(PH)
        state = ("Platzhalter" if n_ph or eff.get("ausstehend") == "platzhalter" else "ausstehend") if problems \
            else ("Layout" if problems_layout else "ok")
        report.append((page, s["id"], s.get("owner", ""), state,
                       txt.count("TODO"), "; ".join(dict.fromkeys(problems + problems_layout)), n_ph))

    out = (a.out or OUT / f"praesentation-{date.today().isoformat()}.pptx").resolve()
    hits = nda_scan(texts)
    import hashlib
    sig = {k: hashlib.sha256(v.encode()).hexdigest()[:12] for k, v in texts.items()}
    ans = load_answers()
    acked = ans.get("_nda_geprueft", {})
    if a.nda_ok:
        for sid in a.nda_ok:
            if sid not in sig:
                sys.exit(f"--nda-ok: keine Folie {sid}")
            acked[sid] = sig[sid]
        ans["_nda_geprueft"] = acked
        ANSWERS.parent.mkdir(parents=True, exist_ok=True)
        ANSWERS.write_text(yaml.safe_dump(ans, allow_unicode=True, sort_keys=False))
    quitted = {k: v for k, v in (hits or {}).items() if acked.get(k) == sig[k]}
    if hits:
        hits = {k: v for k, v in hits.items() if k not in quitted}
    rep_name, n_block = blockers()

    print(f"{'#':>3}  {'Folie':22s} {'Rolle':6s} {'Stand':11s} TODO  {PH:>3}  Grund")
    for p, sid, own, state, todo, why, nph in report:
        print(f"{p:>3}  {sid:22s} {str(own):6s} {state:11s} {todo:>4}  {nph:>3}  {why[:80]}")
    n_pend = sum(r[3] in ("ausstehend", "Platzhalter") for r in report)
    n_todo = sum(r[4] for r in report)
    n_ph = sum(r[6] for r in report)
    print(f"\n{len(report)} Folien, {n_pend} mit fehlenden Inhalten ({n_ph} Platzhalter {PH}), {n_todo} TODO.")
    if hits is None:
        print("NDA-Scan: workshop/inputs/ nicht vorhanden, nicht geprüft.")
    elif hits:
        print("NDA-Scan: mögliche Treffer (von Hand prüfen, Werte werden nicht angezeigt): "
              + ", ".join(f"{k} ({v})" for k, v in hits.items())
              + "\n  Nach Prüfung quittieren: --nda-ok " + " ".join(hits))
    else:
        print("NDA-Scan: keine offenen Treffer im Folientext und in den Notizen (Bilder nicht geprüft).")
    if quitted:
        print("NDA-Scan: quittiert (Text unverändert seit Prüfung): " + ", ".join(quitted))
    changed = handover_changes()
    if changed:
        print("Übergaben geändert – register.yaml/deck.yaml prüfen, dann sha in register.yaml aktualisieren:")
        for c in changed:
            print("  " + c)
    if rep_name is None:
        print("Review: kein Bericht unter results/review/ – vor dem Präsentieren Rolle 5 (E8).")
    elif n_block:
        print(f"Review: {n_block} Blocker in {rep_name} – nicht präsentieren, bevor sie behoben sind (E8).")
    else:
        print(f"Review: keine Blocker in {rep_name}.")

    if a.final and (n_pend or n_todo or hits or n_block or changed):
        sys.exit("--final: offene Folien, TODO, NDA-Treffer, Blocker oder geänderte Übergaben – keine Datei geschrieben.")
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"\nGeschrieben: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
