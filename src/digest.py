"""
News Digest Bot — 6h & 21h WAT
- 1 seule requête Gemini par digest (quota free tier = 20 req/jour)
- Troncature dynamique selon nombre d'articles
- Formatage HTML fait en Python
- Timestamp persistant via GitHub Cache
"""

import os
import re
import json
import time
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

TZ_WAT = ZoneInfo("Africa/Douala")
LAST_RUN_FILE = "/tmp/last_run_timestamp.json"

RSS_SOURCES = {
    "🇨🇲 Cameroun": [
        "https://www.cameroon-tribune.cm/rss.xml",
        "https://actucameroun.com/feed/",
        "https://www.crtv.cm/feed/",
        "https://www.jeuneafrique.com/pays/cameroun/feed/",
        "https://www.lemonde.fr/cameroun/rss_full.xml",
        "https://www.rfi.fr/fr/afrique/rss",
    ],
    "🌍 Afrique": [
        "https://www.jeuneafrique.com/feed/",
        "https://www.bbc.com/afrique/index.xml",
        "https://www.rfi.fr/fr/rss/afrique.xml",
        "https://afrique.le360.ma/feed",
        "https://www.africanews.com/feed/",
        "https://www.voaafrique.com/api/zv-etr_iytpqo",
    ],
    "🌐 Monde": [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.rfi.fr/fr/rss/monde.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.france24.com/fr/rss",
        "https://www.reuters.com/tools/rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],
    "💻 Tech & Dev": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
        "https://www.wired.com/feed/rss",
        "https://github.blog/feed/",
        "https://stackoverflow.blog/feed/",
        "https://www.presse-citron.net/feed/",
        "https://korben.info/feed",
        "https://www.journaldugeek.com/feed/",
    ],
    "🤖 IA & Modèles": [
        "https://openai.com/blog/rss/",
        "https://www.anthropic.com/rss",
        "https://blog.google/technology/ai/rss/",
        "https://huggingface.co/blog/feed.xml",
        "https://mistral.ai/news/feed/",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    ],
    "⚽ Foot International": [
        "https://www.bbc.com/sport/football/rss.xml",
        "https://www.theguardian.com/football/world-cup-2026/rss",
        "https://www.goal.com/feeds/fr/news",
        "https://www.lequipe.fr/rss/actu_rss_Football.xml",
        "https://www.cafonline.com/news/feed/",
        "https://www.bbc.com/sport/africa/rss.xml",
    ],
    "🏆 Ligues Européennes": [
        "https://www.uefa.com/rss/",
        "https://www.theguardian.com/football/championsleague/rss",
        "https://www.premierleague.com/news/rss",
        "https://www.theguardian.com/football/premierleague/rss",
        "https://www.marca.com/rss/futbol/primera-division.xml",
        "https://www.bundesliga.com/api/rss/news",
        "https://www.kicker.de/news/fussball/bundesliga/rss",
        "https://www.gazzetta.it/rss/home.xml",
    ],
    "🦁 Foot Camerounais": [
        "https://www.camfoot.com/feed/",
        "https://www.rfi.fr/fr/rss/afrique-foot.xml",
        "https://actucameroun.com/category/sport/feed/",
        "https://www.jeuneafrique.com/sport/football/feed/",
    ],
}


