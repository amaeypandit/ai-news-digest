#!/usr/bin/env python3
"""
AI News Digest - Daily Morning Brew style email digest
Fetches AI news from curated sources and sends formatted email.

Approach:
- Source-level filtering: Only pull from AI-specific feeds (no keyword filtering needed)
- Extract real summaries from article content
- Add academic sources (arXiv, Papers With Code)
- Rank by engagement + recency
"""

import os
import sys
import re
import time
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# Categories for organization
CATEGORY_NEW_TECH = "New Technology"
CATEGORY_RESEARCH = "Research"
CATEGORY_INDUSTRY = "Industry & Macro"
CATEGORY_COMMUNITY = "Community Highlights"


def log(message: str) -> None:
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def clean_html(html_text: str) -> str:
    """Clean HTML and return plain text."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    # Remove script and style elements
    for element in soup(["script", "style", "nav", "header", "footer"]):
        element.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def truncate_summary(text: str, max_length: int = 280) -> str:
    """Truncate text to max length at sentence boundary."""
    if not text or len(text) <= max_length:
        return text

    # Try to cut at sentence boundary
    truncated = text[:max_length]
    last_period = truncated.rfind('.')
    last_question = truncated.rfind('?')
    last_exclaim = truncated.rfind('!')

    cut_point = max(last_period, last_question, last_exclaim)
    if cut_point > max_length * 0.5:
        return text[:cut_point + 1]

    # Fall back to word boundary
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return text[:last_space] + "..."
    return truncated + "..."


def fetch_article_summary(url: str, timeout: int = 5) -> str:
    """Fetch and extract summary from article URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try meta description first
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return clean_html(meta_desc["content"])

        # Try og:description
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return clean_html(og_desc["content"])

        # Try first paragraph
        article = soup.find("article") or soup.find("main") or soup.body
        if article:
            paragraphs = article.find_all("p")
            for p in paragraphs[:3]:
                text = clean_html(str(p))
                if len(text) > 100:
                    return truncate_summary(text)

        return ""
    except Exception:
        return ""


# =============================================================================
# RSS FEEDS - AI-Specific Sources (no keyword filtering needed)
# =============================================================================

RSS_FEEDS_NEWS = {
    "TechCrunch AI": "https://techcrunch.com/tag/artificial-intelligence/feed/",
    "VentureBeat AI": "https://venturebeat.com/ai/feed/",
    "The Verge AI": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "Ars Technica AI": "https://arstechnica.com/tag/artificial-intelligence/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
}

RSS_FEEDS_BLOGS = {
    "OpenAI Blog": "https://openai.com/blog/rss/",
    "Anthropic Research": "https://www.anthropic.com/feed.xml",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "DeepMind Blog": "https://deepmind.google/blog/rss.xml",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
}


def fetch_rss_feeds() -> list[dict]:
    """Fetch articles from RSS feeds with proper summaries."""
    articles = []
    all_feeds = {**RSS_FEEDS_NEWS, **RSS_FEEDS_BLOGS}

    for source, url in all_feeds.items():
        try:
            log(f"Fetching RSS: {source}")
            feed = feedparser.parse(url)

            is_blog = source in RSS_FEEDS_BLOGS
            category = CATEGORY_NEW_TECH if is_blog else CATEGORY_INDUSTRY

            for entry in feed.entries[:8]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_date = datetime(*published[:6])
                else:
                    pub_date = datetime.now()

                # Skip articles older than 48 hours
                if (datetime.now() - pub_date).total_seconds() > 48 * 3600:
                    continue

                # Get summary from feed
                summary = entry.get("summary", entry.get("description", ""))
                summary = clean_html(summary)
                summary = truncate_summary(summary)

                # If summary is too short, it's probably not useful
                if len(summary) < 50:
                    summary = ""

                articles.append({
                    "title": clean_html(entry.get("title", "No title")),
                    "link": entry.get("link", ""),
                    "summary": summary,
                    "source": source,
                    "category": category,
                    "published": pub_date,
                    "engagement": 0,
                    "needs_summary": len(summary) < 100,
                })

            time.sleep(0.3)

        except Exception as e:
            log(f"Error fetching {source}: {e}")
            continue

    return articles


