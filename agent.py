"""
Research engine for the AI Marketing Brief Bot.
All research functions live here — bot.py imports and calls run_research().
"""

import concurrent.futures
import json
import os
import time as time_module
from datetime import datetime, timezone

import anthropic
import requests

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
XAI_API_KEY = os.environ["XAI_API_KEY"]
SCRAPECREATORS_API_KEY = os.environ["SCRAPECREATORS_API_KEY"]
FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]

RESEARCH_TOPIC = "Claude Code and AI tools for marketing"


# ---------------------------------------------------------------------------
# Lane A — X/Twitter via xAI Grok (last 24h)
# ---------------------------------------------------------------------------

def search_twitter(topic: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    try:
        resp = requests.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "grok-3-fast",
                "input": [
                    {
                        "role": "user",
                        "content": (
                            f"Today is {today}. Search X/Twitter for the most viral and trending "
                            f"posts from the LAST 24 HOURS about: Claude Code being used for marketing, "
                            f"Anthropic Claude AI tools for marketers, using Claude agents to automate marketing workflows. "
                            f"Focus specifically on Claude and Anthropic tools — not generic AI marketing. "
                            f"What are people sharing RIGHT NOW? Include engagement numbers and direct post URLs."
                        ),
                    }
                ],
                "tools": [{"type": "x_search"}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return {"success": True, "text": content["text"], "source": "X/Twitter"}
        return {"success": False, "text": "No output text in response", "source": "X/Twitter"}
    except Exception as e:
        return {"success": False, "text": str(e), "source": "X/Twitter"}


# ---------------------------------------------------------------------------
# Lane B — Reddit via ScrapeCreators (last 24h)
# ---------------------------------------------------------------------------

def search_reddit(topic: str) -> dict:
    posts = []
    try:
        resp = requests.get(
            "https://api.scrapecreators.com/v1/reddit/search",
            headers={"x-api-key": SCRAPECREATORS_API_KEY},
            params={"query": topic, "sort": "new", "time": "day"},
            timeout=30,
        )
        resp.raise_for_status()
        for p in resp.json().get("posts", [])[:8]:
            posts.append({
                "title": p.get("title", ""),
                "score": p.get("score", 0),
                "subreddit": p.get("subreddit", ""),
                "url": p.get("url", ""),
                "preview": (p.get("body", "") or "")[:200],
            })

        for sub in ["marketing", "socialmedia", "automation", "artificial"]:
            try:
                r2 = requests.get(
                    "https://api.scrapecreators.com/v1/reddit/subreddit/search",
                    headers={"x-api-key": SCRAPECREATORS_API_KEY},
                    params={"subreddit": sub, "query": topic, "sort": "new", "time": "day"},
                    timeout=30,
                )
                r2.raise_for_status()
                for p in r2.json().get("posts", [])[:3]:
                    posts.append({
                        "title": p.get("title", ""),
                        "score": p.get("score", 0),
                        "subreddit": p.get("subreddit", sub),
                        "url": p.get("url", ""),
                    })
            except Exception:
                pass

        seen = set()
        unique = []
        for p in sorted(posts, key=lambda x: x.get("score", 0), reverse=True):
            if p["url"] not in seen:
                seen.add(p["url"])
                unique.append(p)

        return {"success": True, "posts": unique[:15], "source": "Reddit"}
    except Exception as e:
        return {"success": False, "posts": [], "source": "Reddit", "error": str(e)}


# ---------------------------------------------------------------------------
# Lane C — Instagram Reels via ScrapeCreators (filtered to 24h)
# ---------------------------------------------------------------------------

def search_instagram(topic: str) -> dict:
    reels = []
    cutoff = int(datetime.now(timezone.utc).timestamp()) - 86400  # 24h ago
    queries = ["Claude Code marketing", "AI tools marketing automation"]
    try:
        for q in queries:
            resp = requests.get(
                "https://api.scrapecreators.com/v2/instagram/reels/search",
                headers={"x-api-key": SCRAPECREATORS_API_KEY},
                params={"query": q, "limit": 15},
                timeout=30,
            )
            print(f"  [Instagram] query={q!r} status={resp.status_code} body={resp.text[:200]}")
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("reels", data.get("data", data.get("items", [])))
                for r in items:
                    views = r.get("video_view_count", 0) or 0
                    likes = r.get("like_count", 0) or 0
                    er = round(likes / views * 100, 2) if views > 0 else 0
                    shortcode = r.get("shortcode", "")
                    reels.append({
                        "username": r.get("owner", {}).get("username", ""),
                        "followers": r.get("owner", {}).get("follower_count", 0),
                        "caption": (r.get("caption", "") or "")[:180],
                        "views": views,
                        "likes": likes,
                        "er": er,
                        "taken_at": r.get("taken_at", 0) or 0,
                        "url": f"https://www.instagram.com/p/{shortcode}/" if shortcode else "",
                    })

        # Prefer last 24h; fall back to most recent 5 if too few
        fresh = [r for r in reels if r["taken_at"] >= cutoff]
        pool = fresh if len(fresh) >= 3 else sorted(reels, key=lambda x: x["taken_at"], reverse=True)[:5]
        pool.sort(key=lambda x: x["er"], reverse=True)

        return {"success": True, "reels": pool[:8], "source": "Instagram"}
    except Exception as e:
        return {"success": False, "reels": [], "source": "Instagram", "error": str(e)}


# ---------------------------------------------------------------------------
# Lane D — YouTube via Firecrawl web search
# ---------------------------------------------------------------------------

def search_youtube(topic: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    videos = []
    year = datetime.now().year
    queries = [
        f"site:youtube.com Claude Code marketing {year}",
        f"site:youtube.com AI tools marketing automation {year}",
    ]
    try:
        for q in queries:
            resp = requests.post(
                "https://api.firecrawl.dev/v1/search",
                headers={
                    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"query": q, "limit": 4},
                timeout=30,
            )
            print(f"  [YouTube] query={q!r} status={resp.status_code}")
            if resp.status_code == 200:
                for r in resp.json().get("data", []):
                    url = r.get("url", "")
                    if "youtube.com" in url or "youtu.be" in url:
                        videos.append({
                            "title": r.get("metadata", {}).get("title", ""),
                            "url": url,
                            "description": r.get("metadata", {}).get("description", ""),
                        })

        seen = set()
        unique = [v for v in videos if v["url"] not in seen and not seen.add(v["url"])]
        return {"success": bool(unique), "videos": unique[:6], "source": "YouTube"}
    except Exception as e:
        return {"success": False, "videos": [], "source": "YouTube", "error": str(e)}


# ---------------------------------------------------------------------------
# Lane E — Web news via Firecrawl
# ---------------------------------------------------------------------------

def search_web(topic: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "query": f"Claude Code AI marketing tools automation {today}",
                "limit": 5,
                "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
            },
            timeout=45,
        )
        resp.raise_for_status()
        articles = []
        for r in resp.json().get("data", []):
            url = r.get("url", "")
            if "youtube.com" not in url:  # YouTube handled by its own lane
                articles.append({
                    "title": r.get("metadata", {}).get("title", ""),
                    "url": url,
                    "description": r.get("metadata", {}).get("description", ""),
                    "preview": (r.get("markdown", "") or "")[:400],
                })
        return {"success": True, "articles": articles, "source": "Web"}
    except Exception as e:
        return {"success": False, "articles": [], "source": "Web", "error": str(e)}


# ---------------------------------------------------------------------------
# Synthesis — Claude writes the brief
# ---------------------------------------------------------------------------

def synthesize_brief(results: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    twitter = results.get("twitter", {})
    reddit = results.get("reddit", {})
    instagram = results.get("instagram", {})
    youtube = results.get("youtube", {})
    web = results.get("web", {})

    research_dump = f"""
=== X/TWITTER ({"live" if twitter.get("success") else "failed"}) ===
{twitter.get("text", "no data")}

=== REDDIT ({"live" if reddit.get("success") else "failed"}) ===
{json.dumps(reddit.get("posts", []), indent=2)}

=== INSTAGRAM REELS ({"live" if instagram.get("success") else "failed"}) ===
{json.dumps(instagram.get("reels", []), indent=2)}

=== YOUTUBE ({"live" if youtube.get("success") else "failed"}) ===
{json.dumps(youtube.get("videos", []), indent=2)}

=== WEB NEWS ({"live" if web.get("success") else "failed"}) ===
{json.dumps(web.get("articles", []), indent=2)}
""".strip()

    prompt = f"""Today is {today}. You are scanning social media for trending content about Claude Code and AI tools used in marketing.

Extract the top 5-6 trending topics from the research below. For each topic output:
- A short bold headline (5-8 words)
- One sentence summary: what's happening and why it matters for marketers
- The direct URL(s) to the actual post on X, Instagram, Reddit, or YouTube

Output format for Telegram HTML (no intro text, start straight with the header):

<b>Claude Code & AI Marketing — {today}</b>

<b>1. [Headline]</b>
[One sentence: what it is + why it matters for marketers.]
<a href="URL">X</a> · <a href="URL">Instagram</a>

<b>2. [Headline]</b>
[One sentence summary.]
<a href="URL">Reddit</a>

(repeat for each topic)

RULES:
- Only include topics specifically about Claude Code or Anthropic AI tools used in marketing — skip generic AI marketing news
- Only use URLs that appear verbatim in the research data — never invent or guess URLs
- If a topic has no direct post URL, skip it
- Summary must be ONE sentence max — scannable at a glance
- Prefer X and Instagram links; Reddit and YouTube as fallback
- Max 6 topics, keep total under 1500 characters

Research data:
{research_dump}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Public API — called by bot.py
# ---------------------------------------------------------------------------

def run_research() -> str:
    """Run all 5 research lanes in parallel, synthesize, return brief text."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Launching 5 research lanes...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            "twitter": pool.submit(search_twitter, RESEARCH_TOPIC),
            "reddit": pool.submit(search_reddit, RESEARCH_TOPIC),
            "instagram": pool.submit(search_instagram, RESEARCH_TOPIC),
            "youtube": pool.submit(search_youtube, RESEARCH_TOPIC),
            "web": pool.submit(search_web, RESEARCH_TOPIC),
        }
        results = {k: f.result() for k, f in futures.items()}

    live = [k for k, v in results.items() if v.get("success")]
    dead = [k for k, v in results.items() if not v.get("success")]
    print(f"  Live: {', '.join(live) or 'none'}")
    if dead:
        print(f"  Failed: {', '.join(dead)}")

    if not live:
        raise RuntimeError("All research lanes failed.")

    print("Synthesizing with Claude...")
    brief = synthesize_brief(results)
    return brief
