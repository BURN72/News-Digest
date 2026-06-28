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
# SOURCES RSS — SÉLECTION COMPLÈTE & QUALIFIÉE
# ─────────────────────────────────────────────
RSS_SOURCES = {

    # ── CAMEROUN ─────────────────────────────
    "🇨🇲 Cameroun": [
        "https://www.cameroon-tribune.cm/rss.xml",          # Journal officiel
        "https://actucameroun.com/feed/",                   # Actu Cameroun (très actif)
        "https://www.crtv.cm/feed/",                        # Radio-TV nationale
        "https://www.jeuneafrique.com/pays/cameroun/feed/", # JA focus Cameroun
        "https://www.lemonde.fr/cameroun/rss_full.xml",     # Le Monde / Cameroun
        "https://www.rfi.fr/fr/afrique/rss",                # RFI Afrique (inclut CM)
    ],

    # ── AFRIQUE ──────────────────────────────
    "🌍 Afrique": [
        "https://www.jeuneafrique.com/feed/",               # Référence presse africaine
        "https://www.bbc.com/afrique/index.xml",            # BBC Afrique FR
        "https://www.rfi.fr/fr/rss/afrique.xml",            # RFI Afrique
        "https://afrique.le360.ma/feed",                    # Le360 Afrique
        "https://www.africanews.com/feed/",                 # Africanews EN
        "https://www.voaafrique.com/api/zv-etr_iytpqo",    # VOA Afrique FR
    ],

    # ── MONDE ────────────────────────────────
    "🌐 Monde": [
        "https://www.lemonde.fr/rss/une.xml",               # Le Monde — Une
        "https://www.rfi.fr/fr/rss/monde.xml",              # RFI Monde
        "https://feeds.bbci.co.uk/news/world/rss.xml",      # BBC World EN
        "https://www.france24.com/fr/rss",                  # France 24 FR
        "https://www.reuters.com/tools/rss",                # Reuters monde
        "https://www.aljazeera.com/xml/rss/all.xml",        # Al Jazeera EN
    ],

    # ── TECH & IA ────────────────────────────
    "💻 Tech / IA": [
        # Veille généraliste EN
        "https://techcrunch.com/feed/",                     # TechCrunch
        "https://www.theverge.com/rss/index.xml",           # The Verge
        "https://arstechnica.com/feed/",                    # Ars Technica
        "https://www.wired.com/feed/rss",                   # Wired
        # IA spécialisé
        "https://openai.com/blog/rss/",                     # OpenAI Blog
        "https://www.anthropic.com/rss",                    # Anthropic
        "https://blog.google/technology/ai/rss/",           # Google AI
        # Dev & Open Source
        "https://github.blog/feed/",                        # GitHub Blog
        "https://stackoverflow.blog/feed/",                 # Stack Overflow
        # FR
        "https://www.presse-citron.net/feed/",              # Presse-Citron FR
        "https://korben.info/feed",                         # Korben (hacking/dev FR)
        "https://www.journaldugeek.com/feed/",              # Journal du Geek FR
    ],

    # ── FOOTBALL — COMPÉTITIONS INTERNATIONALES ──
    "⚽ Coupe du Monde & CAN": [
        "https://www.bbc.com/sport/football/rss.xml",               # BBC Sport
        "https://www.theguardian.com/football/world-cup-2026/rss",  # Guardian WC2026
        "https://www.goal.com/feeds/fr/news",                       # Goal.com FR
        "https://www.lequipe.fr/rss/actu_rss_Football.xml",         # L'Équipe
        "https://www.cafonline.com/news/feed/",                     # CAF (CAN officiel)
        "https://www.bbc.com/sport/africa/rss.xml",                 # BBC Sport Afrique
    ],

    # ── FOOTBALL — LIGUES EUROPÉENNES ────────
    "🏆 Ligues Européennes": [
        # UEFA / Champions League
        "https://www.uefa.com/rss/",                                # UEFA officiel
        "https://www.theguardian.com/football/championsleague/rss", # Guardian UCL
        # Premier League
        "https://www.premierleague.com/news/rss",                   # PL officiel
        "https://www.theguardian.com/football/premierleague/rss",   # Guardian PL
        # La Liga
        "https://www.marca.com/rss/futbol/primera-division.xml",    # Marca (ESP)
        "https://www.sport.es/es/rss/",                             # Sport.es (ESP)
        # Bundesliga
        "https://www.bundesliga.com/api/rss/news",                  # Bundesliga officiel
        "https://www.kicker.de/news/fussball/bundesliga/rss",       # Kicker (GER)
        # Serie A
        "https://www.goal.com/feeds/it/news",                       # Goal.com IT
        "https://www.gazzetta.it/rss/home.xml",                     # Gazzetta dello Sport
    ],

    # ── FOOTBALL — CHAMPIONNAT CAMEROUNAIS ───
    "🦁 Football Camerounais": [
        "https://www.camfoot.com/feed/",                    # Camfoot — référence
        "https://www.rfi.fr/fr/rss/afrique-foot.xml",       # RFI Afrique Foot
        "https://actucameroun.com/category/sport/feed/",    # Actu CM Sport
        "https://www.jeuneafrique.com/sport/football/feed/",# JA Football Afrique
    ],
}