# =============================================================================
# ARXIV - Academic Papers
# =============================================================================

def fetch_arxiv() -> list[dict]:
    """Fetch recent AI papers from arXiv."""
    articles = []

    # arXiv categories for AI/ML
    categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV"]

    try:
        log("Fetching arXiv papers")

        # Use arXiv API - get papers from last 2 days, sorted by submission date
        query = "+OR+".join([f"cat:{cat}" for cat in categories])
        url = f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=30"

        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log(f"arXiv returned {resp.status_code}")
            return articles

        soup = BeautifulSoup(resp.text, "xml")
        entries = soup.find_all("entry")

        for entry in entries:
            try:
                title = entry.find("title").text.strip().replace("\n", " ")
                title = re.sub(r'\s+', ' ', title)

                # Get abstract as summary
                abstract = entry.find("summary").text.strip()
                abstract = re.sub(r'\s+', ' ', abstract)
                summary = truncate_summary(abstract, 300)

                link = entry.find("id").text.strip()

                # Parse date
                published_str = entry.find("published").text
                pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)

                # Skip if older than 7 days (arXiv has weekend delays)
                if (datetime.now() - pub_date).total_seconds() > 7 * 24 * 3600:
                    continue

                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": "arXiv",
                    "category": CATEGORY_RESEARCH,
                    "published": pub_date,
                    "engagement": 0,
                    "needs_summary": False,
                })

            except Exception:
                continue

        log(f"Found {len(articles)} recent arXiv papers")

    except Exception as e:
        log(f"Error fetching arXiv: {e}")

    return articles


# =============================================================================
# PAPERS WITH CODE - Trending Research
# =============================================================================

def fetch_papers_with_code() -> list[dict]:
    """Fetch trending papers from Papers With Code via RSS."""
    articles = []

    try:
        log("Fetching Papers With Code trending")

        # Use the RSS feed which is more reliable
        feed = feedparser.parse("https://paperswithcode.com/rss.xml")

        for entry in feed.entries[:15]:
            try:
                title = entry.get("title", "")
                summary = clean_html(entry.get("summary", ""))
                summary = truncate_summary(summary, 300)

                link = entry.get("link", "")
                if not link:
                    continue

                # Parse date
                published = entry.get("published_parsed")
                if published:
                    pub_date = datetime(*published[:6])
                else:
                    pub_date = datetime.now()

                # Skip if older than 7 days
                if (datetime.now() - pub_date).total_seconds() > 7 * 24 * 3600:
                    continue

                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": "Papers With Code",
                    "category": CATEGORY_RESEARCH,
                    "published": pub_date,
                    "engagement": 0,
                    "needs_summary": len(summary) < 100,
                })

            except Exception:
                continue

        log(f"Found {len(articles)} Papers With Code entries")

    except Exception as e:
        log(f"Error fetching Papers With Code: {e}")

    return articles


# =============================================================================
# HACKER NEWS - AI Stories with actual content
# =============================================================================

