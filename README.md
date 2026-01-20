# AI News Digest

A daily email digest of AI news, delivered to your inbox every morning at 8am EST.

## What You Get

A curated digest organized into four sections:

- **New Technology** - Product launches, model releases, tool announcements
- **Research** - Academic papers from arXiv, technical deep-dives
- **Industry & Macro** - Business news, policy, market developments
- **Community Highlights** - Popular discussions from Hacker News and Reddit

## Sources

| Source | Type |
|--------|------|
| TechCrunch, VentureBeat, Wired, Ars Technica, MIT Tech Review | News RSS |
| OpenAI, Anthropic, Google AI, DeepMind, Hugging Face | Company Blogs |
| arXiv (cs.AI, cs.LG, cs.CL, cs.CV) | Academic Papers |
| r/MachineLearning, r/LocalLLaMA, r/OpenAI, r/ClaudeAI | Reddit |
| Hacker News | Community |

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/amaeypandit/ai-news-digest.git
cd ai-news-digest
pip install -r requirements.txt
```

### 2. Configure email

Create a `.env` file:

```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
RECIPIENT_EMAIL=recipient@example.com
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password).

### 3. Run manually

```bash
python execution/ai_news_digest.py
```

## Automation

This repo uses GitHub Actions to send the digest daily at 8am EST.

To set up your own:

1. Fork this repo
2. Add secrets in Settings → Secrets → Actions:
   - `SMTP_SERVER`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `RECIPIENT_EMAIL`
3. The workflow runs automatically, or trigger manually from the Actions tab

## License

MIT