# ─────────────────────────────────────────────
# TIMESTAMP
# ─────────────────────────────────────────────
def get_last_run_time() -> datetime:
    try:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE) as f:
                data = json.load(f)
                ts = datetime.fromisoformat(data["last_run"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                print(f"📅 Dernière exécution : {ts.astimezone(TZ_WAT).strftime('%d/%m/%Y %H:%M WAT')}")
                return ts
    except Exception:
        pass
    default = datetime.now(timezone.utc) - timedelta(hours=12)
    print("📅 Première exécution — 12 dernières heures")
    return default


def save_last_run_time():
    try:
        with open(LAST_RUN_FILE, "w") as f:
            json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)
    except Exception as e:
        print(f"⚠️  Impossible de sauvegarder le timestamp : {e}")


# ─────────────────────────────────────────────
# CONTEXTE MATINAL / SOIR
# ─────────────────────────────────────────────
def get_digest_context() -> dict:
    now_wat = datetime.now(TZ_WAT)
    hour = now_wat.hour
    print(f"🕐 Heure WAT : {now_wat.strftime('%H:%M')}")
    if 4 <= hour < 14:
        return {
            "emoji": "🌅",
            "label": "matinal",
            "intro": "Bonne matinée ! Voici l'essentiel de l'actu pour bien démarrer ta journée.",
            "now_str": now_wat.strftime("%A %d %B %Y — %H:%M WAT"),
        }
    else:
        return {
            "emoji": "🌙",
            "label": "du soir",
            "intro": "Bonne soirée ! Voici ce qu'il s'est passé aujourd'hui dans le monde.",
            "now_str": now_wat.strftime("%A %d %B %Y — %H:%M WAT"),
        }


# ─────────────────────────────────────────────
# SCRAPING RSS
# ─────────────────────────────────────────────
def fetch_articles(sources: dict, since: datetime) -> dict:
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    results = {}
    for category, urls in sources.items():
        articles = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass
                    if published and published <= since:
                        continue
                    raw = entry.get("summary", entry.get("description", ""))
                    clean = re.sub(r"<[^>]+>", "", raw).strip()
                    articles.append({
                        "title": entry.get("title", "Sans titre").strip(),
                        "summary": clean[:400],
                        "link": entry.get("link", "").strip(),
                        "source": feed.feed.get("title", "").strip(),
                        "published": published.astimezone(TZ_WAT).strftime("%H:%M") if published else "—",
                    })
            except Exception as e:
                print(f"⚠️  {url}: {e}")

        seen = set()
        unique = []
        for a in articles:
            key = a["title"].lower()[:70]
            if key not in seen:
                seen.add(key)
                unique.append(a)
        results[category] = unique
        print(f"  {category}: {len(unique)} articles")
    return results


# ─────────────────────────────────────────────
# GEMINI — 1 SEULE REQUÊTE, BUDGET DYNAMIQUE
# ─────────────────────────────────────────────
def build_prompt(content: str) -> str:
    """Prompt commun pour Gemini et Groq."""
    return f"""Tu es un assistant d'actualite expert. Analyse ces articles et retourne UNIQUEMENT un JSON valide, sans aucun texte avant ou apres.

Pour la section "IA et Modeles" : mets en avant les modeles gratuits, nouvelles offres, mises a jour et innovations IA.

ARTICLES :
{content}

FORMAT JSON ATTENDU :
{{
  "sections": [
    {{
      "categorie": "Cameroun",
      "items": [
        {{
          "tag": "Justice",
          "texte": "1-2 phrases avec contexte et faits cles.",
          "lien": "https://url-directe-article.com/page"
        }}
      ]
    }}
  ]
}}

REGLES ABSOLUES :
1. Inclure TOUTES les categories disponibles dans cet ordre : Cameroun, Afrique, Monde, Tech et Dev, IA et Modeles, Foot International, Ligues Europeennes, Foot Camerounais
2. Inclure LE MAXIMUM d'items par categorie (tous les articles si possible)
3. "lien" = URL COMPLETE et DIRECTE de l'article (jamais une homepage)
4. "tag" = mot-cle court (Politique, Mercato, IA, Mondial, Justice, Transfert...)
5. JSON pur uniquement - zero markdown, zero explication, zero texte hors JSON"""


def parse_json_response(raw: str) -> dict:
    """Nettoie et parse la reponse JSON d'un LLM."""
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    data = json.loads(raw)
    total_items = sum(len(s.get("items", [])) for s in data.get("sections", []))
    print(f"  OK {len(data.get('sections', []))} sections, {total_items} items generes")
    return data


def try_gemini(prompt: str) -> dict:
    """Gemini 2.5 Flash-Lite (gratuit, 1500 req/jour)."""
    print("  Tentative Gemini 2.5 Flash-Lite...")
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash-lite")
    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 8000, "temperature": 0.1}
    )
    return parse_json_response(response.text)


def try_gemma(prompt: str) -> dict:
    """Fallback Gemma 4 E4B (open-source Google, meme cle API que Gemini)."""
    print("  Fallback Gemma 4 E4B (open-source)...")
    # Gemma 4 est accessible via la meme API Google AI Studio
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemma-4-e4b-it")
    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 8000, "temperature": 0.1}
    )
    return parse_json_response(response.text)