def fetch_hacker_news() -> list[dict]:
    """Fetch top AI stories from Hacker News with summaries."""
    articles = []

    # AI-related terms for HN filtering (since HN is general)
    # Be more specific to avoid false positives
    ai_terms = [
        " ai ", "a]i", "[ai", "ai,",  # Ensure "ai" is standalone
        "gpt-", "gpt4", "gpt3", "chatgpt", "llm", "llama",
        "claude", "gemini", "openai", "anthropic", "deepmind",
        "machine learning", "deep learning", "neural net",
        "transformer", "diffusion model", "stable diffusion",
        "midjourney", "copilot", "language model", "hugging face",
        "agi", "alignment", "multimodal", "generative ai",
        "fine-tun", "fine tun", "embedding", "rag ", "vector db"
    ]

    try:
        log("Fetching Hacker News top stories")

        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers=HEADERS,
            timeout=10
        )
        story_ids = resp.json()[:100]  # Check more to find AI stories

        for story_id in story_ids:
            if len(articles) >= 10:  # Limit HN articles
                break

            try:
                story_resp = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    headers=HEADERS,
                    timeout=5
                )
                story = story_resp.json()

                if not story or story.get("type") != "story":
                    continue

                title = story.get("title", "").lower()

                # Check if AI-related (need at least one strong signal)
                is_ai = any(term in title for term in ai_terms)
                if not is_ai:
                    continue

                # Additional check: avoid generic tech terms that slip through
                generic_terms = ["bluetooth", "bitcoin", "crypto", "blockchain", "vpn", "browser"]
                if any(term in title for term in generic_terms):
                    continue

                # Must have decent engagement
                score = story.get("score", 0)
                if score < 50:
                    continue

                pub_time = datetime.fromtimestamp(story.get("time", 0))

                # Skip if older than 48 hours
                if (datetime.now() - pub_time).total_seconds() > 48 * 3600:
                    continue

                url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")

                articles.append({
                    "title": story.get("title", ""),
                    "link": url,
                    "summary": "",  # Will fetch later
                    "source": "Hacker News",
                    "category": CATEGORY_COMMUNITY,
                    "published": pub_time,
                    "engagement": score,
                    "needs_summary": True,
                    "hn_comments": story.get("descendants", 0),
                    "hn_id": story_id,
                })

                time.sleep(0.05)

            except Exception:
                continue

        log(f"Found {len(articles)} HN AI stories")

    except Exception as e:
        log(f"Error fetching Hacker News: {e}")

    return articles


# =============================================================================
# REDDIT - AI Subreddits
# =============================================================================

def fetch_reddit() -> list[dict]:
    """Fetch top posts from AI subreddits."""
    articles = []

    # Focused subreddits - these are AI-specific so no keyword filtering needed
    subreddits = [
        ("MachineLearning", CATEGORY_RESEARCH),
        ("LocalLLaMA", CATEGORY_NEW_TECH),
        ("artificial", CATEGORY_INDUSTRY),
        ("OpenAI", CATEGORY_NEW_TECH),
        ("ClaudeAI", CATEGORY_NEW_TECH),
    ]

    for subreddit, category in subreddits:
        try:
            log(f"Fetching Reddit r/{subreddit}")

            resp = requests.get(
                f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15",
                headers=HEADERS,
                timeout=10
            )

            if resp.status_code != 200:
                log(f"Reddit r/{subreddit} returned {resp.status_code}")
                continue

            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})

                # Skip stickied/pinned posts
                if post_data.get("stickied"):
                    continue

                # Must have decent engagement
                score = post_data.get("ups", 0)
                if score < 50:
                    continue

                pub_time = datetime.fromtimestamp(post_data.get("created_utc", 0))

                # Skip if older than 48 hours
                if (datetime.now() - pub_time).total_seconds() > 48 * 3600:
                    continue

                # Get summary from selftext or external link
                selftext = post_data.get("selftext", "")
                if selftext and len(selftext) > 50:
                    summary = truncate_summary(clean_html(selftext), 300)
                else:
                    summary = ""

                # Use external URL if it's a link post
                url = post_data.get("url", "")
                if "reddit.com" in url or not url:
                    url = f"https://reddit.com{post_data.get('permalink', '')}"

                articles.append({
                    "title": post_data.get("title", "No title"),
                    "link": url,
                    "summary": summary,
                    "source": f"r/{subreddit}",
                    "category": category,
                    "published": pub_time,
                    "engagement": score,
                    "needs_summary": len(summary) < 100,
                    "reddit_comments": post_data.get("num_comments", 0),
                })

            time.sleep(1)  # Reddit rate limiting

        except Exception as e:
            log(f"Error fetching r/{subreddit}: {e}")
            continue

    return articles


# =============================================================================
# SUMMARY ENRICHMENT
# =============================================================================

