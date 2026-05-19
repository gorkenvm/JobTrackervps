import os
import json
import google.generativeai as genai
from openai import OpenAI
import anthropic


def call_llm(prompt: str, provider: str, api_key: str, model_name: str, is_json: bool = False) -> str:
    if provider == "OpenAI":
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"} if is_json else None,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    elif provider == "Claude":
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    else:  # Default to Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        config = genai.GenerationConfig(response_mime_type="application/json") if is_json else None
        response = model.generate_content(prompt, generation_config=config)
        return response.text


def analyze_job(job_desc: str, cv_text: str, link: str = "", provider: str = "Gemini", api_key: str = "", model_name: str = "gemini-1.5-pro", summary_language: str = "TR") -> dict:
    lang_map = {"TR": "Turkish", "EN": "English", "DE": "German"}
    summary_lang_name = lang_map.get(summary_language, "Turkish")

    prompt = f"""
    You are an expert HR recruiter and career assistant.
    Analyze the following job application against the provided CV.

    Job Link: {link}
    Job Description:
    {job_desc}

    Applicant CV:
    {cv_text}

    CRITICAL LANGUAGE RULE: Write ALL text fields (summary_tr, language_explanation, and every score_breakdown note) in {summary_lang_name}. Do NOT use any other language for these fields.

    Return a JSON object with exactly these fields:

    - "title": Job title extracted from the description. If unknown, use "Bilinmiyor".
    - "company": Company name extracted from the description. If unknown, use "Bilinmiyor".
    - "summary_tr": A professional, high-density summary in {summary_lang_name} (max 400 words). Use EXACTLY these labeled sections, each on its own line separated by a newline:
        [Sektör]: Company's industry and domain.
        [Rol]: Core purpose of the position.
        [Beklentiler]: Key responsibilities and required seniority level.
        [Teknoloji]: Main tools, languages, and frameworks required.
        [Güçlü Yönler]: Top 3 strengths from the CV that match this role.
        [Eksikler]: Top 3 gaps or missing requirements relative to this role.
        Avoid filler words. Focus on hard facts only. Each section MUST start on a new line.
    - "language_reqs": Language requirements in 'DE: [Level] / ENG: [Level]' format (e.g., DE: B2 / ENG: C1). If none stated, return "Belirtilmemiş".
    - "language_explanation": 1-2 sentences in {summary_lang_name} explaining how you determined the language levels.
    - "location": Extracted job location (e.g., Berlin, Remote). If unknown, use "Bilinmiyor".
    - "score": Integer 0-100. Compatibility score based on weighted evaluation below. Do NOT just match keywords — analyze depth of experience.
    - "score_breakdown": Object with per-category integer scores and a 1-sentence note in {summary_lang_name}:
        {{
            "technical": {{"score": <integer 0-40>, "max": 40, "note": "<1 sentence in {summary_lang_name}>"}},
            "seniority": {{"score": <integer 0-30>, "max": 30, "note": "<1 sentence in {summary_lang_name}>"}},
            "industry":  {{"score": <integer 0-15>, "max": 15, "note": "<1 sentence in {summary_lang_name}>"}},
            "education": {{"score": <integer 0-15>, "max": 15, "note": "<1 sentence in {summary_lang_name}>"}}
        }}
        Weighting rules:
        - technical (max 40): Alignment of tools, languages, frameworks.
        - seniority (max 30): Years of experience and responsibility level vs. job requirements.
        - industry (max 15): Relevant sector experience.
        - education (max 15): Degree and language prerequisites.
        The sum of the four scores MUST equal the "score" field exactly.
        Final score must reflect realistic hiring probability. If a mandatory skill (e.g., German for a German-only role) is missing, penalize heavily.
    """
    try:
        response_text = call_llm(prompt, provider, api_key, model_name, is_json=True)
        data = json.loads(response_text)
        return data
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return {
            "title": "Analiz Edilemedi",
            "company": "Analiz Edilemedi",
            "summary_tr": "Analysis failed.",
            "language_reqs": "Bilinmiyor",
            "language_explanation": "",
            "location": "Bilinmiyor",
            "score": 0
        }


