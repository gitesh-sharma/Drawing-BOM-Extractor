from pathlib import Path
import base64, json, os, re
import fitz
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

HEADERS = [
    "SL NO","AREA","LINE NO.","DRAWING NO.","REV.","SHEET","ITEM","SIZE (IN)",
    "SCHEDULE/CLASS","MOC","GRADE","DESCRIPTION","QTY","UOM","REMARKS"
]

ITEM_PATTERNS = [
    ("U-BOLT SUPPORT", r"\bU[- ]?BOLT\b"),
    ("STUD BOLT", r"\bSTUD\s+BOLTS?\b|\bSTUD\s+BOLT\b"),
    ("ELBOW 90", r"\b90\s*[°DEG]*\s*ELBOW\b|\bELBOW\s*90\b"),
    ("ELBOW 45", r"\b45\s*[°DEG]*\s*ELBOW\b|\bELBOW\s*45\b"),
    ("REDUCER", r"\bREDUCER\b"), ("TEE", r"\bTEE\b"), ("CROSS", r"\bCROSS\b"),
    ("FLANGE SO", r"\bSO\s*Q?\s*FLANGE\b|\bSOCKET\s*WELD\s*FLANGE\b"),
    ("FLANGE WN", r"\bWN\s*FLANGE\b|\bWELD\s*NECK\s*FLANGE\b"),
    ("BLIND FLANGE", r"\bBLIND\s*FLANGE\b"), ("GASKET", r"\bGASKET\b"),
    ("PIPE", r"\bPIPE\b"), ("VALVE", r"\bVALVE\b"), ("CAP", r"\bCAP\b"),
    ("OLET", r"\bOLET\b"), ("SUPPORT", r"\bSUPPORT\b"), ("NIPPLE", r"\bNIPPLE\b"),
    ("COUPLING", r"\bCOUPLING\b"), ("STRAINER", r"\bSTRAINER\b"),
    ("ORIFICE PLATE", r"\bORIFICE\s+PLATE\b"), ("SPECTACLE BLIND", r"\bSPECTACLE\s+BLIND\b"),
]

def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\x0c", " ")).strip()

def render_page(page, dpi=400):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def preprocess(img):
    g = img.convert("L")
    g = ImageEnhance.Contrast(g).enhance(1.7)
    g = g.filter(ImageFilter.SHARPEN)
    return g

def ocr(img):
    # Keep line structure; table headings are easier to reconstruct from this output.
    txt = pytesseract.image_to_string(preprocess(img), config="--oem 3 --psm 11")
    return clean(txt)

def pdf_text_available(doc):
    return sum(len(p.get_text("text").strip()) for p in doc) > 80

def page_text(page, use_ocr):
    if not use_ocr:
        txt = page.get_text("text")
        if len(txt.strip()) >= 30:
            return clean(txt)
    return ocr(render_page(page))

def grab(text, patterns):
    for p in patterns:
        m = re.search(p, text, re.I | re.M)
        if m:
            return clean(m.group(1)) if m.groups() else clean(m.group(0))
    return ""

def title_fields(text):
    # Labels in drawings are often separated from values by OCR. Use broad fallbacks.
    line = grab(text, [r"\bLINE\s*NO\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9._/\-]+)", r"\bLINE\s*NO\b[\s\S]{0,120}?\b([0-9]{2,}[A-Z0-9._/\-]+)\b"])
    drawing = grab(text, [r"\bDRAWING\s*(?:NUMBER|NO\.?)\s*[:\-]?\s*([A-Z0-9._/\-]+)", r"\b(C\d{2,}[\-A-Z0-9._]+)\b"])
    rev = grab(text, [r"\bREV\.?\s*[:\-]?\s*([A-Z0-9]+)"])
    area = grab(text, [r"\bAREA\s*[:\-]?\s*([A-Z0-9 _/&\-]+)"])
    sheet = grab(text, [r"\b(\d+)\s+OF\s+(\d+)\b", r"\bSHEET\s*[:\-]?\s*(\d+\s*(?:OF|/)\s*\d+)\b"])
    if sheet and re.fullmatch(r"\d+\s+OF\s+\d+", sheet, re.I):
        sheet = re.sub(r"\s+", " ", sheet).upper()
    return {"AREA": area, "LINE NO.": line, "DRAWING NO.": drawing, "REV.": rev, "SHEET": sheet}

def detect_sections(text):
    up = text.upper()
    positions = []
    for label in ["FABRICATION MATERIALS", "ERECTION MATERIALS", "CUT PIPE LENGTHS", "BILL OF MATERIAL"]:
        p = up.find(label)
        if p >= 0: positions.append((p, label))
    return sorted(positions)

