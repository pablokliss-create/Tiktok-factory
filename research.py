#!/usr/bin/env python3
"""Editorial Brain: Research public feeds with zero paid APIs, filter old/SEO content, and build rich TikTok jobs."""

from __future__ import annotations

import email.utils
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "topics.json"
SEEN = ROOT / "seen.json"
JOB_PREFIX = "job_"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def clean(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    date_str = date_str.strip()
    # RFC 2822 / 822 format (e.g. Mon, 28 Oct 2026 14:00:00 GMT)
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass

    # ISO 8601 format (e.g. 2026-10-28T14:00:00Z)
    clean_iso = date_str.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(clean_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TikTokFactory/1.0"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def parse_feed(raw: bytes, feed_meta: Dict[str, str]) -> List[Dict[str, Any]]:
    items = []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[WARN] XML parse error for {feed_meta.get('name')}: {e}", file=sys.stderr)
        return items

    source_name = feed_meta.get("name", "Unknown Source")
    category = feed_meta.get("category", "tech")

    # RSS 2.0 <channel><item>
    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        desc = clean(item.findtext("description"))
        pub_date_str = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date")
        pub_dt = parse_date(pub_date_str)

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "published_at": pub_dt,
                "source": source_name,
                "category": category,
            })

    # Atom <entry>
    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", atom_ns) or root.findall(".//entry"):
        title = clean(entry.findtext("title") or entry.findtext("atom:title", namespaces=atom_ns))
        link_elem = entry.find("atom:link", atom_ns) or entry.find("link")
        link = link_elem.get("href", "").strip() if link_elem is not None else ""
        desc = clean(entry.findtext("summary") or entry.findtext("content") or entry.findtext("atom:summary", namespaces=atom_ns))
        pub_date_str = (
            entry.findtext("published")
            or entry.findtext("updated")
            or entry.findtext("atom:published", namespaces=atom_ns)
            or entry.findtext("atom:updated", namespaces=atom_ns)
        )
        pub_dt = parse_date(pub_date_str)

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "published_at": pub_dt,
                "source": source_name,
                "category": category,
            })

    return items


def is_valid_candidate(item: Dict[str, Any], cfg: Dict[str, Any], now: datetime) -> bool:
    title = item["title"].lower()
    desc = item.get("description", "").lower()
    combined = f"{title} {desc}"

    # 1. Date requirement
    pub_dt = item.get("published_at")
    if not pub_dt:
        return False  # Reject articles with no verifiable publication date

    age_hours = (now - pub_dt).total_seconds() / 3600.0
    max_age = cfg.get("channel", {}).get("max_age_hours", 168)  # Default 7 days
    if age_hours < 0 or age_hours > max_age:
        return False  # Future date glitch or older than allowed window

    # 2. Negative patterns (anti-clickbait, anti-listicle, anti-SEO reviews)
    for pat in cfg.get("negative_patterns", []):
        if re.search(pat, combined, re.IGNORECASE):
            return False

    # 3. Minimum substance check
    if len(item["title"]) < 12:
        return False

    return True


def determine_format(title: str, desc: str) -> str:
    combined = f"{title} {desc}".lower()

    if any(k in combined for k in ["why", "por que", "porque", "como funciona", "how", "mystery", "explained"]):
        return "WHY"
    if any(k in combined for k in ["bizarre", "weird", "stranger", "wtf", "inacreditável", "absurd", "glitch", "flaw", "hacked", "secret"]):
        return "WTF"
    if any(k in combined for k in ["history", "the story of", "how one", "found", "discovered", "journey", "investigation"]):
        return "STORY"
    return "NOW"


