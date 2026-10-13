import os
import time
import json
import re
import requests
from bs4 import BeautifulSoup
import openai

# Environment Secrets
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

groq_client = openai.OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

USER_PROFILE = """
Fourth-year B.Tech student in Biotechnology at IIT Delhi looking for remote Software Engineering (SDE),
Data Science, Machine Learning, or Quantitative Development internships or fresher entry-level positions.
Technical Skills: Python, C++, SQL, Java, Go, PyTorch, TensorFlow, Scikit-Learn, Pandas, NumPy, REST APIs, System Design.
Experience: Software Development Intern at Flipkart (data compression optimization, AI developer tooling),
NSS Secretary, top 25 at FITT Tech Future Hackathon 2024.
"""

def get_active_groq_model():
    """Dynamically fetches active Groq models."""
    try:
        models = groq_client.models.list()
        active_ids = [m.id for m in models.data]
        preferred = ["llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
        for pref in preferred:
            if pref in active_ids:
                return pref
        text_models = [m_id for m_id in active_ids if "whisper" not in m_id and "guard" not in m_id]
        if text_models:
            return text_models[0]
    except Exception as e:
        print(f"[LLM WARNING] Model lookup failed: {e}")
    return "llama-3.3-70b-versatile"

def is_strictly_remote(title, location, description):
    """Filters out Hybrid/Onsite roles."""
    text_combined = f"{title} {location} {description}".lower()
    if any(negative in text_combined for negative in ["hybrid", "on-site", "onsite", "in-office", "relocate"]):
        return False
    remote_keywords = ["remote", "work from home", "wfh", "anywhere", "telecommute"]
    return any(kw in text_combined for kw in remote_keywords)

def scrape_remotive_jobs():
    """Fetches remote software & data science jobs directly from Remotive's free public API."""
    jobs = []
    try:
        url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=15"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json().get("jobs", [])
            for item in data:
                title = item.get("title", "")
                company = item.get("company_name", "")
                desc = item.get("description", "")
                job_url = item.get("url", "")
                salary = item.get("salary", "Not specified")

                if is_strictly_remote(title, "Remote", desc):
                    jobs.append({
                        "source_type": "Remotive API",
                        "title": title,
                        "company": company,
                        "location": "Remote",
                        "url": job_url,
                        "content": desc[:2000],
                        "salary_override": salary,
                        "recruiter": {"name": None, "profile_url": None}
                    })
    except Exception as e:
        print(f"[REMOTIVE SCRAPER ERROR] {e}")
    return jobs

def scrape_linkedin_job_cards(keyword="Software Engineer", limit=3):
    """Fetches public LinkedIn job cards forced to Remote."""
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    params = {"keywords": keyword, "location": "Worldwide", "f_WT": "2", "f_E": "1,2", "start": 0}

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.find_all("li")
            for card in cards[:limit]:
                title_tag = card.find("h3", class_="base-search-card__title")
                company_tag = card.find("h4", class_="base-search-card__subtitle")
                link_tag = card.find("a", class_="base-card__full-link")

                if title_tag and link_tag:
                    job_url = link_tag["href"]
                    title = title_tag.text.strip()
                    company = company_tag.text.strip() if company_tag else "N/A"

                    jobs.append({
                        "source_type": "LinkedIn Job",
                        "title": title,
                        "company": company,
                        "location": "Remote",
                        "url": job_url,
                        "content": f"{title} at {company}. Remote fresher/intern position.",
                        "salary_override": None,
                        "recruiter": {"name": None, "profile_url": None}
                    })
    except Exception as e:
        print(f"[LINKEDIN SCRAPER ERROR] {e}")
    return jobs

def evaluate_opportunity(user_profile, item):
    """Evaluates suitability and drafts contact strategy."""
    if not groq_client:
        return None

    urls_in_content = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', item['content'])
    registration_link = item['url']
    for u in urls_in_content:
        if "linkedin.com" not in u and "google.com" not in u:
            registration_link = u
            break

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    SOURCE: {item['source_type']}
    TITLE: {item['title']}
    COMPANY: {item['company']}
    CONTENT: {item['content']}

    Respond ONLY with valid JSON:
    {{
        "is_fresher_or_intern": true/false,
        "is_remote_confirmed": true/false,
        "has_direct_apply_link": true/false,
        "direct_apply_url": "{registration_link}",
        "expected_stipend_or_salary": "{item.get('salary_override') or 'e.g., $35/hr, ₹40,000/mo, or Not specified'}",
        "fit_score": 85,
        "connection_note": "Draft a <280 char message ONLY IF no apply link is present.",
        "messaging_tips": "2 key technical skills (Python, PyTorch, C++) to emphasize."
    }}
    """

    target_model = get_active_groq_model()
    try:
        res = groq_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return None

def send_telegram_notification(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def main():
    print("=== STARTING MULTI-PLATFORM REMOTE JOB PIPELINE ===")
    send_telegram_notification("🌐 *Multi-Platform Job Scraper Active:* Fetching from LinkedIn, Remotive, and Remote APIs...")

    all_items = []
    seen_urls = set()

    # 1. Fetch from Remotive API (High yield for remote tech)
    remotive_jobs = scrape_remotive_jobs()
    for r in remotive_jobs:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            all_items.append(r)

    # 2. Fetch from LinkedIn Job Cards
    for kw in ["Software Engineer Intern", "Data Science Intern", "Machine Learning Intern"]:
        cards = scrape_linkedin_job_cards(keyword=kw, limit=3)
        for c in cards:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                all_items.append(c)

    print(f"[PIPELINE] Collected {len(all_items)} total opportunities across platforms.")

    matches_found = 0
    for item in all_items:
        eval_res = evaluate_opportunity(USER_PROFILE, item)
        if not eval_res:
            continue

        is_fresher = eval_res.get("is_fresher_or_intern", False)
        is_remote = eval_res.get("is_remote_confirmed", True)
        score = eval_res.get("fit_score", 0)
        has_apply_link = eval_res.get("has_direct_apply_link", True)
        apply_url = eval_res.get("direct_apply_url", item["url"])
        stipend = eval_res.get("expected_stipend_or_salary", "Not specified")

        if is_fresher and is_remote and score >= 70:
            matches_found += 1

            if has_apply_link:
                action_block = f"📝 *Apply Directly Here:* [Registration / Job Link]({apply_url})"
            else:
                recruiter_url = f"https://www.linkedin.com/search/results/people/?keywords=Technical%20Recruiter%20{item['company']}"
                action_block = (
                    f"👤 *No Registration Link Found. Reach Out Directly:* [LinkedIn Recruiter Search]({recruiter_url})\n\n"
                    f"💬 *Outreach Note (<280 chars):*\n`{eval_res.get('connection_note')}`\n\n"
                    f"📌 *Messaging Tips:* {eval_res.get('messaging_tips')}"
                )

            msg = (
                f"🎯 *New Match ({score}% Fit - {item['source_type']})*\n\n"
                f"*Role:* {item['title']}\n"
                f"*Company:* {item['company']}\n"
                f"*Location:* 🏠 Remote\n"
                f"*Expected Pay/Stipend:* {stipend}\n\n"
                f"🔗 [View Source Posting]({item['url']})\n"
                f"{action_block}"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    send_telegram_notification(f"✅ *Multi-Platform Scan Finished:* Scraped {len(all_items)} opportunities across platforms, sent {matches_found} alerts.")

if __name__ == "__main__":
    main()