"""
News Digest Bot — 6h & 21h WAT
Stratégie : batch par catégorie → texte libre → envoi Telegram immédiat
Plus de JSON, plus de parsing, plus de troncature.
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
                        "summary": clean[:300],
                        "link": entry.get("link", "").strip(),
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
# GEMINI : TEXTE LIBRE PAR CATÉGORIE
# ─────────────────────────────────────────────
def summarize_category(category: str, articles: list, ctx: dict) -> str:
    """
    Génère un bloc HTML Telegram pour UNE catégorie.
    Retourne directement du texte HTML prêt à envoyer — pas de JSON.
    """
    extra = ""
    if "IA" in category or "Modèles" in category:
        extra = "\nMets en avant : modèles gratuits, nouvelles offres, mises à jour, innovations."

    # Construire la liste brute des articles
    content = ""
    for a in articles:
        content += f"- {a['title']} [{a['link']}]"
        if a["summary"]:
            content += f" | {a['summary'][:150]}"
        content += "\n"

    prompt = f"""Tu es un assistant d'actualité expert pour un étudiant camerounais passionné d'informatique et de football.{extra}

Voici les articles de la section "{category}" :
{content}

Génère UNIQUEMENT le bloc HTML Telegram pour cette section, sans aucun texte avant ou après.

FORMAT EXACT (HTML Telegram strict) :
<b>{category}</b>
&#8226; <b>TagCourt</b> : 1-2 phrases de contexte + faits clés. <a href="URL_COMPLETE_ARTICLE">Lire</a>
&#8226; <b>TagCourt</b> : 1-2 phrases de contexte + faits clés. <a href="URL_COMPLETE_ARTICLE">Lire</a>
...

RÈGLES :
- Inclure TOUS les articles de la liste
- Balises autorisées UNIQUEMENT : <b>, <i>, <a href="...">
- "URL_COMPLETE_ARTICLE" = URL directe de l'article (pas la homepage)
- TagCourt = mot-clé thématique (Politique, Mercato, IA, Justice, Transfert...)
- Aucun markdown (pas d'astérisques, pas de crochets [])
- Aucun texte hors du bloc HTML"""

    # Essai Gemini 2.5 Flash-Lite, fallback Gemma 4 E4B
    for model_name, label in [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
        ("gemma-4-e4b-it", "Gemma 4 E4B"),
    ]:
        try:
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"max_output_tokens": 4000, "temperature": 0.1}
            )
            text = response.text.strip()
            # Nettoyer backticks éventuels
            text = re.sub(r"^```html\s*", "", text)
            text = re.sub(r"^```\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            print(f"    ✅ {label} — {len(text)} chars générés")
            return text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                print(f"    ⚠️  {label} quota dépassé, essai suivant...")
            else:
                print(f"    ⚠️  {label} erreur: {err[:80]}, essai suivant...")

    # Si tout échoue, retourner un bloc minimal avec les titres
    print(f"    ❌ Tous les modèles ont échoué pour {category}, envoi des titres bruts")
    fallback = f"<b>{category}</b>\n"
    for a in articles:
        title = a["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if a["link"]:
            fallback += f'&#8226; {title} <a href="{a["link"]}">Lire</a>\n'
        else:
            fallback += f"&#8226; {title}\n"
    return fallback


# ─────────────────────────────────────────────
# ENVOI TELEGRAM
# ─────────────────────────────────────────────
def send_telegram_block(text: str, bot_token: str, chat_id: str) -> bool:
    """Envoie un bloc HTML sur Telegram. Découpe si > 3800 chars."""
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Découper proprement entre lignes
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

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(api_url, json=payload, timeout=15)
        if not resp.ok:
            print(f"    ❌ Telegram erreur: {resp.text[:100]}")
            # Retry sans HTML
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

    BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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
        send_telegram_block(msg, BOT_TOKEN, CHAT_ID)
        save_last_run_time()
        return

    # ── Envoyer l'en-tête immédiatement ──
    header = (
        f"{ctx['emoji']} <b>Digest {ctx['label']} — {ctx['now_str']}</b>\n"
        f"<i>{ctx['intro']}</i>\n"
        f"<i>📊 {total} articles • {len([c for c,a in articles.items() if a])} catégories</i>"
    )
    send_telegram_block(header, BOT_TOKEN, CHAT_ID)
    print("\n📨 En-tête envoyé, traitement par catégorie...\n")

    # ── Traiter et envoyer chaque catégorie au fur et à mesure ──
    categories_done = 0
    for category, arts in articles.items():
        if not arts:
            continue

        print(f"  🤖 [{categories_done+1}] {category} ({len(arts)} articles)...")

        block = summarize_category(category, arts, ctx)

        # Envoyer immédiatement sur Telegram
        ok = send_telegram_block(block, BOT_TOKEN, CHAT_ID)
        if ok:
            print(f"    📨 Envoyé sur Telegram")
        else:
            print(f"    ❌ Échec envoi Telegram pour {category}")

        categories_done += 1

        # Pause entre catégories pour respecter le RPM Gemini (15 req/min)
        if categories_done < len([c for c, a in articles.items() if a]):
            time.sleep(5)

    # ── Pied de page ──
    footer = f"✅ <i>Digest complet — {categories_done} sections envoyées.</i>"
    send_telegram_block(footer, BOT_TOKEN, CHAT_ID)

    save_last_run_time()
    print(f"\n🎉 Digest {ctx['label']} complet — {categories_done} sections envoyées !")


if __name__ == "__main__":
    main()
