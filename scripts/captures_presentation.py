"""Capture les copies d'écran de l'application pour la présentation.

Pourquoi automatiser des captures d'écran : la partie 2 de la soutenance dure
6 minutes et porte sur les fonctionnalités de l'application. Des captures faites
à la main deviennent périmées dès que l'interface change, et personne ne se
souvient de la manipulation exacte qui les avait produites. Ici, la séquence est
du code : elle se rejoue.

Prérequis (une fois) :

    pip install playwright && playwright install chromium

Utilisation :

    python scripts/captures_presentation.py

Le script démarre lui-même l'application locale sur un port libre, la pilote,
écrit les images dans `docs/figures/` puis arrête le serveur.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "docs" / "figures"

# Assez large pour que la barre latérale et le contenu tiennent côte à côte, et
# doublé à l'export : une capture nette reste lisible en projection.
#
# La hauteur est celle de la fenêtre, pas celle de la page : Streamlit défile
# dans un conteneur interne, donc `full_page` ne rallonge pas la capture. Une
# fenêtre trop courte coupe la cinquième recommandation — mesuré.
LARGEUR, HAUTEUR, ECHELLE = 1180, 1650, 2

ATTENTE_COURTE = 1.2   # après un clic simple
ATTENTE_CALCUL = 4.0   # après « Recommander » : le classement traverse le catalogue


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def demarrer_app(port: int) -> subprocess.Popen:
    """Lance l'application locale autonome, sans ouvrir de navigateur."""
    commande = [
        sys.executable, "-m", "streamlit", "run", "local/app.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        # Sans cela, Streamlit affiche un bandeau « deploy » et le menu
        # hamburger, qui n'ont rien à faire sur une diapositive.
        "--client.toolbarMode", "minimal",
    ]
    return subprocess.Popen(commande, cwd=RACINE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def attendre_port(port: int, delai: float = 90) -> None:
    """Attend que le serveur accepte les connexions, sinon lève."""
    fin = time.time() + delai
    while time.time() < fin:
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(1)
    raise TimeoutError(f"L'application n'a pas démarré sur le port {port}.")


def rogner_bas(chemin: Path, marge: int = 40) -> None:
    """Coupe le vide sous le contenu.

    La fenêtre est volontairement haute pour ne rien tronquer, ce qui laisse une
    grande zone vide sur les pages courtes. Sur une diapositive, ce vide écrase
    la capture : à largeur fixe, chaque pixel de blanc en bas est un pixel de
    texte en moins. On cherche donc la dernière ligne contenant de l'encre.
    """
    from PIL import Image

    with Image.open(chemin) as img:
        gris = img.convert("L")
        largeur, hauteur = gris.size
        pixels = gris.load()
        # Balayage du bas vers le haut, par pas de 4 lignes : suffisant pour du
        # texte, et 4 fois moins de lectures.
        derniere = hauteur
        for y in range(hauteur - 1, -1, -4):
            if any(pixels[x, y] < 128 for x in range(0, largeur, 3)):
                derniere = y
                break
        bas = min(hauteur, derniere + marge)
        if bas < hauteur:
            img.crop((0, 0, largeur, bas)).save(chemin)


def capturer(page, nom: str, hauteur_max: int | None = None) -> None:
    """Capture la page entière, éventuellement tronquée à `hauteur_max` (px CSS)."""
    chemin = SORTIE / f"{nom}.png"
    if hauteur_max:
        page.screenshot(path=str(chemin), clip={"x": 0, "y": 0,
                                                "width": LARGEUR,
                                                "height": hauteur_max})
    else:
        page.screenshot(path=str(chemin), full_page=True)
        rogner_bas(chemin)
    print(f"  {chemin.relative_to(RACINE)} — {chemin.stat().st_size / 1024:.0f} Ko")


def capturer_bloc(page, nom: str, ancre: str, hauteur: int = 440,
                  marge_haut: int = 12, largeur: int = 575) -> None:
    """Capture la seule zone qui commence au texte `ancre`.

    Sur une diapositive, une capture pleine page réduit la liste de
    recommandations à quelques millimètres. Pour comparer deux listes côte à
    côte, il faut les listes seules : on part donc du titre des résultats et on
    descend de `hauteur` pixels.
    """
    boite = page.get_by_text(ancre).first.bounding_box()
    if boite is None:
        raise RuntimeError(f"Ancre « {ancre} » introuvable.")
    chemin = SORTIE / f"{nom}.png"
    # Par défaut 575 px et non toute la colonne : cela écarte la pile de boutons
    # « Lu », qui n'apporte rien sur une diapositive, et chaque pixel économisé
    # en largeur agrandit d'autant le texte à largeur de colonne fixe. Les blocs
    # sans cette pile prennent une largeur plus grande, sinon on couperait des
    # phrases en deux.
    page.screenshot(path=str(chemin), clip={
        "x": boite["x"] - 8,
        "y": boite["y"] - marge_haut,
        "width": min(LARGEUR - boite["x"] + 8, largeur),
        "height": hauteur,
    })
    rogner_bas(chemin, marge=14)
    print(f"  {chemin.relative_to(RACINE)} — {chemin.stat().st_size / 1024:.0f} Ko")


def sequence(page) -> None:
    """Les quatre gestes qui racontent l'application."""
    # 1. Le produit : cinq articles pour un lecteur du jeu de données.
    page.get_by_role("button", name="Recommander").click()
    page.wait_for_timeout(int(ATTENTE_CALCUL * 1000))
    capturer(page, "app_recommandations")
    capturer_bloc(page, "app_liste_fraiche", "article(s) recommandé(s)")

    # 2. Le même lecteur, fraîcheur désactivée : la démonstration de l'effet
    #    mesuré en partie 1, visible en direct.
    #
    #    On clique le libellé, pas la case : Streamlit masque l'`input` sous son
    #    propre habillage, et `uncheck()` sur le rôle « checkbox » se fait
    #    intercepter par le sélecteur qui le précède.
    page.get_by_text("Limiter aux articles récents").click()
    page.wait_for_timeout(int(ATTENTE_COURTE * 1000))
    page.get_by_role("button", name="Recommander").click()
    page.wait_for_timeout(int(ATTENTE_CALCUL * 1000))
    capturer(page, "app_sans_fraicheur")
    capturer_bloc(page, "app_liste_sans_fraicheur", "article(s) recommandé(s)")

    # 3. Le catalogue : ce qui permet au lecteur de cliquer autre chose que les
    #    suggestions, sans quoi son profil ne ferait que se renforcer.
    #    Tronqué : vingt lignes sur une diapositive ne se lisent pas, les
    #    commandes de tri et de filtre sont ce qui compte.
    page.get_by_role("tab", name="Parcourir les articles").click()
    page.wait_for_timeout(int(ATTENTE_CALCUL * 1000))
    capturer(page, "app_catalogue", hauteur_max=1000)
    # Hauteur choisie pour que le bloc ait à peu près les proportions de celui de
    # l'inscription : sur une diapositive à deux colonnes, deux images de formats
    # très différents se retrouvent à des tailles très différentes.
    capturer_bloc(page, "app_bloc_catalogue", "Trier par", hauteur=390)

    # 4. L'inscription : le cas « nouvel utilisateur » du cahier des charges.
    page.get_by_role("tab", name="Nouveau client").click()
    page.wait_for_timeout(int(ATTENTE_COURTE * 1000))
    capturer(page, "app_inscription")
    capturer_bloc(page, "app_bloc_inscription", "Inscrire un nouveau client",
                  hauteur=560, largeur=690)


def main() -> int:
    if shutil.which("streamlit") is None and not (RACINE / "local" / "app.py").exists():
        print("Application introuvable.", file=sys.stderr)
        return 1

    SORTIE.mkdir(parents=True, exist_ok=True)
    port = port_libre()
    serveur = demarrer_app(port)
    try:
        attendre_port(port)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            navigateur = p.chromium.launch()
            contexte = navigateur.new_context(
                viewport={"width": LARGEUR, "height": HAUTEUR},
                device_scale_factor=ECHELLE)
            page = contexte.new_page()
            page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
            # Le premier rendu charge 265 Mo d'artefacts : laisser le temps.
            page.get_by_role("button", name="Recommander").wait_for(timeout=180_000)
            sequence(page)
            navigateur.close()
    finally:
        serveur.terminate()
        try:
            serveur.wait(timeout=15)
        except subprocess.TimeoutExpired:
            serveur.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
