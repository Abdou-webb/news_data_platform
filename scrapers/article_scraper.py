import uuid
import sys
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup

# =============================================================================
# Sources RSS choisies pour le scraping.
# Au départ j'avais essayé de scraper directement les pages HTML, mais les
# sites modernes utilisent beaucoup de JS pour charger leur contenu, donc
# BeautifulSoup seul ne suffisait pas. Les flux RSS sont bien plus stables
# pour ce type de pipeline batch.
# =============================================================================
RSS_SOURCES = [
    {
        "name": "BBC Technology",
        "rss_url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    },
    {
        "name": "Hacker News",
        "rss_url": "https://news.ycombinator.com/rss",
    },
    {
        "name": "TechCrunch",
        "rss_url": "https://techcrunch.com/feed/",
    },
]

# Namespaces XML utilisés par certains flux RSS (trouvé ça sur la doc RSS 2.0)
XML_NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
}

# Headers pour éviter d'être bloqué - on se fait passer pour un navigateur normal
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


class GenericNewsScraper:
    """
    Scraper d'articles de presse via flux RSS.

    Stratégie en deux temps :
    1. On récupère les métadonnées (titre, date, catégorie...) depuis le RSS
    2. On tente de scraper le texte complet depuis la page de l'article
       -> Si ça échoue (timeout, blocage), on garde la description RSS

    Le contenu retourné peut encore contenir du HTML résiduel.
    C'est voulu : le nettoyage sera fait dans la couche Silver.
    """

    def __init__(self, source_name, rss_url):
        self.source_name = source_name
        self.rss_url = rss_url
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    def _fetch_rss_items(self):
        """Télécharge le flux RSS et retourne la liste des éléments <item>."""
        try:
            response = self.session.get(self.rss_url, timeout=15)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            return root.findall(".//item")
        except ET.ParseError as e:
            print(f"  [ERREUR XML] Impossible de parser le RSS de {self.source_name} : {e}")
            return []
        except requests.RequestException as e:
            print(f"  [ERREUR HTTP] Impossible de joindre {self.rss_url} : {e}")
            return []

    def _get_full_article_text(self, url):
        """
        Essaie de récupérer le contenu complet de l'article depuis son URL.
        Retourne None si ça échoue (le script appelant utilisera la description RSS).

        TODO: Tester newspaper3k ou trafilatura pour une meilleure extraction du
        contenu principal (ces libs sont faites pour ça).
        """
        if not url:
            return None
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            # Essayer différents sélecteurs courants pour le bloc d'article
            # (chaque site structure son HTML différemment...)
            candidate_selectors = [
                "article",
                "[class*='article-body']",
                "[class*='post-content']",
                "[class*='entry-content']",
                "[class*='story-body']",
                "main",
            ]
            for selector in candidate_selectors:
                block = soup.select_one(selector)
                if block:
                    paragraphs = block.find_all("p")
                    text = " ".join(p.get_text(strip=True) for p in paragraphs)
                    if len(text) > 200:  # texte trop court = probablement pas le bon bloc
                        return text

            # Dernier recours : prendre les premiers <p> de toute la page
            all_p = soup.find_all("p")
            fallback = " ".join(p.get_text(strip=True) for p in all_p[:20])
            return fallback if fallback else None

        except Exception as e:
            print(f"    [WARN] Scraping page impossible pour {url} : {e}")
            return None

    def _parse_rss_item(self, item):
        """Transforme un élément <item> RSS en dictionnaire article standardisé."""

        def get_text(tag, ns_prefix=None):
            """Petit helper pour récupérer le texte d'un tag (avec ou sans namespace)."""
            if ns_prefix:
                ns_uri = XML_NAMESPACES.get(ns_prefix, "")
                el = item.find(f"{{{ns_uri}}}{tag}")
            else:
                el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        title = get_text("title")
        url = get_text("link")
        pub_date = get_text("pubDate")
        description = get_text("description")
        category = get_text("category")

        # L'auteur est dans des tags différents selon les sources
        author = (
            get_text("creator", ns_prefix="dc")
            or get_text("author")
            or self.source_name
        )

        # Tentative de récupération du contenu complet de l'article
        full_text = self._get_full_article_text(url)
        raw_content = full_text if full_text else description

        return {
            "id": str(uuid.uuid4()),
            "title": title or "Sans titre",
            "author": author,
            "date": pub_date or datetime.now().isoformat(),
            "category": category or "General",
            "content": raw_content,  # Nettoyage HTML fait dans la couche Silver
            "source": self.source_name,
            "url": url,
        }

    def scrape_latest_articles(self, limit=10):
        """Point d'entrée : scrape et retourne les N derniers articles de la source."""
        print(f"\n[Scraper] {self.source_name}")
        print(f"  RSS : {self.rss_url}")

        items = self._fetch_rss_items()
        if not items:
            print("  Aucun article récupéré.")
            return []

        articles = []
        for item in items[:limit]:
            try:
                article = self._parse_rss_item(item)
                articles.append(article)
                print(f"  [OK] {article['title'][:75]}")
            except Exception as e:
                print(f"  [SKIP] Erreur sur un article : {e}")

        return articles
