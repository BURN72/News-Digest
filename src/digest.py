"""
News Digest Bot — 6h & 21h WAT
- Heure forcée en Africa/Douala (WAT = UTC+1)
- Articles depuis la dernière exécution (fichier timestamp)
- Format HTML Telegram (liens fiables)
- Maximum d'articles par catégorie
"""

import os
import re
import json
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# FUSEAU HORAIRE — WAT (Africa/Douala = UTC+1)
# ─────────────────────────────────────────────
TZ_WAT = ZoneInfo("Africa/Douala")

# Fichier de suivi de la dernière exécution
LAST_RUN_FILE = "/tmp/last_run_timestamp.json"

# ─────────────────────────────────────────────
# SOURCES RSS — 51 SOURCES
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
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://feeds.feedburner.com/blogspot/gJZg",
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
# GESTION DU TIMESTAMP DE DERNIÈRE EXÉCUTION
# ─────────────────────────────────────────────
def get_last_run_time() -> datetime:
    """Retourne l'heure de la dernière exécution. Par défaut : 12h en arrière."""
    try:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE) as f:
                data = json.load(f)
                ts = datetime.fromisoformat(data["last_run"])
                print(f"📅 Dernière exécution : {ts.strftime('%d/%m/%Y %H:%M WAT')}")
                return ts
    except Exception:
        pass
    # Première exécution ou fichier absent → 12h en arrière
    default = datetime.now(timezone.utc) - timedelta(hours=12)
    print(f"📅 Première exécution — récupération des 12 dernières heures")
    return default


def save_last_run_time():
    """Sauvegarde l'heure courante comme dernière exécution."""
    try:
        with open(LAST_RUN_FILE, "w") as f:
            json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)
    except Exception as e:
        print(f"⚠️  Impossible de sauvegarder le timestamp : {e}")


# ─────────────────────────────────────────────
# DÉTECTION MATINAL / SOIR (heure WAT réelle)
# ─────────────────────────────────────────────
def get_digest_context() -> dict:
    now_wat = datetime.now(TZ_WAT)
    hour = now_wat.hour
    print(f"🕐 Heure WAT actuelle : {now_wat.strftime('%H:%M')} (UTC+1)")

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
# SCRAPING RSS — ARTICLES DEPUIS DERNIÈRE EXEC
# ─────────────────────────────────────────────
def fetch_articles(sources: dict, since: datetime) -> dict:
    """Récupère tous les articles publiés depuis `since`."""
    # Assurer que since est timezone-aware
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    results = {}
    for category, urls in sources.items():
        articles = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:30]:  # jusqu'à 30 par source
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass

                    # Inclure si publié après la dernière exécution
                    # Si pas de date, on inclut quand même (mieux trop que trop peu)
                    if published and published <= since:
                        continue

                    # Nettoyage du résumé
                    raw_summary = entry.get("summary", entry.get("description", ""))
                    clean_summary = re.sub(r"<[^>]+>", "", raw_summary)[:500]

                    articles.append({
                        "title": entry.get("title", "Sans titre").strip(),
                        "summary": clean_summary.strip(),
                        "link": entry.get("link", ""),
                        "source": feed.feed.get("title", url),
                        "published": published.astimezone(TZ_WAT).strftime("%H:%M WAT") if published else "—",
                    })
            except Exception as e:
                print(f"⚠️  Erreur sur {url}: {e}")

        # Dédoublonner
        seen = set()
        unique = []
        for a in articles:
            key = a["title"].lower()[:70]
            if key not in seen:
                seen.add(key)
                unique.append(a)

        results[category] = unique
        count = len(unique)
        print(f"  {category}: {count} nouveaux articles")

    return results


