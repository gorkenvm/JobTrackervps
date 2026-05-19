import os
import json
import subprocess
import shutil
import tempfile
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import models
import schemas
import apify_service
import settings_service
import cv_service
from database import engine, get_db
from llm_service import analyze_job, generate_motivation_letter, generate_cv_summary, generate_both
from fpdf import FPDF
import re

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Tracker API")
scheduler = BackgroundScheduler(timezone="Europe/Berlin")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(BASE_DIR, "sample.txt")
PREVIEW_DIR = os.path.join(BASE_DIR, "preview")
os.makedirs(PREVIEW_DIR, exist_ok=True)


def _safe_filename(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', (s or "").strip()) or "Unknown"



_UNICODE_REPLACEMENTS = {
    '—': '-', '–': '-', '−': '-',
    '‘': "'", '’': "'",
    '“': '"', '”': '"', '„': '"',
    '…': '...', '•': '-', ' ': ' ',
    '­': '', '→': '->', '←': '<-',
    '·': '.', '‑': '-', '‐': '-',
}

def _sanitize_for_pdf(text: str) -> str:
    for ch, repl in _UNICODE_REPLACEMENTS.items():
        text = text.replace(ch, repl)
    return text.encode('latin-1', errors='replace').decode('latin-1')


def _save_text_as_pdf(text: str, filepath: str):
    text = _sanitize_for_pdf(text)
    pdf = FPDF(format="A4")
    pdf.set_margins(left=25, top=25, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    w = pdf.epw  # effective page width — set_margins'tan sonra geçerli değer
    for line in text.split("\n"):
        if line.strip():
            pdf.multi_cell(w=w, h=7, text=line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.ln(4)
    pdf.output(filepath)


_MIKTEX_PDFLATEX = r"C:\Users\gorke\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"

_LATEX_ESCAPE_MAP = {
    '\\': r'\textbackslash{}',
    '{': r'\{', '}': r'\}',
    '$': r'\$', '&': r'\&', '#': r'\#',
    '^': r'\^{}', '_': r'\_', '~': r'\textasciitilde{}', '%': r'\%',
}
_LATEX_ESCAPE_RE = re.compile(r'[\\{}\$&#\^_~%]')


def _escape_latex(text: str) -> str:
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group()], text)


_MD_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')


def _apply_bold(text: str) -> str:
    """Convert **keyword** markers (from AI) to \\textbf{keyword} for LaTeX.
    Must be called AFTER _escape_latex so special chars inside keywords are
    already safe (e.g. **90\\%+** → \\textbf{90\\%+})."""
    return _MD_BOLD_RE.sub(r'\\textbf{\1}', text)


_LETTER_TEX_TEMPLATE = r"""\documentclass[letterpaper,10pt]{article}
\usepackage[english]{babel}
\usepackage[utf8]{inputenc}
\usepackage{fontawesome}
\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage{ragged2e}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\begin{document}

%-----------HEADING-----------
\begin{center}
    \textbf{\Huge \scshape VEYSEL MURAT GORKEN} \\ \vspace{5pt}
    \small
    \faMapMarker\ Dortmund, Germany (open to relocation) $|$ Work authorized  \\ \vspace{2pt}
    \textcolor{blue}{\faLinkedin} \href{https://www.linkedin.com/in/vmgorken/}{vmgorken} $|$
    \textcolor{blue}{\faGithub} \href{https://github.com/gorkenvm}{gorkenvm} $|$
    \faPhone\ +49 151 253 20930 $|$
    gorkenvm@gmail.com
\end{center}

\vspace{20pt}

%-----------RECIPIENT-----------
\begin{flushleft}
    \textbf{Date:} \today \\
    \vspace{10pt}
    \textbf{To:} Hiring Team \\
    %%COMPANY%%
\end{flushleft}

\vspace{15pt}

%-----------SUBJECT-----------
\textbf{Re:} %%POSITION%% --- Application

\vspace{15pt}

%-----------BODY-----------
\justify
%%BODY%%

\end{document}
"""


def _build_letter_body_tex(letter_text: str) -> str:
    """Convert plain-text motivation letter paragraphs to LaTeX body content."""
    blocks = [b.strip() for b in re.split(r'\n\s*\n', letter_text.strip()) if b.strip()]
    closing_kws = ('best regards', 'mit freundlichen', 'sincerely', 'yours sincerely')
    parts = []
    for i, block in enumerate(blocks):
        is_closing = any(block.lower().startswith(kw) for kw in closing_kws)
        if is_closing:
            lines = [_escape_latex(ln.strip()) for ln in block.split('\n') if ln.strip()]
            parts.append(r'\vspace{20pt}' + '\n' + ' \\\\\n'.join(lines))
        elif i == 0:
            parts.append(_escape_latex(block.replace('\n', ' ')))
        else:
            parts.append(r'\vspace{10pt}' + '\n' + _escape_latex(block.replace('\n', ' ')))
    return '\n\n'.join(parts)


def _build_motivation_letter_tex(letter_text: str, company: str, position: str) -> str:
    """Inject plain-text letter into the fixed LaTeX motivation letter template."""
    tex = _LETTER_TEX_TEMPLATE
    tex = tex.replace('%%COMPANY%%', _escape_latex(company))
    tex = tex.replace('%%POSITION%%', _escape_latex(position))
    tex = tex.replace('%%BODY%%', _build_letter_body_tex(letter_text))
    return tex


def _compile_latex_to(tex_content: str, output_path: str) -> bool:
    """Compile LaTeX content to PDF and save to output_path. Returns True on success."""
    cmd = _pdflatex_cmd()
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "doc.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
        try:
            result = subprocess.run(
                [cmd, "-interaction=nonstopmode", "doc.tex"],
                cwd=tmpdir, capture_output=True, timeout=60, check=False
            )
            pdf_src = os.path.join(tmpdir, "doc.pdf")
            if os.path.exists(pdf_src):
                shutil.copy2(pdf_src, output_path)
                return True
            log = result.stdout.decode("utf-8", errors="replace")[-800:]
            print(f"pdflatex output:\n{log}")
        except FileNotFoundError:
            print(f"pdflatex not found (tried: {cmd})")
        except subprocess.TimeoutExpired:
            print("pdflatex timeout (60s)")
        except Exception as e:
            print(f"Compile error: {e}")
    return False


def _pdflatex_cmd() -> str:
    import shutil as _shutil
    if _shutil.which("pdflatex"):
        return "pdflatex"
    if os.path.isfile(_MIKTEX_PDFLATEX):
        return _MIKTEX_PDFLATEX
    return "pdflatex"


def _compile_latex(tex_content: str, job_id: int):
    cmd = _pdflatex_cmd()
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "cv.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
        try:
            result = subprocess.run(
                [cmd, "-interaction=nonstopmode", "cv.tex"],
                cwd=tmpdir, capture_output=True, timeout=60, check=False
            )
            pdf_src = os.path.join(tmpdir, "cv.pdf")
            if os.path.exists(pdf_src):
                dest = os.path.join(PREVIEW_DIR, f"preview_{job_id}.pdf")
                shutil.copy2(pdf_src, dest)
                return dest
            log = result.stdout.decode("utf-8", errors="replace")[-800:]
            print(f"pdflatex çıktı (son 800 karakter):\n{log}")
        except FileNotFoundError:
            print(f"pdflatex bulunamadı (denenen: {cmd}). Windows: https://miktex.org/ | Linux: apt install texlive-latex-base")
        except subprocess.TimeoutExpired:
            print("pdflatex zaman aşımı (60s)")
        except Exception as e:
            print(f"Derleme hatası: {e}")
    return None


def _apply_apify_schedule(config: dict):
    scheduler.remove_all_jobs()
    if config.get("enabled") and config.get("schedule_time"):
        try:
            h, m = config["schedule_time"].split(":")
            scheduler.add_job(
                apify_service.fetch_and_import,
                CronTrigger(hour=int(h), minute=int(m)),
                id="apify_daily",
                replace_existing=True,
            )
            print(f"Apify zamanlandı: her gün {config['schedule_time']}")
        except Exception as e:
            print(f"Zamanlama hatası: {e}")


@app.on_event("startup")
def on_startup():
    # DB migrations
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS language_explanation TEXT"))
            conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apify_id VARCHAR UNIQUE"))
            conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS score_breakdown TEXT"))
            conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cv_summary TEXT"))
            conn.commit()
    except Exception as e:
        print(f"Migration uyarısı: {e}")

    # Start scheduler with saved config
    config = apify_service.load_config()
    _apply_apify_schedule(config)
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.post("/jobs/", response_model=schemas.Job)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    db_job = models.Job(
        title="Yükleniyor...",
        company="Yükleniyor...",
        description=job.description,
        link=job.link,
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    cv_content = cv_service.get_cv_text()

    analysis = analyze_job(
        job_desc=job.description,
        cv_text=cv_content,
        link=job.link,
        provider=job.provider,
        api_key=job.api_key,
        model_name=job.model_name,
        summary_language=job.summary_language,
    )
    db_job.title = analysis.get("title", "Bilinmiyor")
    db_job.company = analysis.get("company", "Bilinmiyor")
    db_job.summary_tr = analysis.get("summary_tr", "")
    db_job.language_reqs = analysis.get("language_reqs", "")
    db_job.language_explanation = analysis.get("language_explanation", "")
    db_job.location = analysis.get("location", "")
    db_job.score = analysis.get("score", 0)
    breakdown = analysis.get("score_breakdown")
    if breakdown:
        db_job.score_breakdown = json.dumps(breakdown, ensure_ascii=False)
    db.commit()
    db.refresh(db_job)
    return db_job


@app.get("/jobs/", response_model=list[schemas.Job])
def get_jobs(db: Session = Depends(get_db)):
    return db.query(models.Job).order_by(models.Job.created_at.desc()).all()


@app.post("/jobs/{job_id}/analyze", response_model=schemas.Job)
def reanalyze_job(job_id: int, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not db_job.description:
        raise HTTPException(status_code=400, detail="İlanda açıklama yok, analiz yapılamaz.")
    user_settings = settings_service.load()
    cv_content = cv_service.get_cv_text()
    analysis = analyze_job(
        job_desc=db_job.description,
        cv_text=cv_content,
        link=db_job.link or "",
        provider=user_settings.get("provider", "Gemini"),
        api_key=user_settings.get("api_key", ""),
        model_name=user_settings.get("model_name", "gemini-1.5-pro"),
        summary_language=user_settings.get("summary_language", "TR"),
    )
    db_job.title = analysis.get("title") or db_job.title
    db_job.company = analysis.get("company") or db_job.company
    db_job.score = analysis.get("score", 0)
    db_job.summary_tr = analysis.get("summary_tr", "")
    db_job.language_reqs = analysis.get("language_reqs", "")
    db_job.language_explanation = analysis.get("language_explanation", "")
    db_job.location = analysis.get("location") or db_job.location
    breakdown = analysis.get("score_breakdown")
    if breakdown:
        db_job.score_breakdown = json.dumps(breakdown, ensure_ascii=False)
    db.commit()
    db.refresh(db_job)
    return db_job


@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(db_job)
    db.commit()
    return {"message": "Job deleted"}


@app.put("/jobs/{job_id}/status", response_model=schemas.Job)
def update_job_status(job_id: int, status_update: schemas.JobUpdateStatus, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_job.status = status_update.status
    db.commit()
    db.refresh(db_job)
    return db_job


@app.put("/jobs/{job_id}/details", response_model=schemas.Job)
def update_job_details(job_id: int, details_update: schemas.JobUpdateDetails, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_job.title = details_update.title
    db_job.company = details_update.company
    db.commit()
    db.refresh(db_job)
    return db_job


# ── CV ────────────────────────────────────────────────────────────────────────

@app.get("/cv/list", response_model=list[schemas.CVInfo])
def list_cvs():
    return cv_service.list_cvs()


@app.post("/cv/add", response_model=schemas.CVInfo)
def add_cv(req: schemas.CVAddRequest):
    return cv_service.add_cv(req.name)


@app.post("/cv/{cv_id}/upload")
async def upload_cv_file(cv_id: str, file: UploadFile = File(...)):
    content = await file.read()
    if not cv_service.upload_file(cv_id, content, file.filename or "cv.md"):
        raise HTTPException(status_code=404, detail="CV not found")
    return {"message": "OK"}


@app.put("/cv/{cv_id}/name")
def rename_cv(cv_id: str, req: schemas.CVRenameRequest):
    if not cv_service.rename(cv_id, req.name):
        raise HTTPException(status_code=404, detail="CV not found")
    return {"message": "OK"}


@app.put("/cv/{cv_id}/activate")
def activate_cv(cv_id: str):
    if not cv_service.activate(cv_id):
        raise HTTPException(status_code=404, detail="CV not found")
    return {"message": "OK"}


@app.delete("/cv/{cv_id}")
def delete_cv(cv_id: str):
    if not cv_service.delete(cv_id):
        raise HTTPException(status_code=404, detail="CV not found")
    return {"message": "OK"}


@app.get("/cv/status")
def get_cv_status():
    cvs = cv_service.list_cvs()
    return {"has_cv": any(c["has_file"] for c in cvs)}


@app.post("/sample/upload")
async def upload_sample(file: UploadFile = File(...)):
    content = await file.read()
    with open(SAMPLE_PATH, "wb") as f:
        f.write(content)
    return {"message": "Sample letter uploaded successfully"}


@app.get("/sample/status")
def get_sample_status():
    return {"has_sample": os.path.exists(SAMPLE_PATH)}


# ── Letter ────────────────────────────────────────────────────────────────────

@app.post("/generate/letter")
def generate_letter(req: schemas.LetterRequest, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == req.job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    cv_content = cv_service.get_cv_text()
    if not cv_content:
        raise HTTPException(status_code=400, detail="Please upload a CV first")

    letter_text = generate_motivation_letter(
        job_desc=db_job.description,
        cv_text=cv_content,
        language=req.language,
        draft=req.draft,
        provider=req.provider,
        api_key=req.api_key,
        model_name=req.model_name,
        company_research=req.company_research,
    )

    db_job.motivation_letter = letter_text
    db.commit()
    db.refresh(db_job)
    return {"letter": letter_text}


@app.post("/generate/both")
def generate_both_endpoint(req: schemas.BothRequest, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == req.job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    cv_path = cv_service.get_cv_path(req.cv_id if req.cv_id else None)
    if not cv_path or not os.path.exists(cv_path):
        raise HTTPException(status_code=400, detail="CV bulunamadı. Lütfen önce bir CV yükleyin.")

    cv_without_summary = None
    if cv_path.endswith(".tex"):
        with open(cv_path, "r", encoding="utf-8", errors="replace") as f:
            tex_content = f.read()
        _, cv_without_summary, cv_plain_text = cv_service.parse_latex_cv(tex_content)
    else:
        cv_plain_text = cv_service.get_cv_text(req.cv_id if req.cv_id else None)
        if not cv_plain_text:
            raise HTTPException(status_code=400, detail="CV bulunamadı. Lütfen önce bir CV yükleyin.")

    cv_text = cv_service.get_cv_text(req.cv_id if req.cv_id else None)

    result = generate_both(
        job_desc=db_job.description or "",
        cv_plain_text=cv_plain_text,
        cv_text=cv_text,
        language=req.language,
        draft=req.draft,
        max_chars=req.max_chars,
        company_research=req.company_research,
        provider=req.provider,
        api_key=req.api_key,
        model_name=req.model_name,
    )

    summary = result.get("summary", "")
    letter = result.get("letter", "")

    pdf_url = None
    if summary and cv_without_summary and "[PLACEHOLDER]" in cv_without_summary:
        full_cv = cv_without_summary.replace("[PLACEHOLDER]", _apply_bold(_escape_latex(summary)), 1)
        compiled = _compile_latex(full_cv, req.job_id)
        if compiled:
            pdf_url = f"/cv/preview/{req.job_id}"
    else:
        full_cv = cv_plain_text

    db_job.cv_summary = summary
    db_job.motivation_letter = letter
    db.commit()
    db.refresh(db_job)

    return {"summary": summary, "letter": letter, "full_cv": full_cv, "pdf_url": pdf_url}


@app.post("/generate/cv-summary")
def generate_cv_summary_endpoint(req: schemas.CVSummaryRequest, db: Session = Depends(get_db)):
    db_job = db.query(models.Job).filter(models.Job.id == req.job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    cv_path = cv_service.get_cv_path(req.cv_id if req.cv_id else None)
    if not cv_path or not os.path.exists(cv_path):
        raise HTTPException(status_code=400, detail="CV bulunamadı. Lütfen önce bir CV yükleyin.")

    cv_without_summary = None
    if cv_path.endswith(".tex"):
        with open(cv_path, "r", encoding="utf-8", errors="replace") as f:
            tex_content = f.read()
        _, cv_without_summary, cv_plain_text = cv_service.parse_latex_cv(tex_content)
    else:
        cv_plain_text = cv_service.get_cv_text(req.cv_id if req.cv_id else None)
        if not cv_plain_text:
            raise HTTPException(status_code=400, detail="CV bulunamadı. Lütfen önce bir CV yükleyin.")

    summary = generate_cv_summary(
        job_desc=db_job.description or "",
        cv_plain_text=cv_plain_text,
        language=req.language,
        draft=req.draft,
        provider=req.provider,
        api_key=req.api_key,
        model_name=req.model_name,
        max_chars=req.max_chars,
    )

    pdf_url = None
    if cv_without_summary and "[PLACEHOLDER]" in cv_without_summary:
        full_cv = cv_without_summary.replace("[PLACEHOLDER]", _apply_bold(_escape_latex(summary)), 1)
        compiled = _compile_latex(full_cv, req.job_id)
        if compiled:
            pdf_url = f"/cv/preview/{req.job_id}"
    else:
        full_cv = cv_plain_text

    db_job.cv_summary = summary
    db.commit()

    return {"summary": summary, "full_cv": full_cv, "pdf_url": pdf_url}


@app.post("/generate/cv-recompile")
def recompile_cv_endpoint(req: schemas.CVRecompileRequest, db: Session = Depends(get_db)):
    cv_path = cv_service.get_cv_path(req.cv_id if req.cv_id else None)
    if not cv_path or not cv_path.endswith(".tex") or not os.path.exists(cv_path):
        raise HTTPException(status_code=400, detail="LaTeX (.tex) CV bulunamadı. CV yönetiminden bir .tex dosyası yükleyin.")
    with open(cv_path, "r", encoding="utf-8", errors="replace") as f:
        tex_content = f.read()
    _, cv_without_summary, _ = cv_service.parse_latex_cv(tex_content)
    if "[PLACEHOLDER]" not in cv_without_summary:
        raise HTTPException(status_code=400, detail="CV'de özet bölümü tespit edilemedi.")
    full_cv = cv_without_summary.replace("[PLACEHOLDER]", _apply_bold(_escape_latex(req.summary_text)), 1)
    compiled = _compile_latex(full_cv, req.job_id)
    if not compiled:
        raise HTTPException(
            status_code=500,
            detail="pdflatex bulunamadı veya derleme başarısız. Windows için MiKTeX kurun: https://miktex.org/ — Kurulumdan sonra uygulamayı yeniden başlatın."
        )
    db_job = db.query(models.Job).filter(models.Job.id == req.job_id).first()
    if db_job:
        db_job.cv_summary = req.summary_text
        db.commit()
    return {"pdf_url": f"/cv/preview/{req.job_id}"}


@app.get("/cv/preview/{job_id}")
def get_cv_preview(job_id: int, download: bool = False):
    pdf_path = os.path.join(PREVIEW_DIR, f"preview_{job_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Preview not found")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        pdf_path, media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="cv_preview_{job_id}.pdf"'}
    )


@app.post("/export/letter")
def export_letter(req: schemas.ExportRequest):
    if not req.download_path or not os.path.exists(req.download_path):
        raise HTTPException(status_code=400, detail="Invalid or missing download path.")
    user_part = _safe_filename(req.user_code) if req.user_code else "User"
    company_part = _safe_filename(req.company_name)
    filename = f"Motivation_Letter_{user_part}_{company_part}.pdf"
    full_path = os.path.join(req.download_path, filename)
    try:
        tex = _build_motivation_letter_tex(req.letter_text, req.company_name, req.job_title or req.company_name)
        ok = _compile_latex_to(tex, full_path)
        if not ok:
            _save_text_as_pdf(req.letter_text, full_path)
        return {"saved_path": full_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {e}")


@app.post("/export/cv")
def export_cv(req: schemas.CVExportRequest):
    if not req.download_path or not os.path.exists(req.download_path):
        raise HTTPException(status_code=400, detail="Invalid or missing download path.")
    pdf_src = os.path.join(PREVIEW_DIR, f"preview_{req.job_id}.pdf")
    if not os.path.exists(pdf_src):
        raise HTTPException(status_code=404, detail="CV PDF bulunamadı. Önce CV Özeti oluşturun.")
    user_part = _safe_filename(req.user_code) if req.user_code else "User"
    company_part = _safe_filename(req.company_name)
    filename = f"001_CV_{user_part}_{company_part}.pdf"
    full_path = os.path.join(req.download_path, filename)
    try:
        shutil.copy2(pdf_src, full_path)
        return {"saved_path": full_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to copy PDF: {e}")


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings", response_model=schemas.UserSettings)
def get_settings():
    return settings_service.load()


@app.post("/settings", response_model=schemas.UserSettings)
def save_settings(s: schemas.UserSettings):
    settings_service.save(s.model_dump())
    return s.model_dump()


# ── Apify ─────────────────────────────────────────────────────────────────────

@app.get("/apify/config", response_model=schemas.ApifyConfig)
def get_apify_config():
    return apify_service.load_config()


@app.post("/apify/config", response_model=schemas.ApifyConfig)
def save_apify_config(cfg: schemas.ApifyConfig):
    old = apify_service.load_config()
    merged = {**old, **cfg.model_dump()}
    apify_service.save_config(merged)
    _apply_apify_schedule(merged)
    return merged


@app.post("/apify/fetch")
def manual_apify_fetch(background_tasks: BackgroundTasks):
    background_tasks.add_task(apify_service.fetch_and_import)
    return {"status": "started"}


@app.post("/apify/fetch-url")
def fetch_job_by_url(req: schemas.FetchUrlRequest):
    """Fetch a single LinkedIn job by URL via Apify and return its raw fields."""
    try:
        data = apify_service.fetch_single_url(req.url)
        return data
    except (ValueError, TimeoutError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
