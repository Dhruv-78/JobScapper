import os
import time
import json
import requests
from bs4 import BeautifulSoup
import openai

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

groq_client = openai.OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
) if GROQ_API_KEY else None

USER_PROFILE = """
Software engineer with experience in Python, C++, REST APIs, system design,
SQL, and machine learning (PyTorch, Pandas). Strong background in backend data engineering
and microservices. Looking for Data Engineering or Backend Developer roles.
"""

def scrape_linkedin_jobs(keyword, location="Remote", limit=5):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    params = {"keywords": keyword, "location": location, "start": 0}
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
                jobs.append({
                    "title": title_tag.text.strip(),
                    "company": company_tag.text.strip() if company_tag else "N/A",
                    "url": link_tag["href"]
                })

    except Exception as e:
        print(f"[SCRAPER ERROR] {e}")

    return jobs

def evaluate_job(user_profile, job):
    if not groq_client:
        print("[LLM ERROR] GROQ_API_KEY missing from environment variables.")
        return None

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    JOB TITLE: {job['title']}
    COMPANY: {job['company']}

    Evaluate if this job is a fit.
    Respond ONLY with JSON:
    {{
        "fit_score": 85,
        "verdict": "Apply",
        "customization_tip": "Highlight backend and API skills."
    }}
    """

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        data = json.loads(res.choices[0].message.content)
        print(f"[LLM EVAL] Job: {job['title']} | Score: {data.get('fit_score')}%")
        return data
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return None

def send_telegram_notification(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM ERROR] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in secrets.")
        print(f"[CONSOLE OUTPUT]:\n{text}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        res_data = r.json()
        if not res_data.get("ok"):
            print(f"[TELEGRAM API ERROR] Response: {res_data}")
        else:
            print("[TELEGRAM] Message sent successfully!")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def main():
    print("=== STARTING JOB EVALUATION PIPELINE ===")
    
    # Send quick heart-beat ping to confirm Telegram works
    send_telegram_notification("🤖 *Job Scraper Executed*: Checking for new job postings now...")

    jobs = scrape_linkedin_jobs(keyword="Backend Engineer", limit=5)
    print(f"[PIPELINE] Scraped {len(jobs)} valid job links.")

    matches_found = 0
    for job in jobs:
        eval_result = evaluate_job(USER_PROFILE, job)
        if not eval_result:
            continue

        score = eval_result.get("fit_score", 0)
        # Lowered threshold to 50% for testing visibility
        if score >= 50:
            matches_found += 1
            msg = (
                f"🎯 *Job Match Found ({score}%)*\n"
                f"*Role:* {job['title']}\n"
                f"*Company:* {job['company']}\n"
                f"*Tip:* {eval_result.get('customization_tip')}\n"
                f"[Apply Here]({job['url']})"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    print(f"=== PIPELINE FINISHED. Sent {matches_found} job alerts ===")

if __name__ == "__main__":
    main()