import os
import time
import json
import requests
from bs4 import BeautifulSoup
import openai

# Groq API configuration (Free tier drop-in replacement via OpenAI SDK)
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
    """Fetches public guest job postings from LinkedIn without logging in."""
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    params = {"keywords": keyword, "location": location, "start": 0}
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Error fetching jobs: HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("li")

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
        print(f"Scraper error: {e}")

    return jobs

def evaluate_job(user_profile, job):
    """Evaluates role fit using Groq's free Llama 3.3 70B model."""
    if not groq_client:
        print("GROQ_API_KEY missing. Skipping LLM evaluation.")
        return None

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    JOB TITLE: {job['title']}
    COMPANY: {job['company']}

    Task: Evaluate if this job is a good fit for the candidate profile.
    Respond ONLY with a valid JSON object matching this structure:
    {{
        "fit_score": 85,
        "verdict": "Apply",
        "customization_tip": "Highlight Python and system design projects in your summary."
    }}
    """

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"Groq evaluation error: {e}")
        return None

def send_telegram_notification(text):
    """Sends matched job alerts directly to your Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing. Outputting match to console:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def main():
    print("Starting automated job evaluation pipeline (Groq Free Tier)...")
    jobs = scrape_linkedin_jobs(keyword="Backend Engineer", limit=5)

    matches_found = 0
    for job in jobs:
        eval_result = evaluate_job(USER_PROFILE, job)
        if not eval_result:
            continue

        score = eval_result.get("fit_score", 0)
        if score >= 70:
            matches_found += 1
            msg = (
                f"🎯 *Strong Job Match ({score}%)*\n"
                f"*Role:* {job['title']}\n"
                f"*Company:* {job['company']}\n"
                f"*Tip:* {eval_result.get('customization_tip')}\n"
                f"[Apply Here]({job['url']})"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    print(f"Pipeline complete. Sent {matches_found} alerts.")

if __name__ == "__main__":
    main()