def normalize_item(desc):
    u = desc.upper()
    for name, pat in ITEM_PATTERNS:
        if re.search(pat, u): return name
    return ""

def parse_size(desc):
    # Prefer N.S. column-like inch values; then common size notation.
    m = re.search(r"\b(?:N\.S\.?|SIZE)\s*[:.]?\s*(\d+(?:\s*[-/]\s*\d+)?)\b", desc, re.I)
    if m: return clean(m.group(1)).replace(" ", "")
    m = re.search(r"\b(\d+(?:\s*[-/]\s*\d+)?)\s*(?:INCH|IN)\b", desc, re.I)
    return clean(m.group(1)).replace(" ", "") if m else ""

def parse_schedule(desc):
    m = re.search(r"\b(SCH\.?\s*[0-9A-Z]+|SCHEDULE\s*[0-9A-Z]+|\d+#|\d+\s*#\s*/\s*\d+\s*AARH)\b", desc, re.I)
    if not m: return ""
    return clean(m.group(1)).replace("SCHEDULE", "SCH").upper()

def parse_moc_grade(desc):
    u = desc.upper()
    moc = ""
    if re.search(r"\bSUPER\s*DUPLEX\b", u): moc = "SUPER DUPLEX"
    elif re.search(r"\bDUPLEX\b", u): moc = "DUPLEX"
    elif re.search(r"\bSS\b|STAINLESS", u): moc = "SS"
    elif re.search(r"\bCS\b|CARBON\s*STEEL", u): moc = "CS"
    elif re.search(r"\bGI\b|GALVAN", u): moc = "GI"
    elif re.search(r"\bAS\b|ASBESTOS", u): moc = "AS"
    grade = ""
    patterns = [r"A\s*106\s*GR\.?\s*B", r"A\s*234\s*GR\.?\s*WPB", r"A\s*105", r"A\s*193\s*GR\.?\s*B7", r"A\s*194\s*GR\.?\s*2H", r"PTFE", r"WPB"]
    for p in patterns:
        m = re.search(p, desc, re.I)
        if m:
            grade = re.sub(r"\s+", " ", m.group(0)).strip()
            break
    return moc, grade

def extract_qty_uom(desc):
    # Quantity should generally be the final table value; protect dimensions like 90 MM.
    matches = list(re.finditer(r"(?<![A-Z0-9])([0-9]+(?:\.[0-9]+)?)\s*(M|EA|EACH|NOS?)?\s*$", desc, re.I))
    if matches:
        m = matches[-1]
        q = float(m.group(1))
        u = (m.group(2) or "EA").upper()
        if u in {"EACH", "NO", "NOS"}: u = "EA"
        return q, u, desc[:m.start()].strip()
    return "", "EA", desc

def parse_bom_rows(text, meta, section_name):
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    rows=[]; pending=[]
    # OCR often breaks one component description across 2-4 lines. Start on category/item cues.
    for i,line in enumerate(lines):
        u=line.upper()
        if u in {"PIPE","FITTINGS","FLANGES","GASKETS","BOLTS","SUPPORTS","VALVES","INSTRUMENTS"}: continue
        item=normalize_item(line)
        if not item: continue
        # Skip headings that contain an item word but no descriptive engineering data.
        if len(line) < 12 and item in {"PIPE","SUPPORT","GASKET","VALVE"}: continue
        block=line
        for j in range(1,5):
            if i+j >= len(lines): break
            nxt=lines[i+j]; nu=nxt.upper()
            if normalize_item(nxt) and (re.search(r"\b(PIPE|ELBOW|GASKET|FLANGE|BOLT|U[- ]?BOLT|VALVE)\b", nu)):
                break
            if nu.startswith(("FABRICATION MATERIALS","ERECTION MATERIALS","CUT PIPE LENGTHS","NOTES","CLIENT","PROJECT","LINE NO","DRAWING NUMBER")): break
            block += " " + nxt
            if re.search(r"\b(A\s*106|A\s*234|A\s*105|A\s*193|PTFE|WPB|SCH|B-16\.|150#|125AARH)\b", nxt, re.I):
                # usually enough evidence for this component
                break
        size=parse_size(block)
        sched=parse_schedule(block)
        moc,grade=parse_moc_grade(block)
        qty,uom,desc=extract_qty_uom(block)
        # OCR table has quantities as isolated values; recover common pattern from nearby lines.
        if qty=="":
            for j in range(i+1,min(i+8,len(lines))):
                m=re.fullmatch(r"(\d+(?:\.\d+)?)\s*(M|EA|EACH|NOS?)?",lines[j],re.I)
                if m:
                    qty=float(m.group(1)); uom=(m.group(2) or "EA").upper();
                    if uom in {"EACH","NO","NOS"}:uom="EA"
                    break
        if not size:
            m=re.search(r"\b(\d+(?:\s*[-/]\s*\d+)?)\b", block)
            if m and not re.fullmatch(r"90|45|150|125|4\.5",m.group(1)): size=m.group(1).replace(" ","")
        row={h:"" for h in HEADERS}
        row.update(meta)
        row.update({"ITEM":item,"SIZE (IN)":size,"SCHEDULE/CLASS":sched,"MOC":moc,"GRADE":grade,"DESCRIPTION":desc,"QTY":qty,"UOM":uom,"REMARKS":section_name})
        # Strong anti-duplicate signature.
        sig=(item,size,sched,grade,desc[:140],str(qty),uom,meta.get("SHEET",""))
        if sig not in [x[0] for x in pending]: pending.append((sig,row))
    rows=[x[1] for x in pending]
    return rows