def enrich_summaries(articles: list[dict]) -> list[dict]:
    """Fetch summaries for articles that need them."""
    needs_summary = [a for a in articles if a.get("needs_summary") and a.get("link")]

    if not needs_summary:
        return articles

    log(f"Enriching {len(needs_summary)} articles with summaries")

    def fetch_one(article):
        if "reddit.com" in article["link"] or "news.ycombinator.com" in article["link"]:
            return article  # Skip Reddit/HN comment pages
        summary = fetch_article_summary(article["link"])
        if summary:
            article["summary"] = summary
            article["needs_summary"] = False
        return article

    # Parallel fetch with thread pool
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_one, a): a for a in needs_summary[:20]}
        for future in as_completed(futures, timeout=30):
            try:
                future.result()
            except Exception:
                pass

    return articles


# =============================================================================
# SCORING AND RANKING
# =============================================================================

def calculate_score(article: dict) -> float:
    """Calculate relevance score based on engagement and recency."""
    score = 0.0

    # Recency score (0-40 points)
    hours_old = (datetime.now() - article["published"]).total_seconds() / 3600
    if hours_old <= 12:
        score += 40
    elif hours_old <= 24:
        score += 30
    elif hours_old <= 48:
        score += 20
    else:
        score += 10

    # Engagement score (0-40 points)
    engagement = article.get("engagement", 0)
    if engagement > 500:
        score += 40
    elif engagement > 200:
        score += 30
    elif engagement > 100:
        score += 20
    elif engagement > 50:
        score += 10

    # Source quality bonus (0-20 points)
    high_quality_sources = [
        "OpenAI Blog", "Anthropic Research", "Google AI Blog", "DeepMind Blog",
        "MIT Tech Review", "arXiv", "Papers With Code"
    ]
    if article["source"] in high_quality_sources:
        score += 20
    elif article["source"] in RSS_FEEDS_NEWS:
        score += 10

    # Has good summary bonus
    if article.get("summary") and len(article["summary"]) > 100:
        score += 10

    return score


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove duplicate or very similar articles."""
    unique = []
    seen_titles = []

    for article in articles:
        title = article["title"].lower()

        is_duplicate = False
        for seen in seen_titles:
            similarity = SequenceMatcher(None, title, seen).ratio()
            if similarity > 0.6:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(article)
            seen_titles.append(title)

    return unique


# =============================================================================
# EMAIL FORMATTING
# =============================================================================

def format_html_email(articles: list[dict]) -> str:
    """Format articles into Morning Brew style HTML email."""

    # Group by category
    by_category = {}
    for article in articles:
        cat = article["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(article)

    today = datetime.now().strftime("%B %d, %Y")

    # Category styling
    category_styles = {
        CATEGORY_NEW_TECH: {"icon": "🚀", "color": "#10b981"},
        CATEGORY_RESEARCH: {"icon": "📚", "color": "#8b5cf6"},
        CATEGORY_INDUSTRY: {"icon": "📰", "color": "#3b82f6"},
        CATEGORY_COMMUNITY: {"icon": "💬", "color": "#f59e0b"},
    }

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 640px; margin: 0 auto; padding: 20px; background-color: #f3f4f6;">

    <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 32px; border-radius: 16px; margin-bottom: 24px;">
        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">AI Daily Digest</h1>
        <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0 0; font-size: 15px;">{today}</p>
    </div>

    <div style="background: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #e5e7eb;">
        <p style="font-size: 16px; line-height: 1.7; color: #374151; margin: 0;">
            Good morning! Here's what's happening in AI today — new releases, research breakthroughs, and the conversations that matter.
        </p>
    </div>
"""

    # Order categories
    category_order = [CATEGORY_NEW_TECH, CATEGORY_RESEARCH, CATEGORY_INDUSTRY, CATEGORY_COMMUNITY]

    for category in category_order:
        if category not in by_category:
            continue

        cat_articles = by_category[category][:5]  # Max 5 per category
        style = category_styles.get(category, {"icon": "📌", "color": "#6b7280"})

        html += f"""
    <div style="background: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #e5e7eb;">
        <h2 style="color: {style['color']}; margin: 0 0 20px 0; font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: 8px;">
            <span>{style['icon']}</span> {category}
        </h2>
"""

        for article in cat_articles:
            summary_html = ""
            if article.get("summary"):
                summary_html = f"""<p style="color: #6b7280; margin: 8px 0; font-size: 14px; line-height: 1.6;">{article['summary']}</p>"""

            # Format engagement info
            meta_parts = [article["source"]]
            if article.get("engagement"):
                if "r/" in article["source"]:
                    meta_parts.append(f"↑{article['engagement']}")
                elif article["source"] == "Hacker News":
                    meta_parts.append(f"{article['engagement']} pts")
            meta_parts.append(article["published"].strftime("%b %d"))

            html += f"""
        <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #f3f4f6;">
            <a href="{article['link']}" style="text-decoration: none;">
                <h3 style="color: #111827; margin: 0; font-size: 15px; font-weight: 600; line-height: 1.5;">{article['title']}</h3>
            </a>
            {summary_html}
            <p style="color: #9ca3af; margin: 8px 0 0 0; font-size: 12px;">{' · '.join(meta_parts)}</p>
        </div>
"""

        html += "    </div>\n"

    # Footer
    html += """
    <div style="text-align: center; padding: 24px; color: #9ca3af; font-size: 12px;">
        <p style="margin: 0;">Generated by AI News Digest</p>
        <p style="margin: 4px 0 0 0;">Curated from arXiv, tech news, and community discussions</p>
    </div>

</body>
</html>
"""

    return html


