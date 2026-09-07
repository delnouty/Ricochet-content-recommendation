"""Génère les figures de la présentation de soutenance.

Pourquoi un script et non deux images dessinées à la main : les chiffres de la
présentation doivent avoir une source. Les valeurs ci-dessous sont celles
mesurées sur la **période de test** par `src/experiments.py` ; les modifier ici
et regénérer met les diapositives à jour, sans retouche graphique.

    python scripts/figures_presentation.py

Écrit `docs/figures/fraicheur.pdf` et `docs/figures/compromis.pdf` (PDF
vectoriel : le texte reste net à la projection, contrairement à un PNG).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Palette identique à celle du Beamer (docs/presentation.tex), pour que les
# figures ne ressemblent pas à des pièces rapportées.
PRIMARY = "#1F3A5F"
ACCENT = "#2E86C1"
ACCENT2 = "#E67E22"
VERT = "#27AE60"
GRIS = "#7F8C8D"

SORTIE = Path("docs/figures")

# --- Effet de la fenêtre de comptage, à algorithme constant -----------------
# Une seule variable change : la durée sur laquelle on compte les clics.
FENETRES = [
    ("1 heure", 0.2190, 791),
    ("6 heures", 0.1480, 2657),
    ("24 heures", 0.1060, 6777),
    ("tout l'historique\n(240 h)", 0.0075, 29118),
]

# --- Les cinq configurations, dans leur meilleur réglage ---------------------
# Lues dans le fichier de référence, et non recopiées : c'est ce même fichier qui
# sert de garde-fou à la CI. Une divergence entre la diapositive et la référence
# devient ainsi impossible — la diapositive du 7 septembre affichait « ALS 72 h »
# quand la mesure portait sur 24 h, parce que les deux vivaient séparément.
REFERENCE = Path("models/baseline_metrics.json")

# Nom dans le fichier de référence -> (libellé de la figure, retenu en production)
ETIQUETTES = {
    "popularité 1 h": ("Popularité 1 h", False),
    "mixte 4 popularité + 1 contenu": ("Mixte\n4 pop. + 1 contenu", True),
    "contenu (vivier 6 h)": ("Contenu\nvivier 6 h", False),
    "SVD (Surprise)": ("SVD Surprise", False),
}


def charger_configs() -> list[tuple[str, float, float, bool]]:
    """(libellé, HitRate@5, couverture %, retenu) pour chaque stratégie mesurée."""
    import json

    donnees = json.loads(REFERENCE.read_text(encoding="utf-8"))
    configs = []
    for nom, metriques in donnees["toutes_strategies"].items():
        if nom in ETIQUETTES:
            libelle, retenu = ETIQUETTES[nom]
        elif nom.startswith("ALS"):
            # Le libellé porte la fenêtre et les facteurs réellement mesurés :
            # « ALS (24 h, 16 facteurs) » -> « ALS\n24 h, 16 facteurs ».
            libelle, retenu = "ALS\n" + nom[nom.find("(") + 1:-1], False
        else:
            continue
        configs.append((libelle, metriques["HitRate@5"],
                        metriques["couverture %"], retenu))
    return configs


def _habiller(ax) -> None:
    """Retire ce qui n'informe pas : cadre, graduations superflues."""
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    ax.spines["left"].set_color(GRIS)
    ax.spines["bottom"].set_color(GRIS)
    ax.tick_params(colors=PRIMARY, labelsize=10.5)


def _virgule(ax, axe: str = "x") -> None:
    """Sépare les décimales par une virgule.

    Un axe en « 0.05 » à côté d'étiquettes en « 0,2190 » donne une figure qui
    n'a pas l'air relue — et la présentation est en français.
    """
    from matplotlib.ticker import FuncFormatter

    formateur = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
    (ax.xaxis if axe == "x" else ax.yaxis).set_major_formatter(formateur)


