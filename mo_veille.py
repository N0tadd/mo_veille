"""
Veille marchesonline.com — Notifications Discord
By N0tad
"""

import requests, json, os, sys, time, gc, schedule
from playwright.sync_api import sync_playwright

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KEYWORDS        = "cloison,doublage,isolation,plafond,menuiserie" # A personnaliser
BASE_URL        = "https://www.marchesonline.com"
PAGE_URL        = f"{BASE_URL}/appels-offres/en-cours"
POST_URL        = f"{BASE_URL}/form_post_to_session"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1497255915923963985/2EWwVqM0yfD8rH6CG5LhdzD536XBdZIKlsFFF52KZTY0XNV5eGsKCgXKAhAYFxb08fNf" # A personnaliser

DIR         = os.path.dirname(os.path.abspath(__file__))
FICHIER_VUS = os.path.join(DIR, "marchesonline_vus.json")
FICHIER_LOG = os.path.join(DIR, "marchesonline_veille.log")

POST_BODY = (
    "id_ref_type_avis=1"
    f"&mots_cle={KEYWORDS}"
    "&id_ref_type_recherche=1"
    "&id_ref_departement[]=36&id_ref_departement[]=57&id_ref_departement[]=38" # A personnaliser
    "&id_ref_departement[]=45&id_ref_departement[]=50&id_ref_departement[]=54" # A personnaliser
    "&id_ref_departement[]=73&id_ref_departement[]=86&id_ref_departement[]=80" # A personnaliser
    "&id_ref_departement[]=87&id_ref_region[]=52" # A personnaliser
    "&statut_avis[]=2&date_mise_en_ligne=TODAY&__posted=1" # A personnaliser
    "&data_post_session_name=recherche_avancee"
)

# ─── LOGS ─────────────────────────────────────────────────────────────────────

class Logger:
    def __init__(self, f):
        self.terminal = sys.stdout
        self.log = open(f, "a", encoding="utf-8")

    def write(self, m):
        self.terminal.write(m)
        self.log.write(m)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger(FICHIER_LOG)

# ─── STOCKAGE ─────────────────────────────────────────────────────────────────

def charger_vus() -> set:
    if not os.path.exists(FICHIER_VUS):
        return set()
    try:
        with open(FICHIER_VUS, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, ValueError):
        print("[WARN] marchesonline_vus.json corrompu, réinitialisation")
        return set()

def sauvegarder_vus(vus: set):
    with open(FICHIER_VUS, "w", encoding="utf-8") as f:
        json.dump(list(vus), f, indent=2)

# ─── DISCORD ──────────────────────────────────────────────────────────────────

def envoyer_discord(lien: str, titre: str):
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"embeds": [{
            "title":       f"📢 {titre[:200]}",
            "description": f"[Consulter l'avis]({lien})",
            "color":       0x9B59B6,
            "url":         lien,
            "footer":      {"text": "marchesonline.com — Veille SONISO"},
        }]}, timeout=10)
        r.raise_for_status()
        print(f"  [DISCORD] Envoyé : {lien}")
    except Exception as e:
        print(f"  [ERREUR] Discord : {e}")

# ─── SCRAPE ───────────────────────────────────────────────────────────────────

def scraper():
    try:
        print(f"\n[CHECK] {time.strftime('%Y-%m-%d %H:%M:%S')} — Scraping marchesonline.com...")

        # Requête + extraction via Playwright (contourne Cloudflare)
        tous = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 1) Charger la page pour obtenir les cookies Cloudflare
            page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=30000)

            # 2) POST via fetch() JS injecté dans le contexte du browser
            response = page.evaluate(f"""async () => {{
                const r = await fetch("{POST_URL}", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
                    body: "{POST_BODY}"
                }});
                return r.status;
            }}""")
            print(f"  [POST] status {response}")

            # 3) Charger la page de résultats
            page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=30000)

            for a in page.query_selector_all("a.jqUpdateLink"):
                href = a.get_attribute("href")
                if not href:
                    continue
                tous[BASE_URL + href] = a.inner_text().strip()

            page.close()
            context.close()
            browser.close()

        gc.collect()

        print(f"  {len(tous)} avis scrappés au total")

        vus      = charger_vus()
        nouveaux = {l: t for l, t in tous.items() if l not in vus}

        if not nouveaux:
            print("  Aucun nouvel avis.")
            return

        print(f"  {len(nouveaux)} nouvel(aux) avis trouvé(s) !")
        for lien, titre in sorted(nouveaux.items()):
            envoyer_discord(lien, titre)
            vus.add(lien)
            time.sleep(1)

        sauvegarder_vus(vus)

    except Exception as e:
        print(f"[ERREUR CRITIQUE] scraper() : {e}")
        import traceback; traceback.print_exc()
    finally:
        gc.collect()

# ─── LANCEMENT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"{'='*60}\nVeille marchesonline.com — toutes les 30 min\n"
          f"   Keywords : {KEYWORDS}\n"
          f"   Logs : {FICHIER_LOG}\n   JSON : {FICHIER_VUS}\n{'='*60}\n")
    scraper()
    schedule.every(30).minutes.do(scraper)
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"[ERREUR] Boucle principale : {e}")
        time.sleep(30)
