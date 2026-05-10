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


def generate_cv_summary(job_desc: str, cv_plain_text: str, language: str = "EN", draft: str = "", provider: str = "Gemini", api_key: str = "", model_name: str = "gemini-1.5-pro") -> str:
    lang_name = "English" if language == "EN" else "German"
    draft_block = f"\nCandidate notes to incorporate: {draft.strip()}" if draft and draft.strip() else ""

    prompt = f"""You are an expert CV writer for the German job market.
Write a tailored professional profile/summary for this candidate based on the specific job listing.

CRITICAL RULE 1: Write ONLY in {lang_name}. No other language.
CRITICAL RULE 2: Return ONLY the summary text. No labels, no headers, no JSON, no LaTeX commands, no explanations.
CRITICAL RULE 3: STRICTLY MAXIMUM 480 CHARACTERS (including the ** markers below). Count carefully. Be concise.
CRITICAL RULE 4: Reference concrete requirements from the job description. Use real skills from the CV. Do not invent facts.
CRITICAL RULE 5: Identify the 3 most important keywords in the summary and wrap ONLY those words with **double asterisks** (e.g. **LangGraph**). No other markdown. Exactly 3 bolded keywords.
{draft_block}

--- JOB DESCRIPTION ---
{job_desc}

--- CANDIDATE PROFILE (CV plain text, no summary section) ---
{cv_plain_text}

Output ONLY the summary text with exactly 3 keywords wrapped in **double asterisks**. Under 480 characters total."""
    try:
        result = call_llm(prompt, provider, api_key, model_name, is_json=False).strip()
        if len(result) > 480:
            result = result[:477] + '...'
        return result
    except Exception as e:
        print(f"Error generating CV summary: {e}")
        return "Generation failed."


def generate_motivation_letter(job_desc: str, cv_text: str, language: str, draft: str, provider: str = "Gemini", api_key: str = "", model_name: str = "gemini-1.5-pro", sample_letter_text: str = "") -> str:
    lang_name = "English" if language == "EN" else "German"

    sample_instruction = ""
    if sample_letter_text:
        sample_instruction = f"""
--- SAMPLE LETTER (tone, structure, and personal details to copy) ---
YOU MUST EXACTLY COPY the Name, Address, Email, and Phone number from this sample.
Mimic its tone and writing style closely.
{sample_letter_text}
"""

    draft_instruction = "No specific notes provided."
    if draft and draft.strip():
        draft_instruction = f"""
CRITICAL: The applicant provided the following notes. Incorporate them prominently and seamlessly.
Do NOT ignore any instruction or reference mentioned here.
NOTES:
{draft}
"""

    prompt = f"""
You are an expert career coach specializing in the German job market.
Write a highly professional motivation letter for a job application.
Use a direct, evidence-based tone: no hyperbole, no filler phrases, concrete achievements with numbers where possible.

CRITICAL RULE 1: Write the entire letter in {lang_name}. Do NOT mix languages.
CRITICAL RULE 2: Output ONLY plain text. No markdown, no asterisks, no hashtags, no bold tags.
CRITICAL RULE 3: If a SAMPLE LETTER is provided, EXACTLY COPY the Name, Address, Email, and Phone from it. Do not invent contact details.
CRITICAL RULE 4: The letter MUST be between 250 and 350 words.
CRITICAL RULE 5: Incorporate all applicant notes below. Do not ignore any instruction.

--- JOB DESCRIPTION ---
{job_desc}

--- APPLICANT CV ---
{cv_text}

{sample_instruction}

--- APPLICANT NOTES / DRAFT ---
{draft_instruction}

--- LETTER STRUCTURE (4 paragraphs, no headers or labels) ---

Paragraph 1 — Opening:
State the exact position and give the single strongest reason the applicant is a fit. Be specific.

Paragraph 2 — Technical Experience:
Highlight 2-3 specific, quantified achievements from the CV most relevant to this role. Use numbers. Do not invent facts.

Paragraph 3 — Company Connection:
Explain why the applicant is interested in this specific company and role. Reference something concrete from the job description.

Paragraph 4 — Closing:
State availability, work authorization, and include a clear professional call to action.
"""
    try:
        return call_llm(prompt, provider, api_key, model_name, is_json=False)
    except Exception as e:
        print(f"Error generating letter: {e}")
        return "Generation failed."
