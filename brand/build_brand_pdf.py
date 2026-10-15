"""Builds the Nirvana brand & design-system PDF (derived from nirvanatech.com, observed 2026-10-15)."""
import re
import sys

from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS = "/tmp/claude-0/fonts"
OUT = sys.argv[1] if len(sys.argv) > 1 else "Nirvana_Brand_Design_System.pdf"
for name, f in [("Serif", "InstrumentSerif-Regular.ttf"), ("SerifIt", "InstrumentSerif-Italic.ttf"), ("M4", "Manrope-400.ttf"),
                ("M5", "Manrope-500.ttf"), ("M6", "Manrope-600.ttf"), ("M7", "Manrope-700.ttf"), ("M8", "Manrope-800.ttf")]:
    pdfmetrics.registerFont(TTFont(name, f"{FONTS}/{f}"))

W, H = 792, 612
M = 54
C = {k: HexColor(v) for k, v in {
    "navy900": "#040C21", "navy": "#003366", "deepnavy": "#10285B", "navyblue": "#1C2E52", "navy800": "#002447",
    "sun": "#FFB900", "gold": "#FBC674", "lightgold": "#FEF7EB",
    "headline": "#1C1F26", "graphite": "#363D4D", "n600": "#555B67", "n500": "#767D8A", "grey": "#9B9EA6", "n400": "#A0A5AE",
    "n200": "#E3E5E8", "border": "#E6E7E9", "n100": "#F5F6F7", "white": "#FFFFFF",
    "chip": "#C5D3F5", "periwinkle": "#ADC2F1", "lightblue": "#80A7D9", "royal": "#3067DB", "teal": "#00A89C",
    "turq": "#C8ECE9", "coral": "#F05A24", "ctabg": "#DEE7F9",
}.items()}

c = canvas.Canvas(OUT, pagesize=(W, H))
c.setTitle("Nirvana Brand & Design System")
c.setAuthor("Nirvana CoS office (derived from nirvanatech.com)")
c.setSubject("Working brand reference for internal slides, documents and dashboards")
PAGE = [0]


# ---------------- helpers ----------------
def fill(col):
    c.setFillColor(col)


def text(x, y, s, font="M4", size=10, col=None, align="left", tracking=0):
    fill(col or C["graphite"])
    if tracking:
        c.saveState()
        t = c.beginText()
        t.setFont(font, size)
        t.setCharSpace(tracking)
        w = pdfmetrics.stringWidth(s, font, size) + tracking * (len(s) - 1)
        t.setTextOrigin(x - (w if align == "right" else w / 2 if align == "center" else 0), y)
        t.textOut(s)
        c.drawText(t)
        c.restoreState()
        return
    c.setFont(font, size)
    {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align](x, y, s)


def para(x, y, s, width, font="M4", size=10, leading=None, col=None):
    leading = leading or size * 1.5
    fill(col or C["graphite"])
    c.setFont(font, size)
    for line in simpleSplit(s, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def rrect(x, y, w, h, r, fillc=None, stroke=None, lw=0.75):
    if fillc is not None:
        fill(fillc)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1 if fillc is not None else 0, stroke=1 if stroke is not None else 0)


def eyebrow(x, y, s, col=None):
    text(x, y, s.upper(), "M6", 8, col or C["n500"], tracking=1.2)


def header(kicker, title, sub=None):
    eyebrow(M, H - M - 4, kicker)
    text(M, H - M - 44, title, "Serif", 34, C["headline"])
    if sub:
        para(M, H - M - 66, sub, 560, "M4", 10.5, 15.5, C["n600"])


def footer():
    PAGE[0] += 1
    c.setStrokeColor(C["border"])
    c.setLineWidth(0.6)
    c.line(M, 36, W - M, 36)
    text(M, 22, "Nirvana Brand & Design System  ·  v0.1 working reference  ·  derived from nirvanatech.com on Oct 15, 2026", "M4", 7.5, C["n500"])
    text(W - M, 22, str(PAGE[0]), "M6", 7.5, C["n500"], "right")


