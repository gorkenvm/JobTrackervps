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

    kw = config.get("filter_keywords", "").strip()
    loc = config.get("filter_location", "").strip()
    date_posted = config.get("filter_date_posted", "").strip()
    max_results = config.get("filter_max_results", 0)

    # Resolve actor ID + saved task input (enables direct actor call with full input control)
    act_id = ""
    saved_input = {}
    try:
        td = requests.get(
            f"https://api.apify.com/v2/actor-tasks/{task_id}",
            params={"token": token},
            timeout=30,
        )
        td.raise_for_status()
        task_data = td.json().get("data", {})
        act_id = task_data.get("actId", "")
        saved_input = dict(task_data.get("input") or {})
        print(f"[APIFY] Task çözümlendi: actId={act_id}  saved_input keys={list(saved_input.keys())}")
    except Exception as e:
        print(f"[APIFY] Task detayı alınamadı ({e}), task endpoint'e fallback.")

    # Build overrides — detect which field name the actor uses for max results
    overrides = {}
    if kw:
        overrides["searchTerms"] = [k.strip() for k in kw.split(",") if k.strip()]
    if loc:
        overrides["location"] = loc
    if date_posted:
        overrides["publishedAt"] = date_posted
    if max_results and int(max_results) > 0:
        n = int(max_results)
        for field in ("maxItems", "count", "resultsLimit", "limit", "total"):
            if field in saved_input:
                overrides[field] = n
                print(f"[APIFY] Max sonuç: {field}={n} (task input'tan tespit edildi)")
                break
        else:
            overrides["maxItems"] = n
            print(f"[APIFY] Max sonuç: maxItems={n} (varsayılan)")

    # Run and collect results
    try:
        if act_id:
            # Call actor directly with merged input — full control over all fields
            final_input = {**saved_input, **overrides}
            run_url = f"https://api.apify.com/v2/acts/{act_id}/run-sync-get-dataset-items"
            print(f"[APIFY] Aktör doğrudan çağrılıyor, input={list(final_input.keys())}")
            resp = requests.post(run_url, params={"token": token}, json=final_input, timeout=600)
        elif overrides:
            run_url = f"https://api.apify.com/v2/actor-tasks/{task_id}/run-sync-get-dataset-items"
            resp = requests.post(run_url, params={"token": token}, json=overrides, timeout=600)
        else:
            run_url = f"https://api.apify.com/v2/actor-tasks/{task_id}/run-sync-get-dataset-items"
            resp = requests.get(run_url, params={"token": token}, timeout=600)
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
    apify_provider = config.get("default_provider", "").strip()
    apify_key = config.get("default_api_key", "").strip()
    # Use Apify-specific provider+key only when BOTH are explicitly set; otherwise use main Settings
    if apify_provider and apify_key:
        provider = apify_provider
        api_key = apify_key
    else:
        provider = user_settings.get("provider", "Gemini")
        api_key = user_settings.get("api_key", "")
    model = config.get("default_model", "").strip() or user_settings.get("model_name", "gemini-1.5-pro")
    summary_language = user_settings.get("summary_language", "TR")
    print(f"[APIFY] provider={provider}  key={'set' if api_key else 'BOŞ — analiz atlanacak'}  model={model}")

    db = SessionLocal()
    imported = skipped = analysis_errors = 0
    print(f"[APIFY] Toplam {len(items)} item işlenecek.")

    try:
        for idx, item in enumerate(items):
            apify_id = str(item.get("id") or item.get("jobId") or "").strip() or None
            link = str(item.get("url") or item.get("apifyUrl") or item.get("applyUrl") or "").strip() or None
            title_raw = str(item.get("title") or "?").strip()
            print(f"[APIFY] [{idx+1}/{len(items)}] '{title_raw}'  apify_id={apify_id}  link={link}")

            # Duplicate check by apify_id OR link
            filters = []
            if apify_id:
                filters.append(models.Job.apify_id == apify_id)
            if link:
                filters.append(models.Job.link == link)

            if filters:
                exists = db.query(models.Job).filter(or_(*filters)).first()
                if exists:
                    print(f"[APIFY]   → DUPLICATE (db id={exists.id}), atlanıyor.")
                    skipped += 1
                    continue

            description = str(item.get("description") or item.get("descriptionText") or "").strip()
            title = str(item.get("title") or "Bilinmiyor").strip()
            company = str(item.get("companyName") or "Bilinmiyor").strip()
            location = str(item.get("location") or "").strip()
            print(f"[APIFY]   → YENİ iş: company={company}  desc_len={len(description)}")

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
            print(f"[APIFY]   → DB'ye eklendi id={db_job.id}")

            # AI analysis (only if description + api_key available)
            if not description:
                print(f"[APIFY]   → Açıklama YOK, analiz atlanıyor.")
            elif not api_key:
                print(f"[APIFY]   → API key YOK, analiz atlanıyor.")
            else:
                print(f"[APIFY]   → analyze_job çağrılıyor (provider={provider}, model={model}) ...")
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
                    print(f"[APIFY]   → Analiz döndü: score={analysis.get('score')}  keys={list(analysis.keys())}")
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
                    print(f"[APIFY]   → DB güncellendi (score={db_job.score}).")
                except Exception as e:
                    import traceback
                    print(f"[APIFY]   → LLM analiz hatası (job {db_job.id}): {e}")
                    traceback.print_exc()
                    analysis_errors += 1

            imported += 1
    finally:
        db.close()
    print(f"[APIFY] Bitti: imported={imported}  skipped={skipped}  analysis_errors={analysis_errors}")

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
