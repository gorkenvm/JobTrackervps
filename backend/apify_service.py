import os
import json
import requests
from datetime import datetime
from sqlalchemy import or_
from database import SessionLocal
import models
import settings_service
import cv_service
from llm_service import analyze_job

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'apify_config.json')

DEFAULT_CONFIG = {
    "token": "",
    "task_id": "",
    "schedule_time": "09:00",
    "enabled": False,
    "default_provider": "Gemini",
    "default_api_key": "",
    "default_model": "gemini-1.5-pro",
    "last_run": None,
    "last_imported": 0,
    "last_skipped": 0,
    "last_error": None,
    "filter_keywords": "",
    "filter_location": "",
    "filter_date_posted": "",
    "filter_max_results": 0,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def fetch_and_import() -> dict:
    """Run Apify task sync, import new jobs to DB. Returns result summary."""
    config = load_config()
    token = config.get("token", "").strip()
    task_id = config.get("task_id", "").strip()

    if not token or not task_id:
        return {"error": "Token veya Task ID eksik.", "imported": 0, "skipped": 0, "total": 0}

    # Build optional task input overrides from saved filters
    task_input = {}
    kw = config.get("filter_keywords", "").strip()
    loc = config.get("filter_location", "").strip()
    date_posted = config.get("filter_date_posted", "").strip()
    max_results = config.get("filter_max_results", 0)
    if kw:
        task_input["searchTerms"] = [k.strip() for k in kw.split(",") if k.strip()]
    if loc:
        task_input["location"] = loc
    if date_posted:
        task_input["publishedAt"] = date_posted
    if max_results and int(max_results) > 0:
        task_input["maxItems"] = int(max_results)

    # Run Apify task and collect results (sync, may take a few minutes)
    url = f"https://api.apify.com/v2/actor-tasks/{task_id}/run-sync-get-dataset-items"
    try:
        if task_input:
            resp = requests.post(url, params={"token": token}, json=task_input, timeout=600)
        else:
            resp = requests.get(url, params={"token": token}, timeout=600)
        resp.raise_for_status()
        items = resp.json()
    except requests.exceptions.Timeout:
        err = "Apify isteği zaman aşımına uğradı (10 dk). Task ID veya token'ı kontrol edin."
        _update_last_run(config, 0, 0, err)
        return {"error": err, "imported": 0, "skipped": 0, "total": 0}
    except Exception as e:
        err = str(e)
        _update_last_run(config, 0, 0, err)
        return {"error": err, "imported": 0, "skipped": 0, "total": 0}

    if not isinstance(items, list):
        err = f"Beklenmeyen Apify yanıtı: {type(items).__name__}"
        _update_last_run(config, 0, 0, err)
        return {"error": err, "imported": 0, "skipped": 0, "total": 0}

    cv_text = cv_service.get_cv_text()
    user_settings = settings_service.load()
    provider = config.get("default_provider") or user_settings.get("provider", "Gemini")
    apify_key = config.get("default_api_key", "").strip()
    settings_key = user_settings.get("api_key", "").strip()
    settings_provider = user_settings.get("provider", "Gemini")
    # Only fall back to settings key if providers match — avoids using Gemini key with OpenAI etc.
    api_key = apify_key or (settings_key if settings_provider == provider else "")
    model = config.get("default_model") or user_settings.get("model_name", "gemini-1.5-pro")
    summary_language = user_settings.get("summary_language", "TR")
    print(f"[APIFY] provider={provider}  key={'set' if api_key else 'BOŞ — analiz atlanacak'}  model={model}")

    db = SessionLocal()
    imported = skipped = analysis_errors = 0

    try:
        for item in items:
            apify_id = str(item.get("id") or item.get("jobId") or "").strip() or None
            link = str(item.get("url") or item.get("applyUrl") or "").strip() or None

            # Duplicate check by apify_id OR link
            filters = []
            if apify_id:
                filters.append(models.Job.apify_id == apify_id)
            if link:
                filters.append(models.Job.link == link)

            if filters:
                exists = db.query(models.Job).filter(or_(*filters)).first()
                if exists:
                    skipped += 1
                    continue

            description = str(item.get("description") or item.get("descriptionText") or "").strip()
            title = str(item.get("title") or "Bilinmiyor").strip()
            company = str(item.get("companyName") or "Bilinmiyor").strip()
            location = str(item.get("location") or "").strip()

            db_job = models.Job(
                apify_id=apify_id,
                title=title,
                company=company,
                description=description,
                link=link,
                location=location,
                status="Yeni",
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)

            # AI analysis (only if description + api_key available)
            if description and api_key:
                try:
                    analysis = analyze_job(
                        job_desc=description,
                        cv_text=cv_text,
                        link=link or "",
                        provider=provider,
                        api_key=api_key,
                        model_name=model,
                        summary_language=summary_language,
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
                except Exception as e:
                    print(f"LLM analiz hatası (job {db_job.id}): {e}")
                    analysis_errors += 1

            imported += 1
    finally:
        db.close()

    _update_last_run(config, imported, skipped, None)
    return {
        "imported": imported,
        "skipped": skipped,
        "analysis_errors": analysis_errors,
        "total": len(items),
    }


def fetch_single_url(job_url: str) -> dict:
    """Fetch a single LinkedIn job by URL using the configured Apify task.
    Returns raw job fields (title, company, description, location, apify_id, link).
    Raises an exception on failure.
    """
    config = load_config()
    token = config.get("token", "").strip()
    task_id = config.get("task_id", "").strip()

    if not token or not task_id:
        raise ValueError("Apify token veya Task ID eksik. Önce Apify ayarlarını kaydedin.")

    # Run the task with a single-URL input override
    url = f"https://api.apify.com/v2/actor-tasks/{task_id}/run-sync-get-dataset-items"
    try:
        resp = requests.post(
            url,
            params={"token": token},
            json={"startUrls": [{"url": job_url}]},
            timeout=300,
        )
        resp.raise_for_status()
        items = resp.json()
    except requests.exceptions.Timeout:
        raise TimeoutError("Apify isteği zaman aşımına uğradı (5 dk).")
    except Exception as e:
        raise RuntimeError(f"Apify API hatası: {e}")

    if not isinstance(items, list) or len(items) == 0:
        raise ValueError("Apify bu URL için sonuç döndürmedi. URL doğru bir LinkedIn ilanı mı?")

    item = items[0]
    return {
        "apify_id": str(item.get("id") or item.get("jobId") or "").strip() or None,
        "title": str(item.get("title") or "").strip(),
        "company": str(item.get("companyName") or "").strip(),
        "description": str(item.get("description") or item.get("descriptionText") or "").strip(),
        "location": str(item.get("location") or "").strip(),
        "link": str(item.get("url") or job_url).strip(),
    }


def _update_last_run(config: dict, imported: int, skipped: int, error):
    config["last_run"] = datetime.now().isoformat()
    config["last_imported"] = imported
    config["last_skipped"] = skipped
    config["last_error"] = error
    save_config(config)