def generate_cv_summary(job_desc: str, cv_plain_text: str, language: str = "EN", draft: str = "", provider: str = "Gemini", api_key: str = "", model_name: str = "gemini-1.5-pro", max_chars: int = 680) -> str:
    print("\n" + "="*60)
    print(f"[CV SUMMARY] provider={provider}  model={model_name}  lang={language}  max_chars={max_chars}")
    print(f"[CV SUMMARY] draft={'(var)' if draft and draft.strip() else '(yok)'}")
    print(f"[CV SUMMARY] job_desc  ({len(job_desc)} karakter):\n{job_desc}{'...' if len(job_desc)>400 else ''}")
    print(f"[CV SUMMARY] cv_plain_text ({len(cv_plain_text)} karakter):\n{cv_plain_text}{'...' if len(cv_plain_text)>600 else ''}")
    print("="*60 + "\n")

    lang_name = "English" if language == "EN" else "German"
    draft_block = f"\n\n--- CANDIDATE NOTES (must incorporate naturally) ---\n{draft.strip()}" if draft and draft.strip() else ""
    safe_low = max(max_chars - 60, max_chars * 9 // 10)  # aim for safe_low–max_chars range

    prompt = f"""You are a senior technical recruiter and CV writer specializing in the German tech job market (Data Science, AI/ML, Data Engineering roles). You have placed candidates at SAP, Bosch, Zalando, BMW, Delivery Hero, and Berlin/Munich AI startups. You know exactly how German HR teams and ATS systems (Workday, SAP SuccessFactors, Personio, SmartRecruiters) parse CV summaries.

# YOUR TASK
Write a single tailored "Professional Summary" block for the top of this candidate's CV, precisely matched to the job listing below. The summary must pass both an ATS keyword filter AND a 6-second human HR skim.

# HOW TO THINK (do this silently, do NOT output your reasoning)
1. Extract the 5–8 most load-bearing requirements from the job description: must-have tech stack, seniority signal, domain, industry jargon, and any German-market signals (e.g. "Kundenorientierung", "agile Teams", "Stakeholder-Management").
2. **Identify the company's industry vertical** (e.g. AdTech, FinTech, LegalTech, HealthTech, Energy, E-Commerce, Logistics, Public Sector, Automotive, etc.) and extract the sector-specific business terms and KPIs that appear in the job ad (e.g. AdTech → ROI/ROAS, CTR, CPM, SmartBid, fraud detection; FinTech → AML, KYC, risk scoring, transaction latency; Energy → grid optimization, demand forecasting, SCADA; LegalTech → contract analysis, compliance automation, e-discovery). Use these terms when there is genuine CV evidence to back them — never insert sector jargon without a real connection.
3. Determine the ROLE TITLE from the job description using the rule below, then open the summary with it.
4. Map each requirement to concrete evidence in the candidate's CV. If a requirement has no evidence, DO NOT mention it — never fabricate experience, tools, years, or metrics.
5. Mirror the job ad's vocabulary verbatim where possible (e.g. if the ad says "LLM-based applications", write "LLM-based applications", not "generative AI solutions"). This is for ATS keyword matching.
6. Choose the 3 highest-signal keywords for this specific role. These get bolded.
7. Draft, then cut to fit the character budget.

# ROLE TITLE RULE (mandatory)
- Strip seniority/level prefixes (Senior, Lead, Principal, Junior, Staff, Head of, Consultant) from the job title.
- Keep the core function title exactly as written in the job ad.
- Open the summary with: "[Core Title] with [N]+ years [brief scope]"
- Examples of the rule applied:
  · Job ad says "Senior Data Scientist" → open with "Data Scientist with 4+ years..."
  · Job ad says "Lead AI Engineer" → open with "AI Engineer with 4+ years..."
  · Job ad says "Consultant Machine Learning Engineer" → open with "Machine Learning Engineer with 4+ years..."
  · Job ad says "Principal Data Engineer" → open with "Data Engineer with 3+ years..."
- If the job ad uses two titles (e.g. "Data Scientist / ML Engineer"), use both as Data Scientist / ML Engineer.

# HARD RULES
- Language: write ONLY in {lang_name}. Zero words in any other language (except proper nouns and tool names like "LangGraph", "AWS").
- Length: STRICT MAXIMUM {max_chars} characters total, including the ** markers and all spaces. Count before finalizing. Aim for {safe_low}–{max_chars - 10} to be safe.
- Bolding: wrap EXACTLY 3 keywords (single words or tight 2-word phrases) in **double asterisks**. No other markdown — no italics, no lists, no headers.
- Facts: every claim must be traceable to the CV or candidate notes. No invented metrics, years, certifications, or employer names.
- Structure: 3–5 sentences. No bullet points. No labels like "Summary:" or "Profile:".
- Tone: confident, specific, factual. Match the register of the job ad (formal corporate vs. startup casual).

# ANTI-PATTERNS — DO NOT WRITE LIKE THIS
- "Passionate, results-driven professional with a proven track record..." (generic, zero signal)
- "Seeking to leverage my skills in a challenging environment..." (candidate-centric filler)
- Listing tools without context or impact.
- Copy-pasting the CV's existing summary.
- Translating tool names (keep "LangGraph", "RAG", "FastAPI" as-is even in German).
- Mirroring the sentence structure of any example below — the examples teach principles, not a template.
- Using sector terms (ROI, CTR, AML, SCADA, etc.) as decoration — only use them when the CV evidence directly connects.

# FEW-SHOT EXAMPLES
These examples show different valid styles. Learn the underlying principles. Do NOT copy their structure, opening phrases, or sentence rhythm.

## Example A — Startup AI Engineer role, English
Job ad keywords: agentic workflows, LLM fine-tuning, production deployment, FastAPI
---
AI Engineer with 3+ years shipping production **agentic workflows** for public-sector platforms handling 3,000+ daily requests. Fine-tuned Whisper Large v3 via LoRA (WER −3.65%) and built hybrid RAG+LightGBM pipelines at city scale. Owns the full stack from model training to **FastAPI** deployment; experienced with LangGraph, crewAI, and vector databases. Brings measurable throughput gains — 10× individual processing capacity — to teams building reliable **LLM fine-tuning** infrastructure.

## Example B — Corporate Data Scientist role, English
Job ad keywords: machine learning, stakeholder communication, Power BI, time series forecasting
---
Data Scientist with 4+ years turning complex transport and operational data into decisions for 5M+ residents. Delivered 90%+ accuracy on **time series forecasting** models (LSTM + LightGBM) now live on public ferry screens, and built NL→SQL audit pipelines that cut manual review time by 40%. Comfortable translating model outputs into **Power BI** dashboards for non-technical stakeholders including C-level. Strong foundation in **machine learning** across NLP, anomaly detection, and recommendation systems.

## Example C — Data Engineer role, German
Job ad keywords: Datenpipelines, Apache Spark, Cloud-Infrastruktur, MLOps
---
Data Engineer mit 3+ Jahren Erfahrung im Aufbau skalierbarer **Datenpipelines** für städtische Mobilitätssysteme mit über 5 Millionen Nutzern. Betrieb von Hadoop- und PySpark-Infrastrukturen für Bus-, Fähr- und Metrodaten sowie Echtzeit-Prognosemodelle auf Basis von LSTM und LightGBM. Erfahren in **MLOps**-Workflows mit Docker, MLflow und CI/CD-Pipelines; vertraut mit AWS Glue, Athena und S3 für **Cloud-Infrastruktur**. Liefert end-to-end: von der Rohdatenverarbeitung bis zum produktiven Deployment.
{draft_block}

--- JOB DESCRIPTION ---
{job_desc}

--- CANDIDATE PROFILE (CV plain text, summary section excluded) ---
{cv_plain_text}

# OUTPUT
Return ONLY the final summary text. No preamble, no explanation, no quotation marks, no "Here is the summary:". Just the summary, ≤{max_chars} characters, exactly 3 **bolded** keywords."""
    try:
        result = call_llm(prompt, provider, api_key, model_name, is_json=False).strip()
        if len(result) > max_chars:
            result = result[:max_chars - 3] + '...'
        return result
    except Exception as e:
        print(f"Error generating CV summary: {e}")
        return "Generation failed."


def generate_motivation_letter(job_desc: str, cv_text: str, language: str, draft: str, provider: str = "Gemini", api_key: str = "", model_name: str = "gemini-1.5-pro", company_research: str = "") -> str:
    lang_name = "English" if language == "EN" else "German"
    draft_block = f"\n\n--- CANDIDATE NOTES (must incorporate naturally) ---\n{draft.strip()}" if draft and draft.strip() else ""
    company_research_block = f"\n\n--- COMPANY RESEARCH (use for the hook in paragraph 1) ---\n{company_research.strip()}" if company_research and company_research.strip() else ""

    prompt = f"""You are a senior technical recruiter and career coach specializing in the German tech job market (Data Science, AI/ML, Data Engineering). You have written and reviewed thousands of motivation letters that succeeded at SAP, Bosch, Zalando, BMW, Delivery Hero, N26, Celonis, and Berlin/Munich AI startups. You know exactly why most motivation letters get rejected: they are generic, they restate the CV, and they fail to answer the three questions every German HR actually asks.

# YOUR TASK
Write a tailored motivation letter (Anschreiben / cover letter) for this candidate, precisely matched to the job listing and company below. The letter must feel hand-written for this specific company and role — never like a template.

# THE THREE QUESTIONS YOUR LETTER MUST ANSWER (in this order)
1. WHY THIS COMPANY — specific to their product, mission, technical approach, or recent move. Never generic ("I admire your innovation").
2. WHY THIS ROLE — connect 2–3 concrete job requirements to specific CV evidence with metrics. Do not list the CV — interpret it.
3. WHY THIS CANDIDATE — one differentiator other applicants cannot claim (scale, domain, full-stack ownership, multilingual context, depth in a niche, etc.).

# HOW TO THINK (do this silently, do NOT output your reasoning)
1. Read the job description and company research. Identify: company's core product/mission, the role's 3 most critical requirements, the team's likely pain point.
2. **Identify the company's industry vertical** (AdTech, FinTech, LegalTech, HealthTech, Energy, E-Commerce, Logistics, Public Sector, Automotive, etc.) and collect the sector-specific business terms, KPIs, and product concepts that appear in the job ad or company research (examples: AdTech → ROI/ROAS, CTR, CPM, viewability, bid optimization, ad fraud; FinTech → AML, KYC, credit scoring, payment rails, transaction risk; Energy → demand forecasting, grid balancing, SCADA, smart meter analytics; LegalTech → contract analysis, compliance automation, e-discovery, matter management). Weave these terms into the letter wherever the candidate's CV evidence genuinely connects — this shows sector fluency, not keyword stuffing. **Never use a sector term without real CV evidence behind it.**
3. Find the strongest CV evidence for each critical requirement. Pick metrics that map directly to the role's scale or complexity.
4. Identify ONE differentiator unique to this candidate vs. typical applicants for this role.
5. Decide the hook: a specific company fact (product, tech stack, recent launch, mission angle) that connects authentically to the candidate's background. If company research is thin, use the most specific signal from the job ad itself (a named system, a stated challenge, a team mission line).
6. Draft, then cut padding ruthlessly.

# STRUCTURE (mandatory, 4 paragraphs)
- **Paragraph 1 — Hook + company connection (2–3 sentences):** Open with the specific company hook from step 4. State the role you are applying for naturally within these sentences. Never open with "I am writing to apply for..." or "With great interest I read your job posting...".
- **Paragraph 2 — Role fit (3–5 sentences):** Take 2–3 of the role's critical requirements. For each, give one concrete CV achievement with a metric. Use the job ad's exact terminology for ATS and HR recognition. Do not list tools — show outcomes.
- **Paragraph 3 — Differentiator (2–4 sentences):** One angle that sets this candidate apart for this specific role. Examples of valid differentiators (do not copy these, find the one that fits): city-scale public-sector data context, full-stack ownership from fine-tuning to deployment, hybrid ML+LLM architecture experience, multilingual delivery in a German-speaking team.
- **Paragraph 4 — Close (2–3 sentences):** State work authorization and location reality (Dortmund-based, open to relocation, work-authorized in Germany). Express specific interest in next steps — never "I look forward to hearing from you". **Never mention salary, compensation, Gehaltsvorstellung, or any monetary expectation — not even a range. Never mention German language level, progress, or any language skills.**

# HARD RULES
- Language: write ONLY in {lang_name}. Zero words in any other language (except proper nouns and tool names like "LangGraph", "AWS", "FastAPI").
- Length: 280–350 words total. Count before finalizing. Brevity signals confidence.
- Facts: every claim traceable to the CV or candidate notes. No invented metrics, employers, certifications, or years.
- Tone: confident, specific, factual, human. Match the company's register — formal for corporate (SAP, Bosch, BMW), warmer and more direct for startups.
- Salutation: "Dear Hiring Manager," in English; "Sehr geehrte Damen und Herren," in German — unless a named contact is provided in the job ad, then use the name.
- Sign-off: "Best regards, Veysel Murat Gorken" in English; "Mit freundlichen Grüßen, Veysel Murat Gorken" in German.
- No markdown formatting. No bullet points. No bolded text. Plain prose only.
- Tool names stay in original form even in German letters (LangGraph, RAG, FastAPI, PySpark).

# ABSOLUTE PROHIBITIONS — these will cause automatic rejection of the output
- **NEVER mention salary, compensation, pay, Gehaltsvorstellung, Gehaltswunsch, EUR, or any monetary figure or range.** Salary belongs in the interview, not the cover letter.
- **NEVER mention German language level, B1/B2/C1, language progress, or any statement about language skills.** This includes phrases like "Mein Deutsch liegt auf B1", "My German is improving", "ich entwickle meine Sprachkenntnisse weiter", or any equivalent.
- **NEVER use sector jargon (ROI/ROAS, CTR, AML, SCADA, etc.) without direct CV evidence.** Sector fluency is proven by connecting the term to a real achievement — using it as decoration is worse than not using it.

# ANTI-PATTERNS — DO NOT WRITE LIKE THIS
- "I am writing to express my strong interest in the [Role] position at [Company]." (template opener — instant rejection signal)
- "Your company's commitment to innovation aligns with my passion for..." (generic, says nothing)
- "As you can see from my CV, I have experience in..." (restates the CV instead of interpreting it)
- "I am a results-driven, passionate professional..." (zero signal adjectives)
- "I would welcome the opportunity to discuss..." / "I look forward to hearing from you." (passive, expected, forgettable close)
- Repeating the candidate's job titles and dates — that is the CV's job.
- Praising the company in vague terms ("industry leader", "exciting growth", "amazing team").
- Mirroring the sentence structure of the few-shot examples below.

# FEW-SHOT EXAMPLES
Two examples below in different registers and languages. Learn the underlying principles: specific hook, interpreted CV evidence, real differentiator, confident close. Do NOT copy openings, transitions, or rhythm.

## Example A — Berlin AI startup, English, AI Engineer role
---
Dear Hiring Manager,

Reading that Parloa is rebuilding contact-center AI around voice-first agents rather than chat overlays caught my attention — the engineering choice to treat latency and turn-taking as first-class problems is exactly the territory I have been working in. I would like to apply for the AI Engineer role on your platform team.

The job description highlights production agentic workflows, LLM fine-tuning, and reliability under load. At Izmir Inovasyon I built a hybrid ML and LLM agent pipeline running 3,000+ daily requests for a 5M-resident city, fine-tuned Whisper Large v3 via LoRA from 4.92 to 0.92 loss with a 3.65 percent absolute WER reduction on Turkish speech, and shipped FastAPI services that survived city-scale traffic. The combination of LangGraph orchestration, vector memory, and measurable latency targets in your stack is the kind of system I want to keep building.

What I think I bring beyond the keyword overlap is range across the full vertical — from LoRA fine-tuning, through RAG and agent design, down to FastAPI deployment and Big Data infrastructure on Hadoop and PySpark. Most candidates own one layer well; I have shipped production systems across all of them, which matters when a voice-AI platform fails in unexpected places.

I am based in Dortmund, work-authorized in Germany, and open to relocation to Berlin. I would be glad to walk you through the Whisper LoRA work or the agentic pipeline architecture in a first conversation.

Best regards,
Veysel Murat Gorken

## Example B — Munich corporate, German, Data Scientist role
---
Sehr geehrte Damen und Herren,

der Ansatz von Celonis, Process Mining mit generativer KI zu verbinden, statt klassisches Reporting zu erweitern, beschreibt genau die Richtung, in die ich meine Arbeit der letzten Jahre weiterentwickeln möchte. Ich bewerbe mich auf die ausgeschriebene Position als Data Scientist im Bereich AI-gestützte Prozessanalyse.

In der Stellenanzeige werden hybride ML-Systeme, NLP für strukturierte Geschäftsdaten und enge Zusammenarbeit mit Fachbereichen genannt. Bei Izmir Inovasyon habe ich eine Pipeline aus LightGBM, RAG und BERT mit 87 Prozent ML-Genauigkeit und 93 Prozent F1 in Produktion gebracht, eine NL-zu-SQL-Lösung über 500+ undokumentierte Oracle-Tabellen aufgesetzt, die manuelle Audit-Zeit um 40 Prozent reduziert, und LSTM-Prognosemodelle mit über 90 Prozent Genauigkeit für den städtischen Fährbetrieb ausgeliefert. Die Ergebnisse wurden als PowerBI-Dashboards bis auf Bürgermeister-Ebene konsumiert.

Was mich für diese Rolle besonders passend macht: ich habe ML- und LLM-Komponenten nicht getrennt gebaut, sondern als ein System, in dem klassische Modelle die Vorhersagen liefern und LLM-Agenten die Erklärung gegenüber Fachbereichen übernehmen. Genau diese Brücke zwischen Modell und Stakeholder fehlt in vielen Data-Science-Teams.

Ich lebe in Dortmund, bin in Deutschland arbeitsberechtigt und für einen Umzug nach München offen. Über ein erstes Gespräch zur Process-Mining-Pipeline oder zur Whisper-Feinabstimmung würde ich mich sehr freuen.

Mit freundlichen Grüßen,
Veysel Murat Gorken
{company_research_block}
{draft_block}

--- JOB DESCRIPTION ---
{job_desc}

--- CANDIDATE PROFILE (CV plain text) ---
{cv_text}

# OUTPUT
Return ONLY the final motivation letter. No preamble, no explanation, no commentary, no quotation marks. Plain prose only, 280–350 words, exactly 4 paragraphs plus salutation and sign-off."""
    try:
        return call_llm(prompt, provider, api_key, model_name, is_json=False)
    except Exception as e:
        print(f"Error generating letter: {e}")
        return "Generation failed."


def generate_both(
    job_desc: str,
    cv_plain_text: str,
    cv_text: str,
    language: str = "EN",
    draft: str = "",
    max_chars: int = 680,
    company_research: str = "",
    provider: str = "Gemini",
    api_key: str = "",
    model_name: str = "gemini-1.5-pro",
) -> dict:
    """Single LLM call that returns both CV summary and motivation letter.
    cv_plain_text: LaTeX-stripped text for the summary.
    cv_text: raw CV content for the letter."""
    lang_name = "English" if language == "EN" else "German"
    safe_low = max(max_chars - 60, max_chars * 9 // 10)
    draft_block = f"\n\n--- CANDIDATE NOTES ---\n{draft.strip()}" if draft and draft.strip() else ""
    company_research_block = f"\n\n--- COMPANY RESEARCH ---\n{company_research.strip()}" if company_research and company_research.strip() else ""

    prompt = f"""You are a senior technical recruiter and career coach specializing in the German tech job market (Data Science, AI/ML, Data Engineering). You produce two tailored documents simultaneously for a candidate applying to a specific job.

# STEP 0 — SHARED ANALYSIS (silent, do NOT output)
1. Identify the company's industry vertical (AdTech, FinTech, LegalTech, HealthTech, Energy, E-Commerce, Logistics, Public Sector, Automotive, etc.).
2. Extract sector-specific KPIs and business terms from the job ad (AdTech → ROI/ROAS, CTR, CPM, fraud detection; FinTech → AML, KYC, risk scoring; Energy → demand forecasting, SCADA; LegalTech → contract analysis, compliance). Use these terms in BOTH outputs only when the CV has genuine evidence — never as decoration.
3. Extract the 5–8 most load-bearing requirements from the job description.
4. Map each requirement to CV evidence. If no evidence exists, do NOT mention it. Never fabricate metrics, tools, or employer names.
5. Identify the core role title (strip seniority prefix: Senior, Lead, Principal, Junior, Staff, Head of, Consultant).

---

# TASK 1 — CV PROFESSIONAL SUMMARY

Write a single tailored "Professional Summary" block for the top of the candidate's CV. It must pass both an ATS keyword filter AND a 6-second HR skim.

Rules:
- Language: write ONLY in {lang_name}. Keep tool names as-is (LangGraph, AWS, FastAPI).
- Length: STRICT MAXIMUM {max_chars} characters total including ** markers and spaces. Aim for {safe_low}–{max_chars - 10}.
- Open with: "[Core Title] with [N]+ years [brief scope]"
- Bolding: wrap EXACTLY 3 highest-signal keywords in **double asterisks**. No other markdown.
- Facts: every claim traceable to the CV. No invented metrics or certifications.
- Structure: 3–5 sentences, no bullets, no labels like "Summary:".
- Mirror the job ad's vocabulary verbatim for ATS matching.
- NEVER use sector jargon without direct CV evidence.

Anti-patterns to avoid: generic openers ("Passionate, results-driven..."), listing tools without outcomes, copying the CV's existing summary.

---

# TASK 2 — MOTIVATION LETTER

Write a tailored motivation letter (Anschreiben / cover letter). It must feel hand-written for this specific company and role.

The letter must answer these three questions in order:
1. WHY THIS COMPANY — specific to their product, mission, or technical approach.
2. WHY THIS ROLE — 2–3 job requirements linked to CV evidence with metrics.
3. WHY THIS CANDIDATE — one differentiator other applicants cannot claim.

Structure (mandatory, 4 paragraphs):
- Paragraph 1 — Hook + company connection (2–3 sentences): Open with a specific company fact. State the role naturally. Never open with "I am writing to apply for..." or "With great interest I read...".
- Paragraph 2 — Role fit (3–5 sentences): 2–3 critical requirements mapped to CV achievements with metrics. Use the job ad's exact terminology. Show outcomes, not tool lists.
- Paragraph 3 — Differentiator (2–4 sentences): One angle that sets this candidate apart (full-stack ownership, domain depth, city-scale public-sector context, hybrid ML+LLM architecture, etc.).
- Paragraph 4 — Close (2–3 sentences): Work authorization and location. Specific next-step interest. No passive close ("I look forward to hearing from you").

Rules:
- Language: write ONLY in {lang_name}. Keep tool names as-is.
- Length: 280–350 words total. Count before finalizing.
- Salutation: "Dear Hiring Manager," (EN) or "Sehr geehrte Damen und Herren," (DE) — unless a named contact appears in the job ad.
- Sign-off: "Best regards, Veysel Murat Gorken" (EN) or "Mit freundlichen Grüßen, Veysel Murat Gorken" (DE).
- No markdown, no bullets, no bold. Plain prose only.
- NEVER mention salary, compensation, Gehaltsvorstellung, EUR, or any monetary figure.
- NEVER mention German language level, B1/B2/C1, or language progress.
- NEVER use sector jargon without direct CV evidence.

Anti-patterns: template openers, generic company praise ("industry leader", "amazing team"), restating the CV, passive close.

---

--- JOB DESCRIPTION ---
{job_desc}

--- CANDIDATE PROFILE (CV plain text, for summary) ---
{cv_plain_text}

--- CANDIDATE PROFILE (full CV, for letter) ---
{cv_text}{company_research_block}{draft_block}

# OUTPUT FORMAT
Return valid JSON only — no preamble, no markdown code fences:
{{
  "summary": "<CV professional summary, max {max_chars} chars, exactly 3 bolded keywords>",
  "letter": "<full motivation letter, plain prose, 4 paragraphs + salutation + sign-off>"
}}"""

    try:
        raw = call_llm(prompt, provider, api_key, model_name, is_json=True)
        data = json.loads(raw)
        return {
            "summary": data.get("summary", ""),
            "letter": data.get("letter", ""),
        }
    except Exception as e:
        print(f"Error in generate_both: {e}")
        return {"summary": "", "letter": ""}