def summarize_with_ai(articles_by_category: dict, ctx: dict) -> dict:
    """
    Principal : Gemini 2.5 Flash-Lite (1500 req/jour gratuit).
    Fallback automatique : Groq Llama 3.3 70B (14400 req/jour gratuit).
    Budget tokens calcule dynamiquement selon nombre d'articles.
    """
    total = sum(len(arts) for arts in articles_by_category.values() if arts)
    BUDGET_CONTENT = 55_000
    chars_per_article = max(60, min(300, BUDGET_CONTENT // max(total, 1)))
    print(f"  {total} articles — {chars_per_article} chars/article alloues")

    content = ""
    for category, articles in articles_by_category.items():
        if not articles:
            continue
        content += f"\n=== {category} ===\n"
        for a in articles:
            line = f"- {a['title']}"
            if a["link"]:
                line += f" [{a['link']}]"
            if a["summary"]:
                line += f" | {a['summary'][:chars_per_article]}"
            content += line + "\n"

    print(f"  Contenu : {len(content)} caracteres")
    prompt = build_prompt(content)

    # 1. Essai Gemini
    try:
        return try_gemini(prompt)
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
            print("  Gemini quota depasse, bascule sur Gemma 4......")
        else:
            print(f"  Gemini erreur ({err[:80]}), bascule sur Gemma 4......")

    # 2. Fallback Groq
    if not os.environ.get("GEMINI_API_KEY"):
        print("  GEMINI_API_KEY non defini")
        return {"sections": []}
    try:
        return try_gemma(prompt)
    except Exception as e:
        print(f"  Gemma erreur : {e}")
        return {"sections": []}




# ─────────────────────────────────────────────
# FORMATAGE HTML (Python, pas Gemini)
# ─────────────────────────────────────────────
def format_html(data: dict, ctx: dict) -> str:
    lines = []
    lines.append(f"{ctx['emoji']} <b>Digest {ctx['label']} — {ctx['now_str']}</b>")
    lines.append(f"<i>{ctx['intro']}</i>")
    lines.append("")

    for section in data.get("sections", []):
        cat = section.get("categorie", "")
        items = section.get("items", [])
        if not items:
            continue

        lines.append(f"<b>{cat}</b>")
        for item in items:
            tag = item.get("tag", "").strip()
            texte = item.get("texte", "").strip()
            lien = item.get("lien", "").strip()

            # Nettoyer tout HTML résiduel dans le texte
            texte = re.sub(r"<[^>]+>", "", texte)
            texte = texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            tag = re.sub(r"<[^>]+>", "", tag)
            tag = tag.replace("&", "&amp;")

            if lien and lien.startswith("http"):
                bullet = f'&#8226; <b>{tag}</b> : {texte} <a href="{lien}">Lire</a>'
            else:
                bullet = f"&#8226; <b>{tag}</b> : {texte}"

            lines.append(bullet)

        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# ENVOI TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > 3800:
            if current.strip():
                chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())

    print(f"📨 Envoi en {len(chunks)} message(s)...")
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(api_url, json=payload, timeout=15)
        if resp.ok:
            print(f"  ✅ Message {i+1}/{len(chunks)} OK")
        else:
            print(f"  ❌ Erreur {i+1}: {resp.text}")
            payload["parse_mode"] = ""
            resp2 = requests.post(api_url, json=payload, timeout=15)
            if not resp2.ok:
                return False
    return True


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    ctx = get_digest_context()
    print(f"\n🚀 Digest {ctx['label']} — {ctx['now_str']}")

    required_env = ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Variables manquantes : {', '.join(missing)}")

    last_run = get_last_run_time()

    print(f"\n📡 Scraping RSS depuis {last_run.astimezone(TZ_WAT).strftime('%d/%m %H:%M WAT')}...")
    articles = fetch_articles(RSS_SOURCES, since=last_run)
    total = sum(len(v) for v in articles.values())
    print(f"✅ {total} nouveaux articles")

    if total == 0:
        msg = (
            f"{ctx['emoji']} <b>Digest {ctx['label']} — {ctx['now_str']}</b>\n\n"
            f"<i>Aucun nouvel article depuis la dernière consultation.</i>"
        )
        send_telegram(msg, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
        save_last_run_time()
        return

    print(f"\n🤖 Génération du digest (1 requête Gemini)...")
    data = summarize_with_ai(articles, ctx)

    if not data.get("sections"):
        print("❌ Aucune section générée")
        raise RuntimeError("Gemini returned empty JSON")

    print("\n🎨 Formatage HTML...")
    digest_html = format_html(data, ctx)
    print(f"✅ {len(digest_html)} caractères")

    print("\n📨 Envoi Telegram...")
    success = send_telegram(digest_html, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])

    if success:
        save_last_run_time()
        print(f"\n🎉 Digest {ctx['label']} envoyé avec succès !")
    else:
        raise RuntimeError("Telegram send failed")


if __name__ == "__main__":
    main()