def new_page(bg=None):
    if PAGE[0]:
        c.showPage()
    if bg:
        fill(bg)
        c.rect(0, 0, W, H, fill=1, stroke=0)


# ---------------- logo from the site's own SVG ----------------
def parse_svg(path="/home/claude/brand/nirvana-logo.svg"):
    svg = open(path).read()
    return [(m.group(1), m.group(2)) for m in re.finditer(r'<path d="([^"]+)" fill="([^"]+)"', svg)]


LOGO = parse_svg()


def draw_path(d, sx, sy, ox, oy):
    p = c.beginPath()
    toks = re.findall(r"[MLHVCZmlhvcz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    i, cmd, cx, cy = 0, None, 0.0, 0.0
    X = lambda v: ox + v * sx
    Y = lambda v: oy - v * sy
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                p.close()
            continue
        nums = lambda n: [float(v) for v in toks[i:i + n]]
        if cmd in "Mm":
            a, b = nums(2); i += 2
            cx, cy = (a, b) if cmd == "M" else (cx + a, cy + b)
            p.moveTo(X(cx), Y(cy)); cmd = "L" if cmd == "M" else "l"
        elif cmd in "Ll":
            a, b = nums(2); i += 2
            cx, cy = (a, b) if cmd == "L" else (cx + a, cy + b)
            p.lineTo(X(cx), Y(cy))
        elif cmd in "Hh":
            a, = nums(1); i += 1
            cx = a if cmd == "H" else cx + a
            p.lineTo(X(cx), Y(cy))
        elif cmd in "Vv":
            a, = nums(1); i += 1
            cy = a if cmd == "V" else cy + a
            p.lineTo(X(cx), Y(cy))
        elif cmd in "Cc":
            v = nums(6); i += 6
            if cmd == "c":
                v = [v[0] + cx, v[1] + cy, v[2] + cx, v[3] + cy, v[4] + cx, v[5] + cy]
            p.curveTo(X(v[0]), Y(v[1]), X(v[2]), Y(v[3]), X(v[4]), Y(v[5]))
            cx, cy = v[4], v[5]
        else:
            i += 1
    return p


def logo(x, y, height, mark_only=False, bg=None):
    """(x,y) = bottom-left. Source viewBox 1336x305."""
    s = height / 305.0
    paths = LOGO[:3] if mark_only else LOGO
    for d, col in paths:
        colr = C["white"] if col == "white" else HexColor(col)
        if col == "white" and bg is not None:
            colr = bg
        c.setFillColor(colr)
        c.drawPath(draw_path(d, s, s, x, y + height), fill=1, stroke=0)


# ======================= 1. COVER =======================
new_page(C["white"])
fill(C["lightgold"]); c.circle(W - 40, 40, 260, fill=1, stroke=0)
fill(C["turq"]); c.wedge(W - 300, -260, W + 220, 260, 90, 90, fill=1, stroke=0)
logo(M, H - M - 30, 30)
eyebrow(M, 300, "Brand & design system · v0.1")
text(M, 236, "Designing with", "Serif", 64, C["headline"])
text(M, 172, "the Nirvana look", "Serif", 64, C["headline"])
para(M, 138, "A working reference for slides, documents and internal tools, reverse-engineered from the live "
     "nirvanatech.com site. Colors, type and components below are measured from the site's own CSS.", 430, "M4", 11, 16.5, C["n600"])
rrect(M, 62, 330, 34, 17, C["n100"])
text(M + 14, 75, "Not an official brand book. Confirm with Nirvana marketing before external use.", "M5", 7.8, C["n600"])
PAGE[0] += 1

# ======================= 2. PRINCIPLES =======================
new_page(C["white"])
header("01 · Foundations", "What the brand feels like",
       "Five observations from the site, turned into rules we can apply to any slide, memo or dashboard.")
items = [
    ("Calm confidence", "Lots of white space, few colors, no visual noise. The product (data, savings, speed) carries the message."),
    ("Serif for the claim, sans for the work", "Instrument Serif states the big idea or the big number. Manrope does everything else."),
    ("Navy is the voice, gold is the signature", "Deep navy for text and primary actions. The sun-gold appears in the logo and sparingly as a highlight."),
    ("Numbers are heroes", "Key metrics (32B+ miles, 20% discount) are set huge in serif with a short sans caption underneath."),
    ("Soft, rounded, approachable", "Pill buttons, rounded cards and pale tinted chips keep a technical subject friendly."),
]
y = 410
for i, (h, b) in enumerate(items):
    col = M + (i % 3) * 232 if i < 3 else M + (i - 3) * 232
    yy = y if i < 3 else 210
    rrect(col, yy - 140, 216, 150, 12, None, C["border"])
    text(col + 16, yy - 14, f"{i + 1:02d}", "Serif", 26, C["sun"])
    para(col + 16, yy - 44, h, 186, "M7", 11.5, 15, C["headline"])
    para(col + 16, yy - 78, b, 186, "M4", 9.2, 13.6, C["n600"])
rrect(M + 2 * 232, 70, 216, 150, 12, C["navy900"])
text(M + 2 * 232 + 16, 196, "Voice", "M6", 8, C["gold"], tracking=1.2)
para(M + 2 * 232 + 16, 174, "Plain, benefit-first, specific. Lead with the outcome for the fleet, back it with a number, skip jargon.",
     186, "Serif", 15, 19, C["white"])
footer()

# ======================= 3. LOGO =======================
new_page(C["white"])
header("02 · Logo", "Logo and mark",
       "The mark is a sun cresting a road-like horizon. Use the full lockup by default and the mark alone only where space is tight (favicons, avatars, small footers).")
rrect(M, 190, 430, 240, 14, C["n100"])
logo(M + 50, 285, 52)
# clear-space guides
c.setDash(2, 3); c.setStrokeColor(C["lightblue"]); c.setLineWidth(0.6)
lw = 52 * 1336 / 305
c.rect(M + 50 - 26, 285 - 26, lw + 52, 104, fill=0, stroke=1); c.setDash()
text(M + 22, 202, "Clear space ≥ half the logo height on every side. Minimum width 96 px / 1 in.", "M5", 8.5, C["n600"])
rrect(M + 450, 316, 234, 114, 14, C["white"], C["border"])
logo(M + 467 + 70, 340, 70, mark_only=True)
text(M + 466, 324, "Mark only", "M6", 8, C["n500"], tracking=1)
rrect(M + 450, 190, 234, 110, 14, C["white"], C["border"])
for i, (hx, nm) in enumerate([("#FFB900", "Sun gold"), ("#040C21", "Nirvana navy")]):
    rrect(M + 466 + i * 108, 236, 92, 44, 8, HexColor(hx))
    text(M + 466 + i * 108, 222, nm, "M6", 8.5, C["headline"])
    text(M + 466 + i * 108, 210, hx, "M4", 8, C["n500"])
text(M + 466, 286, "Logo colors (from the site's SVG)", "M6", 8, C["n500"], tracking=0.6)
eyebrow(M, 166, "Don't")
for i, s in enumerate(["Recolor the sun or wordmark", "Stretch, rotate, outline or add effects",
                       "Place on busy photos without a solid backing", "Invent a white version; request the official reversed file"]):
    text(M + (i % 2) * 330, 140 - (i // 2) * 20, "×  " + s, "M5", 9.5, C["graphite"])
footer()

# ======================= 4. COLOR =======================
new_page(C["white"])
header("03 · Color", "Palette",
       "Navy-led and mostly neutral. Hex values are the site's own CSS variables. Rough budget per page: 70% white and neutrals, 20% navy, 10% accents.")


def swatch(x, y, w, hx, name, role, token, dark_text=False):
    col = HexColor(hx)
    rrect(x, y, w, 58, 10, col, C["border"] if hx.upper() in ("#FFFFFF", "#F5F6F7", "#FEF7EB") else None)
    tc = C["headline"] if dark_text else C["white"]
    text(x + 10, y + 40, name, "M7", 9, tc)
    text(x + 10, y + 10, hx.upper(), "M5", 8.5, tc)
    para(x, y - 14, role, w, "M4", 7.6, 10.5, C["n600"])
    text(x, y - 36, token, "M4", 6.8, C["n400"])


eyebrow(M, 452, "Primary")
row = [("#040C21", "Nirvana Navy", "Logo wordmark, darkest text, dark sections", "--dark-navy"),
       ("#003366", "Navy", "Primary buttons (Find an Agent), tags text", "--navy"),
       ("#1C2E52", "Navy Blue", "Secondary dark buttons (Discover)", "--navy-blue"),
       ("#10285B", "Deep Navy", "Charts, emphasis panels", "--deep-navy"),
       ("#FFB900", "Sun Gold", "Logo only, plus rare highlights", "logo SVG"),
       ("#FBC674", "Gold", "Warm highlight, illustration", "--gold"),
       ("#FEF7EB", "Light Gold", "Alternate section background", "--light-gold")]
for i, (hx, n, r, t) in enumerate(row):
    swatch(M + i * 98, 378, 90, hx, n, r, t, dark_text=hx in ("#FFB900", "#FBC674", "#FEF7EB"))
eyebrow(M, 290, "Neutrals")
row = [("#1C1F26", "Headline", "Headings, big numbers", "--headline"),
       ("#363D4D", "Graphite", "Body text, links", "--graphite"),
       ("#555B67", "Neutral 600", "Secondary text", "--neutral-600"),
       ("#9B9EA6", "Grey", "Captions, meta", "--grey"),
       ("#E3E5E8", "Neutral 200", "Secondary buttons", "--neutral-200"),
       ("#E6E7E9", "Border", "Hairlines, card borders", "--border-color"),
       ("#F5F6F7", "Neutral 100", "Panels, table stripes", "--neutral-100")]
for i, (hx, n, r, t) in enumerate(row):
    swatch(M + i * 98, 216, 90, hx, n, r, t, dark_text=i >= 4)
eyebrow(M, 122, "Accents (use sparingly)")
acc = [("#C5D3F5", "Chip blue"), ("#ADC2F1", "Periwinkle"), ("#80A7D9", "Light blue"), ("#00A89C", "Teal"),
       ("#C8ECE9", "Turquoise"), ("#F05A24", "Coral")]
for i, (hx, n) in enumerate(acc):
    x = M + i * 114
    rrect(x, 70, 24, 24, 12, HexColor(hx))
    text(x + 32, 85, n, "M6", 8.5, C["headline"])
    text(x + 32, 73, hx, "M4", 8, C["n500"])
footer()

# ======================= 5. TYPOGRAPHY =======================
new_page(C["white"])
header("04 · Typography", "Two typefaces, clear jobs",
       "Both are free Google Fonts. On the site the serif is always regular weight; hierarchy comes from size, not boldness.")
rrect(M, 250, 330, 200, 14, C["n100"])
text(M + 18, 420, "DISPLAY", "M6", 8, C["n500"], tracking=1.2)
text(M + 18, 352, "Instrument Serif", "Serif", 46, C["headline"])
text(M + 18, 318, "Aa  Bb  Gg  32B+  $40M  20%", "Serif", 26, C["headline"])
para(M + 18, 290, "Heroes, section statements, big stats, pull quotes. Regular 400 only, tight tracking (-1%), never body copy.",
     292, "M4", 9, 13, C["n600"])
rrect(M + 352, 250, 334, 200, 14, C["n100"])
text(M + 370, 420, "TEXT & UI", "M6", 8, C["n500"], tracking=1.2)
text(M + 370, 360, "Manrope", "M5", 40, C["headline"])
for i, (f, lab) in enumerate([("M4", "Regular 400 · body"), ("M5", "Medium 500 · H2"), ("M6", "SemiBold 600 · H3, labels, buttons"), ("M7", "Bold 700 · emphasis")]):
    text(M + 370, 330 - i * 17, lab, f, 11, C["graphite"])
para(M + 370, 264, "Fallbacks: Arial, sans-serif (site) · Calibri/Arial in Office files.", 300, "M4", 8.5, 12, C["n500"])
eyebrow(M, 222, "Type scale (web px; site uses a 16 px base)")
scale = [("Display stat", "Serif", 128, 40, "Instrument Serif 400 · 1.0 lh"), ("H1 hero", "Serif", 64, 30, "Instrument Serif 400 · -1 px"),
         ("H2 statement", "Serif", 48, 24, "Instrument Serif 400 · 1.2 lh"), ("H2 section", "M5", 36, 18, "Manrope 500 · 1.2 lh"),
         ("H3 card title", "M6", 20, 13, "Manrope 600"), ("Body", "M4", 16, 10.5, "Manrope 400 · 1.5 lh · Graphite"),
         ("Small / meta", "M4", 14, 9.5, "Manrope 400 · Neutral 600"), ("Label / chip", "M6", 14, 9, "Manrope 600 · Navy")]
for i, (lab, f, px, show, spec) in enumerate(scale):
    colx = M + (i % 2) * 344
    yy = 196 - (i // 2) * 36
    text(colx, yy, f"{px}", "M7", 9, C["sun"])
    text(colx + 28, yy, lab, f, min(show, 15), C["headline"])
    text(colx + 150, yy, spec, "M4", 8, C["n500"])
footer()

# ======================= 6. COMPONENTS =======================
new_page(C["white"])
header("05 · Components", "Building blocks", "As implemented on the site. Reuse these shapes in slides and tools rather than inventing new ones.")


def pill(x, y, label, bg, fg, font="M6", size=10, arrow=False, pad=16, h=30):
    s = label + ("  →" if arrow else "")
    w = pdfmetrics.stringWidth(s, font, size) + pad * 2
    rrect(x, y, w, h, h / 2, bg)
    text(x + pad, y + h / 2 - size * 0.35, s, font, size, fg)
    return w


eyebrow(M, 450, "Buttons")
x = M
x += pill(x, 410, "Find an Agent", C["navy"], C["white"]) + 12
x += pill(x, 410, "Report a Claim", C["n200"], C["navy900"]) + 12
x += pill(x, 410, "Discover", C["navyblue"], C["white"], arrow=True) + 12
text(x + 6, 420, "Our Insurance  →", "M6", 10, C["navy900"])
para(M, 398, "Primary: Navy #003366 pill, white Manrope 600. Secondary: Neutral 200 pill, navy text. Text links carry a → arrow. Fully rounded (999 px).",
     600, "M4", 8.6, 12, C["n600"])
eyebrow(M, 352, "Chips / tags")
x = M
for lab in ["Safety", "Engineering", "Newsletter"]:
    x += pill(x, 318, lab, C["chip"], C["navy"], size=9, pad=10, h=22) + 8
para(M, 304, "Chip blue #C5D3F5 at 80%, navy text, 600 weight, pill radius.", 300, "M4", 8.6, 12, C["n600"])
eyebrow(M + 360, 352, "Stat block")
for i, (num, cap) in enumerate([("32B+", "miles of telematics data"), ("20%", "upfront safety discount")]):
    bx = M + 360 + i * 165
    text(bx + 70, 300, num, "Serif", 44, C["headline"], "center")
    text(bx + 70, 284, cap, "M4", 8.5, C["n600"], "center")
c.setStrokeColor(C["border"]); c.line(M + 515, 280, M + 515, 340)
eyebrow(M, 250, "Card")
rrect(M, 92, 210, 146, 16, C["white"], C["border"])
text(M + 18, 210, "Seamless Claims", "M6", 12, C["headline"])
para(M + 18, 190, "Short benefit statement in Graphite, two to three lines at most.", 172, "M4", 9, 13, C["n600"])
text(M + 18, 108, "Learn More  →", "M6", 9, C["navy900"])
eyebrow(M + 240, 250, "Banner")
rrect(M + 240, 92, 444, 146, 8, C["ctabg"])
c.saveState(); pth = c.beginPath(); pth.roundRect(M + 240, 92, 444, 146, 8); c.clipPath(pth, stroke=0, fill=0)
fill(C["chip"]); c.circle(M + 660, 120, 80, fill=1, stroke=0); c.restoreState()
text(M + 262, 196, "Building the first AI-native insurer", "Serif", 22, C["headline"])
para(M + 262, 172, "Soft periwinkle field with one sentence and one dark pill CTA. Radius 8 px, generous padding.", 290, "M4", 9, 13, C["n600"])
pill(M + 262, 112, "Discover", C["navyblue"], C["white"], arrow=True)
footer()

# ======================= 7. LAYOUT, SHAPE, IMAGERY =======================
new_page(C["white"])
header("06 · Layout, shape & imagery", "Space, radius and pictures")
eyebrow(M, 470, "Radius tokens")
for i, (r, lab) in enumerate([(8, "8 · small"), (10, "10 · default"), (16, "16 · cards"), (24, "24 · large"), (22, "pill · buttons")]):
    rrect(M + i * 66, 400, 58, 44, r, C["n100"], C["border"])
    text(M + i * 66, 386, lab, "M5", 7.5, C["graphite"])
eyebrow(M, 350, "Spacing")
for i, s in enumerate([4, 8, 16, 24, 32, 48, 64]):
    fill(C["lightblue"]); c.rect(M + sum([4, 8, 16, 24, 32, 48, 64][:i]) * 0.9 + i * 18, 300, s * 0.9, s * 0.9 if s < 40 else 36, fill=1, stroke=0)
    text(M + sum([4, 8, 16, 24, 32, 48, 64][:i]) * 0.9 + i * 18, 288, str(s), "M5", 8, C["n600"])
para(M, 268, "8-pt rhythm. Sections breathe: ~56–96 px vertical padding on web, one idea per slide. Hero content is centered; everything else is left-aligned on a 12-column grid.",
     330, "M4", 9, 13.5, C["n600"])
eyebrow(M + 380, 470, "Imagery")
rrect(M + 380, 300, 304, 150, 12, C["navy900"])
fill(C["gold"]); c.circle(M + 600, 400, 26, fill=1, stroke=0)
fill(C["deepnavy"]); c.rect(M + 380, 300, 304, 60, fill=1, stroke=0)
text(M + 396, 318, "Real fleets on real roads, natural light", "M6", 10, C["white"])
para(M + 380, 284, "Photography of trucks and drivers in wide landscapes, warm daylight, no stock-smile clichés. Product shots use clean UI on tablets. "
     "Decorative shapes: soft quarter circles in turquoise/mint with a fine grain (About page).", 304, "M4", 9, 13.5, C["n600"])
fill(C["turq"]); c.wedge(M + 380, 70, M + 520, 210, 0, 90, fill=1, stroke=0)
fill(C["lightgold"]); c.wedge(M + 500, 70, M + 640, 210, 90, 90, fill=1, stroke=0)
text(M + 640, 100, "Quarter-circle motif", "M5", 8.5, C["n600"], "right")
footer()

# ======================= 8. DATA VIZ & DASHBOARDS =======================
new_page(C["white"])
header("07 · Data & dashboards", "Charts and status in the brand",
       "Our own extension for internal tools (not on the website). Keep charts quiet: neutrals for context, navy for the main series, color only where it means something.")
eyebrow(M, 440, "Series order")
ser = [("#003366", "1 Navy"), ("#FFB900", "2 Sun gold"), ("#00A89C", "3 Teal"), ("#80A7D9", "4 Light blue"), ("#F05A24", "5 Coral"), ("#9B9EA6", "6 Grey (other)")]
for i, (hx, n) in enumerate(ser):
    rrect(M + i * 104, 404, 96, 24, 6, HexColor(hx))
    text(M + i * 104, 390, n, "M5", 8.5, C["graphite"])
eyebrow(M, 352, "Status (semantic, separate from brand accents)")
for i, (hx, bg, n) in enumerate([("#0B7A6F", "#D9F2EF", "Good / tailwind"), ("#8A5A00", "#FEF0D2", "Watch / warning"), ("#B23A12", "#FDE3D8", "Critical / headwind"), ("#003366", "#DEE7F9", "Info / new")]):
    pill(M + i * 160, 318, n, HexColor(bg), HexColor(hx), size=9, pad=12, h=24)
eyebrow(M, 270, "Example: bar chart")
vals = [62, 48, 35, 27, 18]
labs = ["Competitor", "Market", "Policy", "Research", "Other"]
c.setStrokeColor(C["border"]); c.setLineWidth(0.5)
for g in range(5):
    c.line(M, 110 + g * 30, M + 300, 110 + g * 30)
for i, v in enumerate(vals):
    rrect(M + 12 + i * 58, 110, 34, v * 1.8, 3, C["navy"] if i == 0 else C["lightblue"])
    text(M + 29 + i * 58, 98, labs[i], "M4", 7.5, C["n600"], "center")
    text(M + 29 + i * 58, 114 + v * 1.8, str(v), "M6", 8, C["headline"], "center")
eyebrow(M + 360, 270, "Rules")
y = 250
for r in ["Big number in Instrument Serif, caption in Manrope underneath", "One highlighted series in Navy; the rest in Light blue or Grey",
          "Hairline gridlines in Border #E6E7E9; no chart borders or 3D", "Tabular numerals; label values directly instead of legends",
          "Status pills use the semantic set, never the logo gold"]:
    text(M + 360, y, "—", "M6", 9, C["sun"]); y = para(M + 376, y, r, 300, "M4", 9, 13, C["graphite"]) - 6
footer()

# ======================= 9. SLIDES & DOCS =======================
new_page(C["white"])
header("08 · Applying it", "Slides and documents")
# slide thumbnails
def thumb(x, y, kind):
    w, h = 196, 110
    rrect(x, y, w, h, 6, C["white"], C["border"])
    if kind == "title":
        logo(x + 12, y + h - 22, 9)
        text(x + 12, y + 46, "Last-mile delivery", "Serif", 17, C["headline"])
        text(x + 12, y + 30, "Market entry plan", "Serif", 17, C["headline"])
        text(x + 12, y + 12, "CoS office · Oct 2026", "M4", 6.5, C["n500"])
    elif kind == "stat":
        text(x + 12, y + h - 16, "WHY NOW", "M6", 6, C["n500"], tracking=0.8)
        for i, (n, cp) in enumerate([("$40M", "saved via safety"), ("20%", "upfront discount"), ("32B+", "miles of data")]):
            text(x + 34 + i * 64, y + 44, n, "Serif", 22, C["headline"], "center")
            text(x + 34 + i * 64, y + 32, cp, "M4", 5.5, C["n600"], "center")
    elif kind == "section":
        fill(C["navy900"]); c.roundRect(x, y, w, h, 6, fill=1, stroke=0)
        text(x + 14, y + 52, "Go-to-market", "Serif", 22, C["white"])
        text(x + 14, y + 36, "02", "M6", 8, C["gold"])
    else:
        text(x + 12, y + h - 18, "Recommendation", "M6", 8.5, C["headline"])
        fill(C["n100"]); c.rect(x + 12, y + 14, 80, 60, fill=1, stroke=0)
        rrect(x + 100, y + 14, 84, 60, 4, C["ctabg"])
        text(x + 106, y + 60, "Key takeaway", "M6", 6, C["navy"])
    text(x, y - 12, {"title": "Title", "stat": "Stat / proof", "section": "Section divider", "body": "Content + takeaway"}[kind], "M5", 8, C["n600"])


for i, k in enumerate(["title", "section", "stat", "body"]):
    thumb(M + (i % 2) * 212, 330 - (i // 2) * 150, k)
eyebrow(M + 450, 450, "Slide rules")
y = 430
for r in ["16:9, white background; navy section dividers only", "Title in Instrument Serif 36–44 pt; body Manrope 14–18 pt",
          "One message per slide, stated as the title", "Max one accent color per slide besides navy", "Logo bottom-left on title slide only; page numbers in Grey",
          "Sources in 9 pt Grey at the slide foot"]:
    text(M + 450, y, "—", "M6", 9, C["sun"]); y = para(M + 466, y, r, 220, "M4", 9, 13, C["graphite"]) - 5
eyebrow(M + 450, y - 10, "Document rules")
y -= 30
for r in ["Manrope 10.5–11 pt body, 1.5 leading, Graphite", "H1 Instrument Serif 28 pt; H2 Manrope 600 14 pt",
          "Tables: Neutral 100 header, hairline rows", "Callouts: Light Gold or Chip-blue panel, 8 px radius"]:
    text(M + 450, y, "—", "M6", 9, C["sun"]); y = para(M + 466, y, r, 220, "M4", 9, 13, C["graphite"]) - 5
footer()

# ======================= 10. TOKENS =======================
new_page(C["white"])
header("09 · Tokens", "Copy-paste tokens", "Drop into any HTML page, dashboard or artifact. Office users: set theme colors and fonts from the same values.")
code = """:root {
  /* brand */
  --nv-navy-900: #040C21;   --nv-navy: #003366;      --nv-navy-blue: #1C2E52;
  --nv-deep-navy: #10285B;  --nv-sun: #FFB900;       --nv-gold: #FBC674;   --nv-gold-50: #FEF7EB;
  /* neutrals */
  --nv-headline: #1C1F26;   --nv-text: #363D4D;      --nv-text-2: #555B67; --nv-muted: #9B9EA6;
  --nv-n200: #E3E5E8;       --nv-border: #E6E7E9;    --nv-n100: #F5F6F7;   --nv-bg: #FFFFFF;
  /* accents */
  --nv-chip: #C5D3F5;       --nv-periwinkle: #ADC2F1; --nv-light-blue: #80A7D9;
  --nv-teal: #00A89C;       --nv-turquoise: #C8ECE9;  --nv-coral: #F05A24;  --nv-cta-bg: #DEE7F9;
  /* type */
  --nv-font-display: "Instrument Serif", Georgia, serif;
  --nv-font-body: "Manrope", Arial, sans-serif;
  /* shape */
  --nv-r-sm: 8px; --nv-r: 10px; --nv-r-card: 16px; --nv-r-lg: 24px; --nv-r-pill: 999px;
}
/* Google Fonts */
https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700&display=swap"""
rrect(M, 120, W - 2 * M, 340, 12, C["navy900"])
yy = 438
for line in code.splitlines():
    text(M + 20, yy, line, "M5", 8.6, HexColor("#DCE3F3") if not line.strip().startswith("/*") else C["gold"])
    yy -= 13.2
eyebrow(M, 96, "Sources & confidence")
para(M, 80, "Measured on Oct 15, 2026 from nirvanatech.com: CSS custom properties, computed styles of live elements, and the logo SVG. "
     "Type sizes were normalized from an 800 px-wide viewport. The data-viz palette, status colors and slide/document rules are our extensions, not Nirvana's.",
     W - 2 * M, "M4", 8.6, 12.5, C["n600"])
footer()
c.save()
print("wrote", OUT, PAGE[0], "pages")
