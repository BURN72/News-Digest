"""
News Digest Bot — 6h & 21h
Scrape les flux RSS → résumé via Gemini 3.5 Flash (gratuit) → envoi Telegram
"""

import os
import re
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
# SOURCES RSS
# ─────────────────────────────────────────────
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
        "https://stability.ai/news/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://feeds.feedburner.com/blogspot/gJZg",  # Google Research
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

TZ_CAMEROON = timezone(timedelta(hours=1))
MAX_ARTICLES_PER_CATEGORY = 15  # On en prend plus pour que Gemini ait du choix
HOURS_LOOKBACK = 24


# ─────────────────────────────────────────────
# DÉTECTION MATINAL / SOIR
# ─────────────────────────────────────────────
def get_digest_context() -> dict:
    hour = datetime.now(TZ_CAMEROON).hour
    if 4 <= hour < 14:
        return {
            "emoji": "🌅",
            "label": "matinal",
            "intro": "Bonne matinée ! Voici l'essentiel de l'actu pour bien démarrer ta journée.",
        }
    else:
        return {
            "emoji": "🌙",
            "label": "du soir",
            "intro": "Bonne soirée ! Voici ce qu'il s'est passé aujourd'hui dans le monde.",
        }


# ─────────────────────────────────────────────
# SCRAPING RSS
# ─────────────────────────────────────────────
def fetch_articles(sources: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    results = {}

    for category, urls in sources.items():
        articles = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:20]:
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    if published and published < cutoff:
                        continue

                    # Récupérer le lien direct de l'article
                    link = entry.get("link", "")

                    articles.append({
                        "title": entry.get("title", "Sans titre"),
                        "summary": entry.get("summary", entry.get("description", ""))[:400],
                        "link": link,  # lien direct article
                        "source": feed.feed.get("title", url),
                        "published": published.strftime("%H:%M") if published else "??:??",
                    })
            except Exception as e:
                print(f"⚠️  Erreur sur {url}: {e}")

        # Dédoublonner par titre
        seen = set()
        unique = []
        for a in articles:
            key = a["title"].lower()[:60]
            if key not in seen:
                seen.add(key)
                unique.append(a)

        results[category] = unique[:MAX_ARTICLES_PER_CATEGORY]
        print(f"  {category}: {len(results[category])} articles récupérés")

    return results


# ─────────────────────────────────────────────
# RÉSUMÉ VIA GEMINI 3.5 FLASH
# ─────────────────────────────────────────────
def summarize_with_gemini(articles_by_category: dict) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-3.5-flash")

    ctx = get_digest_context()
    now_cm = datetime.now(TZ_CAMEROON).strftime("%A %d %B %Y — %H:%M")

    content = ""
    for category, articles in articles_by_category.items():
        if not articles:
            continue
        content += f"\n\n## {category}\n"
        for a in articles:
            content += f"- TITRE: {a['title']}\n"
            content += f"  SOURCE: {a['source']}\n"
            content += f"  LIEN: {a['link']}\n"
            content += f"  HEURE: {a['published']}\n"
            if a["summary"]:
                clean = re.sub(r"<[^>]+>", "", a["summary"])
                content += f"  RESUME: {clean[:300]}\n"

    prompt = f"""Tu es un assistant d'actualité expert pour un étudiant camerounais passionné d'informatique et de football.

Voici les articles des dernières 24h :

{content}

Génère un digest {ctx['label']} en français, riche et bien structuré.

RÈGLES STRICTES :
1. Exactement *10 bullets* par catégorie (si moins d'articles disponibles, utilise-en le maximum)
2. Chaque bullet = 2 lignes : une ligne de contexte + les faits essentiels
3. Chaque bullet se termine par le lien DIRECT de l'article (pas la homepage) entre parenthèses
4. Format Markdown Telegram uniquement : *gras*, _italique_, [texte](url) — PAS de ##
5. Les liens doivent être les URL complètes des articles individuels

FORMAT EXACT À SUIVRE :

{ctx['emoji']} *Digest {ctx['label']} du {now_cm}*
_{ctx['intro']}_

*🇨🇲 Cameroun*
• _Politique_ : [description 2 lignes avec contexte] ([Lire](url_article))
• ...

*🌍 Afrique*
• ...

*🌐 Monde*
• ...

*💻 Tech & Dev*
• ...

*🤖 IA & Modèles* ← Section dédiée aux modèles IA gratuits, nouvelles offres, mises à jour, innovations
• _Nouveau modèle_ : [description] ([Lire](url))
• _Offre gratuite_ : [description] ([Lire](url))
• ...

*⚽ Foot International* (Mondial 2026 + CAN + compétitions africaines)
• ...

*🏆 Ligues Européennes* (PL, Liga, Bundesliga, Serie A, UCL)
• ...

*🦁 Foot Camerounais*
• ...

Ton : informatif, dynamique, avec une touche de contexte pour chaque info. 
Priorité absolue aux liens directs des articles individuels."""

    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 4000}
    )
    return response.text


# ─────────────────────────────────────────────
# ENVOI TELEGRAM (multi-messages si trop long)
# ─────────────────────────────────────────────
def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Découper proprement par section pour ne pas couper en plein milieu
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 4000:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,  # évite les previews qui alourdissent
        }
        resp = requests.post(url, json=payload, timeout=15)
        if not resp.ok:
            print(f"❌ Erreur Telegram (chunk {i+1}): {resp.text}")
            # Retry sans Markdown
            payload["parse_mode"] = ""
            resp = requests.post(url, json=payload, timeout=15)
            if not resp.ok:
                return False
        print(f"  📨 Chunk {i+1}/{len(chunks)} envoyé")

    return True


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    ctx = get_digest_context()
    print(f"🚀 Démarrage du digest {ctx['label']}...")

    required_env = ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Variables manquantes : {', '.join(missing)}")

    print("\n📡 Récupération des articles RSS...")
    articles = fetch_articles(RSS_SOURCES)
    total = sum(len(v) for v in articles.values())
    print(f"✅ {total} articles récupérés au total")

    if total == 0:
        fallback = f"{ctx['emoji']} *Digest {ctx['label']}*\n\n_Aucun article récent trouvé. Vérifiez les flux RSS._"
        send_telegram(fallback, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
        return

    print("\n🤖 Génération du résumé avec Gemini 3.5 Flash...")
    digest = summarize_with_gemini(articles)
    print("✅ Résumé généré")

    print("\n📨 Envoi sur Telegram...")
    success = send_telegram(digest, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])

    if success:
        print(f"✅ Digest {ctx['label']} envoyé avec succès !")
    else:
        print("❌ Échec de l'envoi Telegram")
        raise RuntimeError("Telegram send failed")


if __name__ == "__main__":
    main()