# Fuseau horaire Cameroun (UTC+1)
TZ_CAMEROON = timezone(timedelta(hours=1))
MAX_ARTICLES_PER_CATEGORY = 5
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
                for entry in feed.entries[:10]:
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    if published and published < cutoff:
                        continue

                    articles.append({
                        "title": entry.get("title", "Sans titre"),
                        "summary": entry.get("summary", entry.get("description", ""))[:300],
                        "link": entry.get("link", ""),
                        "source": feed.feed.get("title", url),
                        "published": published.strftime("%H:%M") if published else "??:??",
                    })
            except Exception as e:
                print(f"⚠️  Erreur sur {url}: {e}")

        # Dédoublonner par titre et limiter
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
            content += f"- [{a['source']}] {a['title']} ({a['published']})\n"
            if a["summary"]:
                clean = re.sub(r"<[^>]+>", "", a["summary"])
                content += f"  → {clean[:200]}\n"

    prompt = f"""Tu es un assistant d'actualité pour un étudiant camerounais en informatique.
Voici les titres des dernières 24h récupérés depuis des flux RSS :

{content}

Génère un digest {ctx['label']} en français, structuré, concis et engageant.

Format attendu (Markdown Telegram — *gras*, _italique_, pas de ##) :

{ctx['emoji']} *Digest {ctx['label']} du {now_cm}*
_{ctx['intro']}_

Pour chaque catégorie qui a des articles :
- Titre de section en gras (ex: *🇨🇲 Cameroun*)
- 3 à 5 bullets avec l'essentiel en 1-2 lignes max
- Lien cliquable à la fin de chaque bullet si possible

Regroupe les sections foot ainsi :
- *⚽ Foot International* (Mondial + CAN + grandes compétitions)
- *🏆 Ligues Européennes* (PL, Liga, Bundesliga, Serie A, UCL)
- *🦁 Foot Camerounais* (championnat local + Lions Indomptables)

Termine toujours par *💻 Veille Tech & IA* avec les 3-5 infos les plus importantes pour un dev.
Ton dynamique et informatif. Maximum 45 lignes au total."""

    response = model.generate_content(prompt)
    return response.text


# ─────────────────────────────────────────────
# ENVOI TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        resp = requests.post(url, json=payload, timeout=15)
        if not resp.ok:
            print(f"❌ Erreur Telegram (chunk {i+1}): {resp.text}")
            payload["parse_mode"] = ""
            resp = requests.post(url, json=payload, timeout=15)
            if not resp.ok:
                return False
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
