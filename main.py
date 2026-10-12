import os
import time
import json
import requests
from bs4 import BeautifulSoup
import openai

# API Secrets
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

groq_client = openai.OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

USER_PROFILE = """
Fourth-year B.Tech student in Biotechnology at IIT Delhi looking for entry-level Software Engineering,
Data Science, Quantitative Development, or Machine Learning roles/internships.
Skills: Python, C++, SQL, Java, Go, PyTorch, TensorFlow, Scikit-Learn, Pandas, NumPy, REST APIs, System Design.
Experience: Software Development Intern at Flipkart (data compression, AI developer tooling),
NSS Secretary, top 25 at FITT Tech Future Hackathon 2024.
"""

def get_active_groq_model():
    """Dynamically retrieves an active text model from Groq API."""
    try:
        models = groq_client.models.list()
        active_ids = [m.id for m in models.data]
        
        preferred = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant"
        ]
        for pref in preferred:
            if pref in active_ids:
                return pref
        
        text_models = [m_id for m_id in active_ids if "whisper" not in m_id and "guard" not in m_id]
        if text_models:
            return text_models[0]
    except Exception as e:
        print(f"[LLM WARNING] Dynamic model lookup failed: {e}")
    
    return "llama-3.3-70b-versatile"

def fetch_job_description(job_url, headers):
    """Fetches full job description text from LinkedIn guest page."""
    try:
        res = requests.get(job_url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            if desc_div:
                return desc_div.text.strip()[:2000] # Cap text for context efficiency
    except Exception as e:
        print(f"[SCRAPER WARNING] Could not fetch description for {job_url}: {e}")
    return "Description unretrievable."

def scrape_fresher_remote_jobs(keyword="Software Engineer", limit=5):
    """
    Fetches guest LinkedIn jobs filtered specifically for Remote + Entry Level/Internships.
    f_WT=2 -> Remote
    f_E=1,2 -> Internship (1), Entry Level (2)
    """
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    params = {
        "keywords": keyword,
        "location": "Remote",
        "f_WT": "2",      # Remote only
        "f_E": "1,2",     # Internship & Entry level only
        "start": 0
    }

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        print(f"[SCRAPER] LinkedIn HTTP Status: {response.status_code}")
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("li")
        print(f"[SCRAPER] Total raw job cards found: {len(cards)}")

        for card in cards[:limit]:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            link_tag = card.find("a", class_="base-card__full-link")

            if title_tag and link_tag:
                job_url = link_tag["href"]
                description = fetch_job_description(job_url, headers)

                jobs.append({
                    "title": title_tag.text.strip(),
                    "company": company_tag.text.strip() if company_tag else "N/A",
                    "url": job_url,
                    "description": description
                })

    except Exception as e:
        print(f"[SCRAPER ERROR] {e}")

    return jobs

def evaluate_job(user_profile, job):
    """Evaluates role fit, expected stipend/salary, and confirms fresher eligibility."""
    if not groq_client:
        print("[LLM ERROR] GROQ_API_KEY missing!")
        return None

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    JOB TITLE: {job['title']}
    COMPANY: {job['company']}
    DESCRIPTION: {job['description']}

    TASK:
    Analyze this job posting carefully.

    Respond ONLY with a valid JSON object matching this schema:
    {{
        "is_fresher_friendly": true/false,
        "is_remote": true/false,
        "expected_stipend_or_salary": "e.g., $30/hr, ₹30,000/mo, or Not specified in description",
        "fit_score": 85,
        "verdict": "Apply / Consider / Skip",
        "customization_tip": "Highlight experience with microservices and PyTorch."
    }}

    CRITICAL RULES:
    1. Set "is_fresher_friendly" to false if the description explicitly requires 2+ years of prior full-time industry experience.
    2. Extract any salary, stipend, or compensation numbers mentioned in the description. If none exist, output "Not specified in description".
    """

    target_model = get_active_groq_model()

    try:
        res = groq_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        print(f"[LLM SUCCESS] Evaluated using model: {target_model}")
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"[LLM ERROR] Evaluation failed on {target_model}: {e}")
        return None

def send_telegram_notification(text):
    """Sends matched job alerts directly to your Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM NOTICE] Secrets missing. Outputting message locally:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"[TELEGRAM] Response Status: {res.status_code}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def main():
    print("=== STARTING FRESHER REMOTE JOB PIPELINE ===")
    send_telegram_notification("🤖 *Job Scraper Executed:* Scanning for Remote Fresher / Internship roles...")

    jobs = scrape_fresher_remote_jobs(keyword="Software Engineer", limit=5)
    print(f"[PIPELINE] Scraped {len(jobs)} valid job listings.")

    matches_found = 0
    for job in jobs:
        eval_result = evaluate_job(USER_PROFILE, job)
        if not eval_result:
            continue

        is_fresher = eval_result.get("is_fresher_friendly", True)
        score = eval_result.get("fit_score", 0)
        stipend = eval_result.get("expected_stipend_or_salary", "Not specified")

        print(f"Job: {job['title']} | Fresher Friendly: {is_fresher} | Score: {score}% | Stipend: {stipend}")

        # Send alert if job is suitable for freshers and scores >= 70%
        if is_fresher and score >= 70:
            matches_found += 1
            msg = (
                f"🎯 *New Remote Fresher Opportunity ({score}% Match)*\n"
                f"*Role:* {job['title']}\n"
                f"*Company:* {job['company']}\n"
                f"*Expected Stipend/Salary:* {stipend}\n"
                f"*Work Mode:* 🏠 Remote\n"
                f"*Tip:* {eval_result.get('customization_tip')}\n\n"
                f"[Apply Here]({job['url']})"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    if matches_found == 0:
        send_telegram_notification("ℹ️ Scan completed. No remote fresher postings found above 70% match in this run.")

    print(f"=== PIPELINE FINISHED. Sent {matches_found} job alerts ===")

if __name__ == "__main__":
    main()