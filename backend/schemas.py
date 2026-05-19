from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserSettings(BaseModel):
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    download_path: str = ""
    summary_language: str = "TR"
    user_code: str = ""


class JobCreate(BaseModel):
    link: str
    description: str
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    summary_language: str = "TR"

class JobUpdateStatus(BaseModel):
    status: str

class JobUpdateDetails(BaseModel):
    title: str
    company: str

class ApifyConfig(BaseModel):
    token: str = ""
    task_id: str = ""
    schedule_time: str = "09:00"
    enabled: bool = False
    default_provider: str = "Gemini"
    default_api_key: str = ""
    default_model: str = "gemini-1.5-pro"
    last_run: Optional[str] = None
    last_imported: int = 0
    last_skipped: int = 0
    last_error: Optional[str] = None
    filter_keywords: str = ""
    filter_location: str = ""
    filter_date_posted: str = ""
    filter_max_results: int = 0


class Job(BaseModel):
    id: int
    apify_id: Optional[str] = None
    title: str
    company: str
    description: Optional[str] = None
    link: Optional[str] = None
    status: str
    score: Optional[int] = None
    motivation_letter: Optional[str] = None
    summary_tr: Optional[str] = None
    language_reqs: Optional[str] = None
    language_explanation: Optional[str] = None
    location: Optional[str] = None
    score_breakdown: Optional[str] = None
    cv_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class LetterRequest(BaseModel):
    job_id: int
    language: str
    draft: str
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    company_research: str = ""

class ExportRequest(BaseModel):
    letter_text: str
    company_name: str
    job_title: str = ""
    download_path: str
    job_id: int = 0
    user_code: str = ""

class CVExportRequest(BaseModel):
    job_id: int
    company_name: str
    download_path: str
    user_code: str = ""

class FetchUrlRequest(BaseModel):
    url: str

class CVInfo(BaseModel):
    id: str
    name: str
    filename: str
    has_file: bool
    is_active: bool

class CVAddRequest(BaseModel):
    name: str

class CVRenameRequest(BaseModel):
    name: str

class CVSummaryRequest(BaseModel):
    job_id: int
    cv_id: str = ""
    language: str = "EN"
    draft: str = ""
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    max_chars: int = 680

class CVRecompileRequest(BaseModel):
    job_id: int
    cv_id: str = ""
    summary_text: str

class BothRequest(BaseModel):
    job_id: int
    cv_id: str = ""
    language: str = "EN"
    draft: str = ""
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    max_chars: int = 680
    company_research: str = ""
