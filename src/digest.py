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
def build_prompt_for_batch(content: str, categories: list) -> str:
    """Prompt pour un batch d'articles (sous-ensemble de catégories)."""
    cats_str = ", ".join(categories)
    return f"""Tu es un assistant d\'actualite expert. Analyse ces articles et retourne UNIQUEMENT un JSON valide.

ARTICLES DU BATCH :
{content}

FORMAT JSON (rien d\'autre — zero markdown, zero texte avant/apres) :
{{
  "sections": [
    {{
      "categorie": "NOM_CATEGORIE",
      "items": [
        {{
          "tag": "MotCle",
          "texte": "1-2 phrases contexte + faits cles.",
          "lien": "https://url-complete-article.com/page"
        }}
      ]
    }}
  ]
}}

REGLES :
1. Traiter UNIQUEMENT les categories presentes dans ce batch : {cats_str}
2. Inclure TOUS les articles de chaque categorie dans les items
3. "lien" = URL COMPLETE de l\'article (jamais une homepage)
4. "tag" = mot-cle court (Politique, Mercato, IA, Mondial, Justice...)
5. JSON pur uniquement"""


def parse_json_response(raw: str) -> dict:
    """Nettoie et parse la reponse JSON d'un LLM."""
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    data = json.loads(raw)
    total_items = sum(len(s.get("items", [])) for s in data.get("sections", []))
    print(f"    -> {len(data.get('sections', []))} sections, {total_items} items")
    return data


def call_model(prompt: str, model_name: str) -> dict:
    """Appelle un modèle Google AI (Gemini ou Gemma) avec la même clé."""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 8000, "temperature": 0.1}
    )
    return parse_json_response(response.text)


def call_with_fallback(prompt: str) -> dict:
    """
    Essai 1 : Gemini 2.5 Flash-Lite (1500 req/jour gratuit)
    Fallback  : Gemma 4 E4B open-source (même clé API Google)
    """
    for model_name, label in [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
        ("gemma-4-e4b-it",        "Gemma 4 E4B (fallback)"),
    ]:
        try:
            print(f"    [{label}]...")
            return call_model(prompt, model_name)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                print(f"    Quota depasse sur {label}, essai suivant...")
            else:
                print(f"    Erreur {label}: {err[:100]}, essai suivant...")
    return {"sections": []}


def merge_sections(results: list) -> dict:
    """
    Fusionne les sections de plusieurs batches.
    Si une catégorie apparaît dans plusieurs batches, on concatène les items.
    """
    merged = {}
    for result in results:
        for section in result.get("sections", []):
            cat = section.get("categorie", "")
            items = section.get("items", [])
            if cat not in merged:
                merged[cat] = []
            merged[cat].extend(items)

    # Reconstruire dans l'ordre défini
    ORDER = [
        "🇨🇲 Cameroun", "🌍 Afrique", "🌐 Monde", "💻 Tech & Dev",
        "🤖 IA & Modèles", "⚽ Foot International",
        "🏆 Ligues Européennes", "🦁 Foot Camerounais"
    ]
    sections = []
    for cat in ORDER:
        # Chercher la catégorie avec correspondance partielle (émojis)
        items = None
        for key in merged:
            if any(c in key for c in cat.split()) or cat in key or key in cat:
                items = merged[key]
                break
        if items:
            sections.append({"categorie": cat, "items": items})

    return {"sections": sections}


def summarize_with_ai(articles_by_category: dict, ctx: dict) -> dict:
    """
    Envoie TOUS les articles en plusieurs batches Gemini/Gemma.
    Chaque batch = MAX_ARTICLES_PER_BATCH articles → output JSON safe.
    Tous les résultats sont fusionnés avant envoi Telegram.

    Calcul dynamique :
    - Output JSON estimé : ~60 tokens par article
    - max_output_tokens = 8000 → max ~130 articles par batch
    - On prend MAX_ARTICLES_PER_BATCH = 40 pour rester safe
    """
    MAX_ARTICLES_PER_BATCH = 40   # articles par requête Gemini
    SUMMARY_LEN = 120             # chars de résumé par article

    # Aplatir tous les articles par catégorie
    total = sum(len(arts) for arts in articles_by_category.values() if arts)
    print(f"  {total} articles au total")

    # Calculer le nombre de batches nécessaires
    import math
    nb_batches = max(1, math.ceil(total / MAX_ARTICLES_PER_BATCH))
    print(f"  -> {nb_batches} batch(es) de {MAX_ARTICLES_PER_BATCH} articles max")

    # Distribuer les articles en batches en préservant les catégories
    # On remplit chaque batch catégorie par catégorie
    batches = []           # liste de dict {cat: [articles]}
    current_batch = {}
    current_count = 0

    for category, articles in articles_by_category.items():
        if not articles:
            continue
        # Répartir les articles de cette catégorie entre les batches
        idx = 0
        while idx < len(articles):
            if current_count >= MAX_ARTICLES_PER_BATCH:
                batches.append(current_batch)
                current_batch = {}
                current_count = 0
            # Combien peut-on mettre dans le batch courant ?
            space = MAX_ARTICLES_PER_BATCH - current_count
            chunk = articles[idx:idx + space]
            if chunk:
                if category not in current_batch:
                    current_batch[category] = []
                current_batch[category].extend(chunk)
                current_count += len(chunk)
            idx += space

    if current_batch:
        batches.append(current_batch)

    print(f"  Distribution : {[sum(len(v) for v in b.values()) for b in batches]} articles/batch")

    # Traiter chaque batch
    all_results = []
    for i, batch in enumerate(batches):
        cats_in_batch = list(batch.keys())
        n_arts = sum(len(v) for v in batch.values())
        print(f"\n  Batch {i+1}/{len(batches)} — {n_arts} articles ({', '.join(c.split()[0] for c in cats_in_batch)})")

        # Construire le contenu du batch
        content = ""
        for cat, arts in batch.items():
            content += f"\n=== {cat} ===\n"
            for a in arts:
                line = f"- {a['title']}"
                if a["link"]:
                    line += f" [{a['link']}]"
                if a["summary"]:
                    line += f" | {a['summary'][:SUMMARY_LEN]}"
                content += line + "\n"

        prompt = build_prompt_for_batch(content, cats_in_batch)
        result = call_with_fallback(prompt)
        all_results.append(result)

        # Pause entre batches pour respecter le RPM (15 req/min)
        if i < len(batches) - 1:
            print(f"    Pause 5s entre batches...")
            time.sleep(5)

    # Fusionner tous les résultats
    print(f"\n  Fusion de {len(all_results)} batch(es)...")
    merged = merge_sections(all_results)
    total_items = sum(len(s.get("items", [])) for s in merged.get("sections", []))
    print(f"  Total final : {len(merged.get('sections', []))} sections, {total_items} items")
    return merged




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
