import os
import time
import json
import re
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

def get_active_groq_model():
    """Dynamically retrieves an active text model from Groq API."""
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
        print(f"[LLM WARNING] Dynamic model lookup failed: {e}")
    return "llama-3.3-70b-versatile"

def fetch_job_details(job_url, headers):
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
        print(f"[SCRAPER WARNING] Details fetch error: {e}")

    return description, recruiter_info

def scrape_linkedin_job_cards(keyword, limit_per_keyword=2):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    params = {"keywords": keyword, "location": "Remote", "f_WT": "2", "f_E": "1,2", "start": 0}

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
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
        print(f"[JOB CARD SCRAPER ERROR] {e}")
    return jobs

def scrape_linkedin_hiring_posts():
    """Scrapes hiring posts from public feed aggregators and LinkedIn search endpoints."""
    posts = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # Target guest search API for content posts
    search_terms = ["hiring intern remote python", "hiring software engineer fresher remote", "DM resume data science intern"]
    
    for term in search_terms:
        try:
            url = f"https://www.google.com/search?q=site:linkedin.com/posts+%22{requests.utils.quote(term)}%22"
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                links = soup.find_all("a", href=True)
                for l in links:
                    href = l["href"]
                    if "/posts/" in href or "/feed/update/" in href:
                        clean_url = href.split("&")[0].replace("/url?q=", "")
                        if "linkedin.com" in clean_url:
                            posts.append({
                                "source_type": "LinkedIn Post",
                                "title": f"Hiring Post ({term})",
                                "company": "Poster / Hiring Manager",
                                "url": clean_url,
                                "content": "Direct hiring post found on LinkedIn.",
                                "recruiter": {"name": "Post Author", "profile_url": clean_url}
                            })
        except Exception as e:
            print(f"[POST SCRAPER ERROR] {e}")

    return posts

def evaluate_job(user_profile, item):
    """Evaluates posting and conditionally determines if a registration link or recruiter DM is needed."""
    if not groq_client:
        return None

    # Detect external URLs/registration links inside the content
    urls_in_content = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', item['content'])
    registration_link = urls_in_content[0] if urls_in_content else None

    prompt = f"""
    CANDIDATE PROFILE:
    {user_profile}

    SOURCE TYPE: {item['source_type']}
    TITLE/ROLE: {item['title']}
    COMPANY/POSTER: {item['company']}
    CONTENT: {item['content']}
    DETECTED LINK: {registration_link}

    TASK:
    Analyze if this posting has a direct registration/application link or if candidate must contact the poster directly.

    Respond ONLY with a valid JSON object:
    {{
        "is_fresher_or_intern": true/false,
        "has_direct_apply_link": true/false,
        "direct_apply_url": "{registration_link if registration_link else 'None'}",
        "expected_stipend_or_salary": "e.g., $35/hr, ₹40,000/mo, or Not specified",
        "fit_score": 85,
        "connection_note": "Write a <280 character connection request note ONLY IF has_direct_apply_link is false.",
        "messaging_tips": "Key points to mention if reaching out directly."
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
    print("=== STARTING DUAL-CHANNEL SCRAPER & EVALUATOR ===")
    
    # 1. ALWAYS send a Daily Status Update so you know it ran
    send_telegram_notification("📅 *Daily Job Scraper Update:* Running scan across LinkedIn Job Cards & Direct Hiring Posts...")

    all_items = []
    seen_urls = set()

    # Gather Job Cards
    for kw in JOB_KEYWORDS:
        cards = scrape_linkedin_job_cards(keyword=kw, limit_per_keyword=2)
        for c in cards:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                all_items.append(c)

    # Gather LinkedIn Posts
    posts = scrape_linkedin_hiring_posts()
    for p in posts:
        if p["url"] not in seen_urls:
            seen_urls.add(p["url"])
            all_items.append(p)

    print(f"[PIPELINE] Collected {len(all_items)} total opportunities.")

    matches_found = 0
    for item in all_items:
        eval_res = evaluate_job(USER_PROFILE, item)
        if not eval_res:
            continue

        is_fresher = eval_res.get("is_fresher_or_intern", False)
        score = eval_res.get("fit_score", 0)
        has_apply_link = eval_res.get("has_direct_apply_link", False)
        apply_url = eval_res.get("direct_apply_url", "None")
        stipend = eval_res.get("expected_stipend_or_salary", "Not specified")

        if is_fresher and score >= 70:
            matches_found += 1
            
            # Action logic: Show apply link IF present; show recruiter profile ONLY IF no apply link
            if has_apply_link and apply_url != "None":
                action_block = f"📝 *Apply Directly Here:* [Registration Link]({apply_url})"
            else:
                recruiter_url = item["recruiter"]["profile_url"] or f"https://www.linkedin.com/search/results/people/?keywords=Recruiter%20{item['company']}"
                action_block = (
                    f"👤 *No direct registration link found. Contact Recruiter:* [LinkedIn Profile]({recruiter_url})\n\n"
                    f"💬 *Outreach Note (<280 chars):*\n`{eval_res.get('connection_note')}`\n\n"
                    f"📌 *Tips:* {eval_res.get('messaging_tips')}"
                )

            msg = (
                f"🎯 *New Match ({score}% Fit - {item['source_type']})*\n\n"
                f"*Role:* {item['title']}\n"
                f"*Company/Poster:* {item['company']}\n"
                f"*Stipend/Pay:* {stipend}\n"
                f"*Work Mode:* 🏠 Remote\n\n"
                f"🔗 [View Original Post]({item['url']})\n"
                f"{action_block}"
            )
            send_telegram_notification(msg)
            time.sleep(1)

    send_telegram_notification(f"✅ *Daily Scan Finished:* Processed {len(all_items)} postings, sent {matches_found} qualified alerts.")

if __name__ == "__main__":
    main()