def score_item(item: Dict[str, Any], now: datetime) -> int:
    base_score = 40
    title = item["title"].lower()
    desc = item.get("description", "").lower()
    combined = f"{title} {desc}"

    # Recency score (max 35)
    pub_dt = item.get("published_at")
    if pub_dt:
        age_hours = (now - pub_dt).total_seconds() / 3600.0
        if age_hours <= 24:
            base_score += 35
        elif age_hours <= 48:
            base_score += 25
        elif age_hours <= 72:
            base_score += 15
        elif age_hours <= 168:
            base_score += 5

    # Curiosity & impact keywords (+5 each, up to 30)
    curiosity_keywords = [
        "breakthrough", "discovery", "first ever", "inédito", "descoberta",
        "nasa", "james webb", "quantum", "robot", "humanoid", "zero-day",
        "cyber", "satellite", "mars", "space", "fusion", "supercomputer",
        "autonomous", "telescope", "physics", "security", "ai model", "chip"
    ]
    curiosity_hits = sum(5 for k in curiosity_keywords if k in combined)
    base_score += min(30, curiosity_hits)

    # Authority bonus
    if item.get("source") in ["NASA News", "MIT Technology Review", "Ars Technica"]:
        base_score += 10

    return base_score


def generate_editorial_package(item: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    title_raw = item["title"]
    desc_raw = item.get("description", "")
    source_name = item.get("source", "Fonte Especializada")

    # Clean description to first 2-3 sentences for factual grounding
    desc_sentences = [s.strip() for s in re.split(r"[.!?]", desc_raw) if len(s.strip()) > 15]
    factual_body = ". ".join(desc_sentences[:3]) if desc_sentences else desc_raw[:350]
    if factual_body and not factual_body.endswith("."):
        factual_body += "."

    if fmt == "NOW":
        hook = f"Isso acabou de acontecer na ciência e tecnologia: {title_raw}."
        script = (
            f"{hook} "
            f"De acordo com relatórios publicados pela {source_name}, os novos dados confirmam: {factual_body} "
            "Isso muda completamente o cenário porque abre portas para aplicações que antes pareciam distantes. "
            "Acompanhe o canal para as próximas atualizações desta história."
        )
    elif fmt == "WHY":
        hook = f"Você já se perguntou por que todo mundo está comentando sobre {title_raw}?"
        script = (
            f"{hook} "
            f"A explicação técnica revelada pela {source_name} é fascinante: {factual_body} "
            "O detalhe crucial é o impacto real que essa descoberta causa na infraestrutura que usamos todos os dias. "
            "Você acha que isso vai transformar o setor nos próximos meses?"
        )
    elif fmt == "WTF":
        hook = f"Parece ficção científica, mas é 100% real: {title_raw}."
        script = (
            f"{hook} "
            f"Uma investigação detalhada divulgada pela {source_name} trouxe à tona os seguintes fatos: {factual_body} "
            "O mais surpreendente é como essa falha ou fenômeno passou despercebido até agora. "
            "Deixe nos comentários a sua teoria sobre o caso."
        )
    else:  # STORY
        hook = f"A história real por trás de {title_raw} é muito mais impressionante do que parece."
        script = (
            f"{hook} "
            f"Tudo começou com uma série de eventos documentados pela {source_name}: {factual_body} "
            "O resultado final surpreendeu até mesmo os especialistas envolvidos. "
            "Qual lição você tira dessa reviravolta?"
        )

    # Build scene plan
    scene_plan = [
        {
            "scene": 1,
            "duration_seconds": 6,
            "voice_line": hook,
            "visual_direction": f"High impact visual representing {title_raw}, cinematic lighting.",
        },
        {
            "scene": 2,
            "duration_seconds": 18,
            "voice_line": factual_body[:180],
            "visual_direction": "Technical details, schematics, motion graphics or real-world footage.",
        },
        {
            "scene": 3,
            "duration_seconds": 12,
            "voice_line": "O ponto central é o impacto prático dessa revelação para o futuro imediato.",
            "visual_direction": "Modern futuristic environment, dynamic transitions.",
        },
    ]

    # Visual keywords for search
    words = re.findall(r"\b[A-Za-z0-9]{4,}\b", title_raw)
    visual_keywords = list(dict.fromkeys(words[:4] + [item.get("category", "tech"), "technology", "futuristic"]))

    hashtags = [
        "#curiosidades",
        "#tecnologia",
        "#ciencia",
        f"#{item.get('category', 'tech')}",
        "#fatosreais",
    ]

    return {
        "format": fmt,
        "hook": hook,
        "angle": f"Curiosidade e impacto de {title_raw}",
        "summary": factual_body,
        "script": script,
        "scene_plan": scene_plan,
        "visual_keywords": visual_keywords,
        "caption": f"{title_raw} | Fatos verificados via {source_name}",
        "hashtags": hashtags,
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value[:60] or "topic"


def main():
    cfg = load_json(CONFIG, {})
    seen = load_json(SEEN, {})
    now = datetime.now(timezone.utc)
    candidates: List[Dict[str, Any]] = []

    feeds = cfg.get("feeds", [])
    print(f"[*] Starting research across {len(feeds)} sources...")

    for feed_entry in feeds:
        feed_meta = feed_entry if isinstance(feed_entry, dict) else {"url": str(feed_entry), "name": "RSS Feed", "category": "tech"}
        url = feed_meta.get("url")
        if not url:
            continue
        try:
            raw_data = fetch(url)
            parsed_items = parse_feed(raw_data, feed_meta)
            valid_count = 0
            for item in parsed_items:
                item_hash = hashlib.sha256(item["title"].lower().strip().encode()).hexdigest()[:16]
                item["id"] = item_hash

                if item_hash not in seen and is_valid_candidate(item, cfg, now):
                    item["score"] = score_item(item, now)
                    candidates.append(item)
                    valid_count += 1
            print(f"  [+] {feed_meta.get('name')}: found {len(parsed_items)} items, {valid_count} valid candidates.")
        except Exception as exc:
            print(f"  [-] Feed failed ({feed_meta.get('name')}): {exc}", file=sys.stderr)

    candidates.sort(key=lambda x: (-x["score"], x["title"]))

    chosen: List[Dict[str, Any]] = []
    chosen_titles: List[str] = []
    limit = cfg.get("channel", {}).get("max_queue_items_per_run", 5)

    for item in candidates:
        norm_title = re.sub(r"[^a-z0-9]+", " ", item["title"].lower()).strip()
        if any(norm_title in old or old in norm_title for old in chosen_titles):
            continue

        chosen.append(item)
        chosen_titles.append(norm_title)
        if len(chosen) >= limit:
            break

    timestamp = now.strftime("%Y%m%d-%H%M%S")

    for item in chosen:
        job_id = f"{timestamp}-{item['id']}"
        fmt = determine_format(item["title"], item.get("description", ""))
        editorial = generate_editorial_package(item, fmt)

        job_data = {
            "id": job_id,
            "status": "ready_for_production",
            "created_at": now.isoformat(),
            "published_at": item["published_at"].isoformat() if item.get("published_at") else None,
            "language": cfg.get("channel", {}).get("language", "pt-BR"),
            "score": item["score"],
            "format": fmt,
            "category": item.get("category", "tech"),
            "topic": item["title"],
            "title": item["title"],
            "hook": editorial["hook"],
            "angle": editorial["angle"],
            "summary": editorial["summary"],
            "script": editorial["script"],
            "scene_plan": editorial["scene_plan"],
            "visual_keywords": editorial["visual_keywords"],
            "caption": editorial["caption"],
            "hashtags": editorial["hashtags"],
            "sources": [{"name": item["source"], "url": item["link"]}],
            "source": item["source"],
            "source_url": item["link"],
            "production": {
                "engine": "MoneyPrinterTurbo",
                "voice_name": "pt-BR-AntonioNeural",
                "video_aspect": "9:16",
                "duration_target_seconds": 45,
            },
        }

        filename = ROOT / f"{JOB_PREFIX}{job_id}-{slug(item['title'])}.json"
        filename.write_text(
            json.dumps(job_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        seen[item["id"]] = now.isoformat()
        print(f"[OK] Generated job ({fmt}, score={item['score']}): {filename.name}")

    SEEN.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Total candidates evaluated: {len(candidates)} | Created jobs: {len(chosen)}")


if __name__ == "__main__":
    main()
