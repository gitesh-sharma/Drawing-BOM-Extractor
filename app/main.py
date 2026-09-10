from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import shutil, uuid
from .extractor import extract_document
from .excel_export import export_bom, HEADERS

BASE=Path(__file__).resolve().parent.parent; UPLOADS=BASE/"uploads"; OUTPUTS=BASE/"outputs"
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)
app=FastAPI(title="BOM Drawing Extractor V2",version="2.0")
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
@app.get("/")
def home(): return FileResponse(BASE/"static"/"index.html")

@app.post("/api/extract-batch")
async def extract_batch(files:list[UploadFile]=File(...)):
    allowed={".pdf",".png",".jpg",".jpeg",".webp",".tif",".tiff"}
    batch=uuid.uuid4().hex; all_rows=[]; all_cut=[]; all_review=[]; docs=[]; warnings=[]
    for f in files:
        ext=Path(f.filename or "").suffix.lower()
        if ext not in allowed: raise HTTPException(400,f"Unsupported file type: {ext}")
        job=uuid.uuid4().hex; source=UPLOADS/f"{job}{ext}"
        with source.open("wb") as out: shutil.copyfileobj(f.file,out)
        result=extract_document(source)
        docs.append({"filename":f.filename,"pages":result["pages"],"rows":len(result["rows"]),"review":len(result["review"]),"document_type":result["document_type"]})
        for r in result["rows"]:
            r["SOURCE FILE"]=f.filename
            all_rows.append(r)
        for r in result.get("cut_pipe",[]):
            r["SOURCE FILE"]=f.filename; all_cut.append(r)
        for x in result["review"]:
            x["filename"]=f.filename; all_review.append(x)
        warnings += [f"{f.filename}: {w}" for w in result["warnings"]]
    # Consolidated BOM: preserve drawing + sheet traceability. Aggregate only exact same source keys if desired later.
    for i,r in enumerate(all_rows,1): r["SL NO"]=i
    result={"rows":all_rows,"cut_pipe":all_cut,"review":all_review,"warnings":warnings,"pages":sum(d["pages"] for d in docs),"document_type":"batch" ,"page_texts":[]}
    xlsx=OUTPUTS/f"BOM_CONSOLIDATED_{batch[:8]}.xlsx"; export_bom(result,xlsx)
    return {"batch_id":batch,"documents":docs,"rows":len(all_rows),"cut_pipe":len(all_cut),"review_count":len(all_review),"warnings":warnings,"download":f"/api/download/{xlsx.name}"}

@app.get("/api/download/{name}")
def download(name:str):
    p=OUTPUTS/name
    if not p.exists(): raise HTTPException(404,"File not found")
    return FileResponse(p,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",filename=p.name)