def figure_fraicheur(chemin: Path) -> None:
    """La fraîcheur pèse plus que le modèle : facteur 250 sur la précision."""
    fig, ax = plt.subplots(figsize=(8.2, 2.7))

    etiquettes = [f[0] for f in FENETRES]
    valeurs = [f[1] for f in FENETRES]
    candidats = [f[2] for f in FENETRES]
    positions = range(len(FENETRES))

    # La première barre est celle retenue : elle seule porte la couleur d'accent.
    couleurs = [ACCENT2] + [ACCENT] * (len(FENETRES) - 1)
    ax.barh(list(positions), valeurs, color=couleurs, height=0.6)

    # Colonne des candidats calée à droite de la barre la plus longue, sinon
    # l'étiquette de valeur de la première barre lui passe dessus.
    for y, (valeur, nb) in enumerate(zip(valeurs, candidats)):
        ax.text(valeur + 0.006, y, f"{valeur:.4f}".replace(".", ","),
                va="center", fontsize=11.5, color=PRIMARY, fontweight="bold")
        ax.text(0.335, y, f"{nb:,} candidats".replace(",", " "),
                va="center", ha="right", fontsize=10, color=GRIS)

    ax.set_yticks(list(positions), etiquettes, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.34)
    ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
    ax.set_xlabel("HitRate@5", fontsize=10.5, color=PRIMARY)
    ax.set_title("Même algorithme, seule la fenêtre de comptage change",
                 fontsize=12, color=PRIMARY, fontweight="bold", loc="left")
    _habiller(ax)
    _virgule(ax, "x")

    # La flèche dit ce que les barres montrent, sans commentaire à l'oral.
    ax.annotate("facteur 250", xy=(0.010, 3), xytext=(0.105, 2.62),
                fontsize=12, color=ACCENT2, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=ACCENT2, lw=1.4,
                                connectionstyle="arc3,rad=0.25"))

    fig.tight_layout()
    fig.savefig(chemin, transparent=True)
    plt.close(fig)


def figure_compromis(chemin: Path) -> None:
    """Précision contre couverture : pourquoi le mixte est retenu."""
    fig, ax = plt.subplots(figsize=(8.2, 3.0))

    configs = charger_configs()
    for libelle, hitrate, couverture, retenu in configs:
        ax.scatter(hitrate, couverture,
                   s=210 if retenu else 110,
                   color=ACCENT2 if retenu else ACCENT,
                   edgecolor=PRIMARY if retenu else "none",
                   linewidth=1.6, zorder=3)

    # Placement à la main : cinq points seulement, et l'automatique les
    # chevauche. L'ancrage évite que les libellés de droite sortent du cadre.
    # Clé = premier mot du libellé, pour que « ALS 24 h » reste reconnu si la
    # fenêtre retenue change.
    decalages = {
        "Popularité": (-10, 2, "right"),
        "Mixte": (-10, 6, "right"),
        "ALS": (12, -2, "left"),
        "Contenu": (12, -2, "left"),
        "SVD": (12, -8, "left"),
    }
    for libelle, hitrate, couverture, retenu in configs:
        dx, dy, ancre = decalages[libelle.split()[0].split("\n")[0]]
        ax.annotate(libelle, xy=(hitrate, couverture),
                    xytext=(dx, dy), textcoords="offset points", ha=ancre,
                    fontsize=10.5, color=ACCENT2 if retenu else PRIMARY,
                    fontweight="bold" if retenu else "normal")

    # La flèche entre popularité et mixte est l'argument du choix. Ses extrémités
    # viennent des mesures, pour qu'elle ne pointe pas à côté après une mise à
    # jour de la référence.
    par_debut = {l.split()[0].split("\n")[0]: (h, c) for l, h, c, _ in configs}
    pop_x, pop_y = par_debut["Popularité"]
    mix_x, mix_y = par_debut["Mixte"]
    ax.annotate("", xy=(mix_x, mix_y * 0.86), xytext=(pop_x, pop_y * 1.12),
                arrowprops=dict(arrowstyle="-|>", color=VERT, lw=1.6,
                                connectionstyle="arc3,rad=-0.35"), zorder=2)
    ax.text(0.316, 0.011, "couverture\n× 38 pour\n0,001 de\nprécision",
            fontsize=10.5, color=VERT, fontweight="bold", ha="right", va="center")

    ax.set_yscale("log")
    ax.set_xlim(-0.005, 0.32)
    ax.set_ylim(0.0020, 0.75)
    ax.set_yticks([0.003, 0.01, 0.03, 0.1, 0.3])
    ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
    ax.set_xlabel("HitRate@5  (précision)", fontsize=10.5, color=PRIMARY)
    ax.set_ylabel("Couverture du catalogue %\n(échelle log)",
                  fontsize=10.5, color=PRIMARY)
    ax.set_title("En haut à droite = précis et varié ; le mixte s'en approche seul",
                 fontsize=12, color=PRIMARY, fontweight="bold", loc="left")
    ax.grid(axis="both", color=GRIS, alpha=0.18, linewidth=0.6)
    _habiller(ax)
    _virgule(ax, "x")
    _virgule(ax, "y")

    fig.tight_layout()
    fig.savefig(chemin, transparent=True)
    plt.close(fig)


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    figure_fraicheur(SORTIE / "fraicheur.pdf")
    figure_compromis(SORTIE / "compromis.pdf")
    for f in sorted(SORTIE.glob("*.pdf")):
        print(f"{f} — {f.stat().st_size / 1024:.0f} Ko")


if __name__ == "__main__":
    main()