# ─────────────────────────────────────────────
# RÉSUMÉ GEMINI — FORMAT HTML TELEGRAM STRICT
# ─────────────────────────────────────────────
def summarize_with_gemini(articles_by_category: dict, ctx: dict) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-3.5-flash")

    # Construire le contenu brut
    content = ""
    total = 0
    for category, articles in articles_by_category.items():
        if not articles:
            continue
        content += f"\n\n=== {category} ({len(articles)} articles) ===\n"
        for a in articles:
            total += 1
            content += f"TITRE: {a['title']}\n"
            content += f"SOURCE: {a['source']}\n"
            content += f"LIEN: {a['link']}\n"
            content += f"HEURE: {a['published']}\n"
            if a["summary"]:
                content += f"RESUME: {a['summary'][:300]}\n"
            content += "---\n"

    print(f"📝 Total articles transmis à Gemini : {total}")

    prompt = f"""Tu es un assistant d'actualité expert pour un étudiant camerounais passionné d'informatique et de football.

Voici TOUS les nouveaux articles depuis la dernière consultation :

{content}

MISSION : Génère un digest {ctx['label']} complet, riche et bien formaté en HTML Telegram.

═══ RÈGLES DE FORMAT HTML TELEGRAM STRICTES ═══
✅ Balises autorisées UNIQUEMENT :
   - <b>texte</b> → gras
   - <i>texte</i> → italique  
   - <a href="URL_COMPLETE">texte</a> → lien cliquable
   - &#8226; → bullet point (•)
   - Sauts de ligne normaux

❌ INTERDIT ABSOLUMENT :
   - Astérisques * ou ** (Markdown)
   - Crochets [texte](url) (Markdown)
   - Underscores _ pour italique
   - Tout autre Markdown

═══ STRUCTURE DU DIGEST ═══

{ctx['emoji']} <b>Digest {ctx['label']} — {ctx['now_str']}</b>
<i>{ctx['intro']}</i>

Pour CHAQUE catégorie qui a des articles :

[EMOJI] <b>[Nom catégorie]</b>
&#8226; <b>[Tag thématique]</b> : [2 lignes de contexte et faits clés]. <a href="URL_DIRECTE_ARTICLE">Lire</a>
&#8226; ...
(inclure LE MAXIMUM d'articles disponibles pour cette catégorie)

═══ SECTIONS OBLIGATOIRES (si articles disponibles) ═══
🇨🇲 <b>Cameroun</b>
🌍 <b>Afrique</b>
🌐 <b>Monde</b>
💻 <b>Tech &amp; Dev</b>
🤖 <b>IA &amp; Modèles</b> — mentionne les modèles gratuits, nouvelles offres, mises à jour
⚽ <b>Foot International</b> — Mondial 2026, CAN, compétitions africaines
🏆 <b>Ligues Européennes</b> — PL, Liga, Bundesliga, Serie A, UCL
🦁 <b>Foot Camerounais</b> — Lions Indomptables, championnat local

═══ RÈGLES CONTENU ═══
- Inclure TOUS les articles disponibles, pas seulement 3 ou 5
- Chaque bullet = 1-2 phrases avec contexte + lien direct de l'article
- Les URLs dans href doivent être les URLs COMPLÈTES des articles (pas des homepages)
- Si l'URL contient des caractères spéciaux, les garder tels quels
- Ton dynamique, informatif, avec contexte pour chaque info"""

    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 8000}
    )
    return response.text


# ─────────────────────────────────────────────
# ENVOI TELEGRAM — MODE HTML
# ─────────────────────────────────────────────
def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Découper proprement entre lignes (jamais en plein milieu d'une balise)
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
            print(f"  ✅ Message {i+1}/{len(chunks)} envoyé")
        else:
            print(f"  ❌ Erreur message {i+1}: {resp.text}")
            # Retry sans formatage si HTML pose problème
            payload["parse_mode"] = ""
            resp2 = requests.post(api_url, json=payload, timeout=15)
            if not resp2.ok:
                print(f"  ❌ Retry échoué : {resp2.text}")
                return False
            print(f"  ✅ Message {i+1} envoyé sans formatage")

    return True


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    ctx = get_digest_context()
    print(f"\n🚀 Démarrage du digest {ctx['label']} — {ctx['now_str']}")

    # Vérification des variables d'environnement
    required_env = ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Variables manquantes : {', '.join(missing)}")

    # Récupérer le timestamp de la dernière exécution
    last_run = get_last_run_time()

    # Scraping
    print(f"\n📡 Récupération des articles depuis {last_run.strftime('%d/%m %H:%M UTC')}...")
    articles = fetch_articles(RSS_SOURCES, since=last_run)
    total = sum(len(v) for v in articles.values())
    print(f"\n✅ {total} nouveaux articles récupérés au total")

    if total == 0:
        fallback = (
            f"{ctx['emoji']} <b>Digest {ctx['label']} — {ctx['now_str']}</b>\n\n"
            f"<i>Aucun nouvel article depuis la dernière consultation. Tout est à jour !</i>"
        )
        send_telegram(fallback, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
        save_last_run_time()
        return

    # Résumé Gemini
    print("\n🤖 Génération du résumé avec Gemini 3.5 Flash...")
    digest = summarize_with_gemini(articles, ctx)
    print("✅ Résumé généré")

    # Envoi Telegram
    print("\n📨 Envoi sur Telegram...")
    success = send_telegram(digest, os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])

    if success:
        save_last_run_time()
        print(f"\n🎉 Digest {ctx['label']} envoyé avec succès !")
    else:
        print("\n❌ Échec de l'envoi Telegram")
        raise RuntimeError("Telegram send failed")


if __name__ == "__main__":
    main()
