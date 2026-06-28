# 🌅 Morning News Digest Bot

Bot Telegram qui t'envoie chaque matin à **6h (heure Cameroun)** un digest personnalisé des actualités :
Cameroun · Afrique · Monde · Tech/IA · Football

Hébergé gratuitement sur **GitHub Actions**.

---

## 🏗️ Architecture

```
GitHub Actions (cron 5h UTC)
       ↓
src/digest.py
  ├── feedparser  →  scrape les flux RSS (24 sources)
  ├── Claude API  →  résumé intelligent structuré
  └── Telegram Bot API  →  envoi sur ton téléphone
```

---

## 🚀 Guide de configuration (15 minutes)

### Étape 1 — Créer le bot Telegram

1. Ouvre Telegram et cherche **@BotFather**
2. Envoie `/newbot`
3. Donne un nom au bot (ex: `MonDigestBot`)
4. BotFather te donne un **token** → note-le (ex: `123456:ABC-DEF...`)

### Étape 2 — Récupérer ton Chat ID

1. Cherche **@userinfobot** sur Telegram
2. Démarre le bot → il t'affiche ton **Chat ID** (nombre entier, ex: `987654321`)

### Étape 3 — Récupérer ta clé Gemini API (gratuit)

1. Va sur [aistudio.google.com](https://aistudio.google.com)
2. Clique **"Get API key"** dans le menu de gauche
3. **Create API key** → copie la clé générée
4. Pas de carte bancaire requise 🎉

> 💡 Gemini 3.5 Flash est **100% gratuit** avec 1 500 requêtes/jour en free tier — pour 1 digest par jour, c'est largement suffisant.

### Étape 4 — Fork et configurer le repo GitHub

1. **Fork** ce repo sur ton compte GitHub
2. Va dans **Settings → Secrets and variables → Actions**
3. Clique **New repository secret** et ajoute ces 3 secrets :

| Nom du secret | Valeur |
|---|---|
| `GEMINI_API_KEY` | Ta clé Google AI Studio |
| `TELEGRAM_BOT_TOKEN` | Token de @BotFather |
| `TELEGRAM_CHAT_ID` | Ton Chat ID numérique |

### Étape 5 — Activer GitHub Actions

1. Va dans l'onglet **Actions** de ton repo
2. Clique **"I understand my workflows, enable them"**
3. Pour tester immédiatement : **Actions → Morning News Digest → Run workflow**

---

## ⚙️ Personnalisation

### Modifier les sources RSS

Édite `src/digest.py`, section `RSS_SOURCES` :

```python
RSS_SOURCES = {
    "🇨🇲 Cameroun": [
        "https://ton-site.cm/feed/",   # Ajoute tes sources
    ],
    # Ajoute une nouvelle catégorie :
    "💰 Économie": [
        "https://www.lesechos.fr/rss/rss_une.xml",
    ],
}
```

### Changer l'heure d'envoi

Dans `.github/workflows/morning-digest.yml` :

```yaml
# Format : minute heure * * *  (heure en UTC)
# Cameroun = UTC+1, donc 6h Cameroun = 5h UTC
- cron: "0 5 * * *"   # 6h Cameroun
- cron: "0 4 * * *"   # 5h Cameroun
- cron: "30 5 * * *"  # 6h30 Cameroun
```

### Ajouter un groupe Telegram

Pour envoyer dans un groupe :
1. Ajoute ton bot au groupe
2. Remplace `TELEGRAM_CHAT_ID` par l'ID du groupe (commence par `-`)

---

## 🧪 Test local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Définir les variables d'environnement
export GEMINI_API_KEY="AIzaSy..."
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"

# Lancer
python src/digest.py
```

---

## 📋 Logs GitHub Actions

Pour voir les logs d'exécution :
**Actions → Morning News Digest → [dernière exécution]**

---

## 🛠️ Dépannage

| Problème | Solution |
|---|---|
| Bot Telegram ne répond pas | Envoie `/start` au bot avant le premier run |
| Erreur `ANTHROPIC_API_KEY` | Vérifie les secrets GitHub |
| Flux RSS vides | Certains sites bloquent les scrapers — remplace l'URL |
| `Markdown` parsing error | Le digest est renvoyé sans formatage automatiquement |

---

## 📦 Structure du projet

```
news-digest/
├── .github/
│   └── workflows/
│       └── morning-digest.yml   ← Scheduler GitHub Actions
├── src/
│   └── digest.py                ← Script principal
├── requirements.txt
└── README.md
```
