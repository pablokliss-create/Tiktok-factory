#!/usr/bin/env python3
"""Build a zero-paid-API editorial queue from public RSS feeds."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "topics.json"
SEEN = ROOT / "seen.json"
JOB_PREFIX = "job_"

def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TikTokFactory/0.1 (+GitHub Actions)"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()

def clean(text):
    text = text or ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def parse_feed(raw, source):
    root = ET.fromstring(raw)
    result = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = clean(item.findtext("description") or "")

        if title and link:
            result.append({
                "title": title,
                "link": link,
                "description": description,
                "source": source
            })

    return result

def norm(text):
    return re.sub(r"[^a-z0-9à-ÿ]+", " ", text.lower()).strip()

def score(item, cfg):
    text = norm(item["title"] + " " + item["description"])

    high = sum(4 for k in cfg["keywords"]["high"] if norm(k) in text)
    medium = sum(2 for k in cfg["keywords"]["medium"] if norm(k) in text)
    negative = sum(8 for k in cfg["keywords"]["negative"] if norm(k) in text)
    novelty = 2 if any(
        k in text for k in ("novo", "new", "lançou", "launch", "revela")
    ) else 0

    return max(0, 50 + high + medium + novelty - negative)

def slug(text):
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value[:60] or "topic"

def main():
    cfg = load_json(CONFIG, {})
    seen = load_json(SEEN, {})
    candidates = []

    for feed in cfg.get("feeds", []):
        try:
            for item in parse_feed(fetch(feed), feed):
                item["id"] = hashlib.sha256(
                    norm(item["title"]).encode()
                ).hexdigest()[:16]

                if item["id"] not in seen:
                    item["score"] = score(item, cfg)
                    candidates.append(item)

        except Exception as exc:
            print(f"[WARN] feed failed: {feed}: {exc}", file=sys.stderr)

    candidates.sort(key=lambda x: (-x["score"], x["title"]))

    chosen = []
    chosen_titles = []
    limit = cfg.get("channel", {}).get("max_queue_items_per_run", 3)

    for item in candidates:
        title = norm(item["title"])

        if any(title in old or old in title for old in chosen_titles):
            continue

        chosen.append(item)
        chosen_titles.append(title)

        if len(chosen) >= limit:
            break

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")

    for item in chosen:
        job_id = f"{timestamp}-{item['id']}"

        brief = {
            "id": job_id,
            "status": "queued",
            "created_at": now.isoformat(),
            "language": cfg.get("channel", {}).get("language", "pt-BR"),
            "score": item["score"],
            "topic": item["title"],
            "title": item["title"],
            "hook": f"Você precisa saber disso sobre {item['title']}.",
            "script": (
                f"Hoje vamos falar sobre {item['title']}. "
                f"{item['description'][:700]} "
                "O ponto principal é entender por que essa notícia importa. "
                "Confira a fonte para os detalhes completos."
            ),
            "visual_keywords": [
                item["title"],
                "technology",
                "news"
            ],
            "caption": item["title"],
            "hashtags": [
                "#tecnologia",
                "#ia",
                "#noticias"
            ],
            "source": item["source"],
            "source_url": item["link"],
            "production": {
                "engine": "MoneyPrinterTurbo",
                "duration_target_seconds": 45
            }
        }

        filename = ROOT / f"{JOB_PREFIX}{job_id}-{slug(item['title'])}.json"
        filename.write_text(
            json.dumps(brief, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        seen[item["id"]] = now.isoformat()

    SEEN.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Candidates: {len(candidates)} | Queued: {len(chosen)}")

if __name__ == "__main__":
    main()