def parse_cut_pipe(text, meta):
    rows=[]
    for line in [clean(x) for x in text.splitlines() if clean(x)]:
        m=re.search(r"(?:<\s*(\d+)\s*>|\b(\d+)\b)\s+(\d{2,5})\s*(?:PE/BE|BE/PE|PE|BE)\b",line,re.I)
        if not m: continue
        piece=m.group(1) or m.group(2); length=float(m.group(3)); end=re.search(r"(PE/BE|BE/PE|PE|BE)\b",line,re.I).group(1).upper()
        rows.append({**meta,"PIECE NO":piece,"CUT LENGTH":length,"N.S.":parse_size(line),"REMARKS":end})
    return rows

def validate(rows):
    review=[]; seen=set()
    for idx,r in enumerate(rows,1):
        missing=[]
        for f in ["DRAWING NO.","SHEET","ITEM","DESCRIPTION"]:
            if not r.get(f): missing.append(f)
        if r.get("QTY","")=="": missing.append("QTY")
        if missing: review.append({"row":idx,"reason":"Missing: "+", ".join(missing),"data":r})
        key=(r.get("DRAWING NO."),r.get("SHEET"),r.get("ITEM"),r.get("SIZE (IN)"),r.get("DESCRIPTION"),r.get("QTY"))
        if key in seen: review.append({"row":idx,"reason":"Possible duplicate row on same drawing/sheet","data":r})
        seen.add(key)
        if r.get("ITEM") in {"PIPE","ELBOW 90","ELBOW 45","TEE","REDUCER","FLANGE SO","FLANGE WN","BLIND FLANGE"} and not r.get("SIZE (IN)"):
            review.append({"row":idx,"reason":"Engineering item has no confidently detected N.S./size","data":r})
    return review

def extract_document(path: Path):
    ext=path.suffix.lower(); warnings=[]; page_texts=[]; rows=[]; cut=[]
    if ext==".pdf":
        doc=fitz.open(path); pages=len(doc); use_ocr=not pdf_text_available(doc)
        for p in doc: page_texts.append(page_text(p,use_ocr))
        doc.close(); dtype="image/scanned PDF" if use_ocr else "text/vector PDF"
    else:
        pages=1; page_texts=[ocr(Image.open(path).convert("RGB"))]; dtype="image"
    for page_no,text in enumerate(page_texts,1):
        meta=title_fields(text)
        if not meta["SHEET"]: meta["SHEET"]=f"{page_no} OF {pages}"
        # If OCR captured malformed line/drawing fields, use common engineering identifiers.
        if not meta["LINE NO."]:
            m=re.search(r"\b(\d{2,4}-[A-Z]{1,4}-[A-Z0-9]{2,}-\d{5,})\b",text,re.I)
            if m: meta["LINE NO."]=m.group(1)
        if not meta["DRAWING NO."]:
            m=re.search(r"\b(C\d{2,}-PI-[A-Z0-9]+-\d{5,})\b",text,re.I)
            if m: meta["DRAWING NO."]=m.group(1)
        # Section-aware extraction; retain source section in REMARKS.
        sections=detect_sections(text)
        if sections:
            for n,(start,label) in enumerate(sections):
                end=sections[n+1][0] if n+1<len(sections) else len(text)
                chunk=text[start:end]
                if "CUT PIPE LENGTHS" in label: cut.extend(parse_cut_pipe(chunk,meta))
                else: rows.extend(parse_bom_rows(chunk,meta,label))
        else:
            rows.extend(parse_bom_rows(text,meta,""))
    # Assign stable row numbers after all extraction.
    for i,r in enumerate(rows,1): r["SL NO"]=i
    review=validate(rows)
    if not rows: warnings.append("No BOM rows were confidently extracted. Review the source image and/or configure a vision-AI adapter.")
    return {"document_type":dtype,"pages":pages,"rows":rows,"cut_pipe":cut,"review":review,"warnings":warnings,"page_texts":page_texts}