def format_plain_text(articles: list[dict]) -> str:
    """Format articles as plain text fallback."""
    today = datetime.now().strftime("%B %d, %Y")

    text = f"""AI DAILY DIGEST - {today}
{'=' * 50}

"""

    # Group by category
    by_category = {}
    for article in articles:
        cat = article["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(article)

    for category, cat_articles in by_category.items():
        text += f"\n{category.upper()}\n{'-' * 40}\n\n"
        for article in cat_articles[:5]:
            text += f"• {article['title']}\n"
            if article.get("summary"):
                text += f"  {article['summary'][:200]}...\n"
            text += f"  {article['source']} | {article['link']}\n\n"

    return text


# =============================================================================
# EMAIL SENDING
# =============================================================================

def send_email(html_content: str, text_content: str) -> bool:
    """Send the digest email via SMTP."""

    if not all([SMTP_USERNAME, SMTP_PASSWORD, RECIPIENT_EMAIL]):
        log("ERROR: Missing email configuration. Check .env file.")
        return False

    try:
        log(f"Sending email to {RECIPIENT_EMAIL}")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"AI Daily Digest - {datetime.now().strftime('%B %d, %Y')}"
        msg["From"] = SMTP_USERNAME
        msg["To"] = RECIPIENT_EMAIL

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        log("Email sent successfully!")
        return True

    except Exception as e:
        log(f"ERROR sending email: {e}")
        return False


def save_to_file(html_content: str) -> str:
    """Save digest to .tmp for debugging."""
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    filename = f"digest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(tmp_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    log(f"Digest saved to {filepath}")
    return filepath


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    log("Starting AI News Digest v2")

    # Fetch from all sources
    all_articles = []

    # Parallel fetch from different source types
    all_articles.extend(fetch_rss_feeds())
    all_articles.extend(fetch_arxiv())
    all_articles.extend(fetch_papers_with_code())
    all_articles.extend(fetch_hacker_news())
    all_articles.extend(fetch_reddit())

    log(f"Fetched {len(all_articles)} total articles")

    if not all_articles:
        log("No articles found.")
        return

    # Enrich articles that need summaries
    all_articles = enrich_summaries(all_articles)

    # Calculate scores
    for article in all_articles:
        article["score"] = calculate_score(article)

    # Sort by score within each category
    all_articles.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate
    articles = deduplicate_articles(all_articles)
    log(f"After deduplication: {len(articles)} unique articles")

    # Format email
    html_content = format_html_email(articles)
    text_content = format_plain_text(articles)

    # Save to file
    save_to_file(html_content)

    # Send email
    success = send_email(html_content, text_content)

    if success:
        log("Digest completed successfully!")
    else:
        log("Digest saved locally but email failed. Check configuration.")


if __name__ == "__main__":
    main()
