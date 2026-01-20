# AI News Digest Directive

## Goal
Automatically curate AI-related content from free sources and send a daily "Morning Brew" style digest via email every morning at 8am. Focus on: new technologies, research breakthroughs, industry macro developments, and popular community discussions.

## Inputs
- Configuration from `.env` file:
  - Email sender credentials (SMTP server, port, username, password)
  - Recipient email address

## Content Categories

The digest is organized into four sections:
1. **New Technology** - Product launches, model releases, tool announcements (from company blogs, r/LocalLLaMA, r/OpenAI, r/ClaudeAI)
2. **Research** - Academic papers and technical deep-dives (from arXiv, r/MachineLearning)
3. **Industry & Macro** - Business news, policy, market developments (from tech news RSS)
4. **Community Highlights** - Popular discussions and projects (from Hacker News, Reddit)

## Data Sources

### RSS Feeds - News (AI-specific tags, no keyword filtering needed)
- TechCrunch AI: `https://techcrunch.com/tag/artificial-intelligence/feed/`
- VentureBeat AI: `https://venturebeat.com/ai/feed/`
- The Verge AI: `https://www.theverge.com/ai-artificial-intelligence/rss/index.xml`
- Ars Technica AI: `https://arstechnica.com/tag/artificial-intelligence/feed/`
- MIT Tech Review: `https://www.technologyreview.com/topic/artificial-intelligence/feed/`
- Wired AI: `https://www.wired.com/feed/tag/ai/latest/rss`

### RSS Feeds - Company Blogs
- OpenAI Blog: `https://openai.com/blog/rss/`
- Anthropic Research: `https://www.anthropic.com/feed.xml`
- Google AI Blog: `https://blog.google/technology/ai/rss/`
- DeepMind Blog: `https://deepmind.google/blog/rss.xml`
- Hugging Face Blog: `https://huggingface.co/blog/feed.xml`

### Academic Sources
- **arXiv API** - Categories: cs.AI, cs.LG, cs.CL, cs.CV
  - URL: `http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG...`
  - Provides paper abstracts as summaries
  - Allow 7-day window (arXiv has weekend submission delays)

### Reddit (JSON API, no auth needed)
- r/MachineLearning → Research category
- r/LocalLLaMA → New Technology category
- r/artificial → Industry category
- r/OpenAI → New Technology category
- r/ClaudeAI → New Technology category

**Reddit filtering:**
- Minimum 50 upvotes
- Skip stickied posts
- Max 48 hours old
- Extract selftext as summary when available

### Hacker News (Firebase API, no auth needed)
- Fetch top 100 stories, filter for AI-related
- Minimum 50 points
- Max 48 hours old

**HN filtering approach:**
- Use specific AI terms (avoid generic words like "model" alone)
- Include: llm, gpt, chatgpt, claude, gemini, openai, anthropic, machine learning, deep learning, transformer, etc.
- Exclude: bluetooth, bitcoin, crypto, blockchain (common false positives)

## Summary Extraction

**Priority order for getting article summaries:**
1. RSS feed `<summary>` or `<description>` field (clean HTML)
2. Meta description tag from article URL
3. OpenGraph `og:description` tag
4. First substantial paragraph from article body

**For academic papers:**
- arXiv provides full abstracts - truncate to ~300 chars

**For Reddit:**
- Use post selftext when available
- Truncate to 300 chars at sentence boundary

## Scoring Algorithm

Articles are scored (0-100+) based on:

| Factor | Points | Notes |
|--------|--------|-------|
| Recency (≤12h) | 40 | Fresher = better |
| Recency (12-24h) | 30 | |
| Recency (24-48h) | 20 | |
| Engagement >500 | 40 | Upvotes/points |
| Engagement >200 | 30 | |
| Engagement >100 | 20 | |
| Engagement >50 | 10 | |
| High-quality source | 20 | OpenAI, Anthropic, arXiv, etc. |
| News source | 10 | TechCrunch, Wired, etc. |
| Has good summary | 10 | >100 chars |

## Output Format

HTML email with:
- Header with date
- Brief intro paragraph
- 4 category sections (max 5 articles each)
- Each article shows: title (linked), summary, source + engagement + date
- Clean, mobile-friendly design

## Tools/Scripts

- `execution/ai_news_digest.py` - Main script

## Dependencies

```
feedparser>=6.0.0
requests>=2.28.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
lxml  # For XML parsing (arXiv)
```

## Scheduling

```bash
# Add to crontab for daily 8am execution
0 8 * * * cd /path/to/News && /usr/bin/python3 execution/ai_news_digest.py >> .tmp/cron.log 2>&1
```

## Debugging

- Digests are saved to `.tmp/digest_YYYYMMDD_HHMMSS.html` before sending
- All operations are logged with timestamps
- Script continues if individual sources fail

## Learnings & Updates

### 2026-01-19
- **arXiv date filtering**: Extended from 48h to 7 days due to weekend submission delays
- **Papers With Code**: API unreliable, switched to RSS feed (also unreliable, may need alternative)
- **HN false positives**: Added exclusion list for generic tech terms (bluetooth, bitcoin, etc.)
- **Summary extraction**: Priority order established - RSS > meta description > og:description > first paragraph
- **Keyword filtering removed**: Using source-level curation instead (AI-specific RSS tags, subreddits)
