import os
import time
import json
import requests
from bs4 import BeautifulSoup
import openai

# API Secrets from GitHub Environment
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

JOB_KEYWORDS = [
    "Software Engineer Intern",
    "Entry Level Software Engineer",
    "Data Science Intern",
    "Machine Learning Intern"
]

POST_SEARCH_QUERIES = [
    'site:linkedin.com/posts "hiring" "intern" OR "fresher" "software engineer" OR "data science" "remote"',
    'site:linkedin.com/posts "DM me your resume" "software" OR "data science" "remote"',
    'site:linkedin.com/posts "my team is hiring" "intern" OR "entry level" "remote"'
]

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

def fetch_job_details(job_url, headers):
    """Fetches job description and attempts to extract posted recruiter info."""
    description = "Description unretrievable."
    recruiter_info = {"name": None, "profile_url": None}

    try:
        res = requests.get(job_url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            if desc_div:
                description = desc_div.text.strip()[:2500]

            recruiter_card = soup.find("div", class_="message-the-recruiter") or soup.find("a", class_="base-card__full-link")
            if recruiter_card:
                name_tag = recruiter_card.find("h3") or recruiter_card.find("span")
                link_tag = recruiter_card.get("href") or recruiter_card.find("a", href=True)
                
                if name_tag:
                    recruiter_info["name"] = name_tag.text.strip()
                if isinstance(link_tag, str):
                    recruiter_info["profile_url"] = link_tag
                elif link_tag and link_tag.get("href"):
                    recruiter_info["profile_url"] = link_tag["href"]
    except Exception as e:
        print(f"[SCRAPER WARNING] Could not fetch details for {job_url}: {e}")

    return description, recruiter_info

def scrape_linkedin_job_cards(keyword, limit_per_keyword=2):
    """Scrapes public LinkedIn job cards."""
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    params = {
        "keywords": keyword,
        "location": "Remote",
        "f_WT": "2",     # Remote
        "f_E": "1,2",    # Internship & Entry Level
        "start": 0
    }

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("li")

        for card in cards[:limit_per_keyword]:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            link_tag = card.find("a", class_="base-card__full-link")

            if title_tag and link_tag:
                job_url = link_tag["href"]
                description, recruiter = fetch_job_details(job_url, headers)

                jobs.append({
                    "source_type": "Job Card",
                    "title": title_tag.text.strip(),
                    "company": company_tag.text.strip() if company_tag else "N/A",
                    "url": job_url,
                    "content": description,
                    "recruiter": recruiter
                })
    except Exception as e:
        print(f"[SCRAPER ERROR] Job card error: {e}")

    return jobs

def scrape_linkedin_hiring_posts():
    """Fetches public LinkedIn posts about hiring using DDG web search parsing."""
    posts = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for query in POST_SEARCH_QUERIES:
        try:
            url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            results = soup.find_all("a", class_="result__url")

            for r in results[:3]:
                href = r.get("href", "")
                if "linkedin.com/posts" in href or "linkedin.com/feed/update" in href:
                    snippet_div = r.find_parent("div", class_="result__body")
                    snippet_text = snippet_div.find("a", class_="result__snippet").text if snippet_div else "Hiring post snippet"

                    posts.append({
                        "source_type": "LinkedIn Post",
                        "title": "Direct Hiring Post",
                        "company": "Poster / Hiring Team",
                        "url": href,
                        "content": snippet_text,
                        "recruiter": {"name": "Post Author", "profile_url": href}
                    })
        except Exception as e:
            print(f"[POST SCRAPER WARNING] {e}")

    return posts

def evaluate_and_generate_outreach(user_profile, item):
    """Evaluates posting/job fit and drafts direct outreach templates."""
    if not groq_client:
        print("[LLM ERROR] GROQ_API_KEY missing!")
        return None

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    SOURCE TYPE: {item['source_type']}
    TITLE/ROLE: {item['title']}
    COMPANY/POSTER: {item['company']}
    CONTENT/DESCRIPTION: {item['content']}

    TASK:
    Analyze this posting/job and generate personalized outreach content for the hiring recruiter/manager.

    Respond ONLY with a valid JSON object matching this schema:
    {{
        "is_relevant_fresher_or_intern": true/false,
        "job_type": "Internship / Entry-Level / Direct Post Callout",
        "expected_stipend_or_salary": "e.g., $35/hr, ₹40,000/mo, or Not specified",
        "fit_score": 85,
        "connection_note": "Under 280 character connection message mentioning IIT Delhi, Flipkart intern experience, and interest in their role/post.",
        "messaging_strategy_tips": "2 bullet points on specific technical angles (e.g. PyTorch, C++, system design) to mention in a DM."
    }}

    RULES:
    1. Set "is_relevant_fresher_or_intern" to false if it requires 2+ years of prior post-grad experience.
    2. Connection note MUST be under 280 characters to fit LinkedIn's invite limit.
    """

    target_model = get_active_groq_model()

    try:
        res = groq_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        print(f"[LLM SUCCESS] Evaluated {item['source_type']} - '{item['title']}' using {target_model}")
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"[LLM ERROR] Evaluation failed on {target_model}: {e}")
        return None

def send_telegram_notification(text):
    """Sends notification to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM NOTICE] Secrets missing. Outputting locally:")
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
    print("=== STARTING JOBS + LINKEDIN POSTS SCRAPER & OUTREACH PIPELINE ===")
    send_telegram_notification("🤖 *Job & Post Scraper Active:* Fetching job listings and recruiter hiring posts...")

    all_items = []
    seen_urls = set()

    # 1. Scrape Job Cards
    for kw in JOB_KEYWORDS:
        jobs = scrape_linkedin_job_cards(keyword=kw, limit_per_keyword=2)
        for j in jobs:
            if j["url"] not in seen_urls:
                seen_urls.add(j["url"])
                all_items.append(j)

    # 2. Scrape Hiring Posts
    posts = scrape_linkedin_hiring_posts()
    for p in posts:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            all_items.append(p)

    print(f"[PIPELINE] Collected {len(all_items)} total items (Job Cards + LinkedIn Posts).")

    matches_found = 0
    for item in all_items:
        eval_result = evaluate_and_generate_outreach(USER_PROFILE, item)
        if not eval_result:
            continue

        is_relevant = eval_result.get("is_relevant_fresher_or_intern", False)
        score = eval_result.get("fit_score", 0)
        stipend = eval_result.get("expected_stipend_or_salary", "Not specified")
        job_type = eval_result.get("job_type", "Internship / Fresher")
        connection_note = eval_result.get("connection_note", "")
        tips = eval_result.get("messaging_strategy_tips", "")

        recruiter_link = ""
        if item["recruiter"]["profile_url"]:
            recruiter_link = f"👤 *Recruiter / Post Link:* [Open Profile or Post]({item['recruiter']['profile_url']})\n"
        else:
            search_query = f"Technical Recruiter {item['company']}"
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}"
            recruiter_link = f"🔍 *Find Recruiter:* [Search Recruiter]({search_url})\n"

        if is_relevant and score >= 70:
            matches_found += 1
            msg = (
                f"🎯 *New Match ({score}% Fit - {item['source_type']})*\n\n"
                f"*Title:* {item['title']}\n"
                f"*Company/Poster:* {item['company']}\n"
                f"*Type:* {job_type}\n"
                f"*Expected Pay/Stipend:* {stipend}\n"
                f"*Work Mode:* 🏠 Remote\n\n"
                f"🔗 [View Link]({item['url']})\n"
                f"{recruiter_link}\n"
                f"💬 *Ready-to-Send Connection Note (<280 chars):*\n"
                f"`{connection_note}`\n\n"
                f"📌 *Messaging Strategy Tips:*\n{tips}"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    if matches_found == 0:
        send_telegram_notification("ℹ️ Scan complete. No suitable fresher/internship listings or posts found in this cycle.")

    print(f"=== PIPELINE FINISHED. Sent {matches_found} alerts ===")

if __name__ == "__main__":
    main()