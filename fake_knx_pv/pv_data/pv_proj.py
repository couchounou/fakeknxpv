from datetime import datetime, timedelta
import numpy as np

# Profil mensuel de croissance (%)
profil_mensuel = [1.7, 2.6, 5.2, 8.6, 12.0, 13.7, 16.3, 15.9, 11.6, 7.7, 3.0, 1.7]
croissance_annuelle = sum(profil_mensuel)

print(f"Croissance annuelle totale: {croissance_annuelle}%")
print(f"Profil mensuel: {profil_mensuel}")

# Calculer la progression cumulée sur 12 mois (en %)
progression_cumulee = []
total = 0
for p in profil_mensuel:
    total += p
    progression_cumulee.append(total)

print(f"\nProgression cumulée annuelle: {[round(p, 2) for p in progression_cumulee]}")

# ============= PARAMETRES A PERSONNALISER =============
date_depart = datetime(2024, 1, 1)  # Date où la valeur est 0
date_actuelle = datetime(2025, 1, 1)  # Date actuelle
valeur_actuelle = 8  # Valeur X actuelle
valeur_cible = 200  # Valeur Z cible

# ======================================================

def calculer_date_cible(date_depart, date_actuelle, valeur_actuelle, 
                        valeur_cible, profil_mensuel):
    """
    Calcule la date à laquelle la grandeur atteindra la valeur cible.
    """
    # Calculer le temps écoulé en mois
    mois_ecoules = (date_actuelle.year - date_depart.year) * 12 + \
                   (date_actuelle.month - date_depart.month)

    # Calculer la progression actuelle (0 à 100% = un cycle complet)
    progression_actuelle = (valeur_actuelle / valeur_cible) * 100

    # Position dans le cycle (0 à 100)
    position_cycle = progression_actuelle % 100

    # Nombre de cycles complets déjà parcourus
    cycles_parcourus = progression_actuelle // 100

    # Trouver le mois du cycle où nous sommes actuellement
    mois_dans_cycle = None
    mois_actuel = (date_actuelle.month - 1) % 12

    # Calculer le taux de croissance cumulé depuis le départ
    jours_ecoules = (date_actuelle - date_depart).days
    taux_cumule = (valeur_actuelle / jours_ecoules) if jours_ecoules > 0 else 0

    # Nombre de cycles complets à parcourir
    cycles_manquants = (valeur_cible - valeur_actuelle) / (valeur_cible)

    # Estimation simple : si croissance linéaire
    if valeur_actuelle > 0 and jours_ecoules > 0:
        jours_par_unite = jours_ecoules / valeur_actuelle
        jours_manquants = (valeur_cible - valeur_actuelle) * jours_par_unite
        date_cible = date_actuelle + timedelta(days=jours_manquants)
    else:
        date_cible = None

    return date_cible, mois_ecoules, progression_actuelle

# Calculer
date_cible, mois_ecoules, progression = calculer_date_cible(
    date_depart, date_actuelle, valeur_actuelle, valeur_cible, profil_mensuel
)

print(f"\n{'='*60}")
print(f"RESULTATS DE LA PROJECTION")
print(f"{'='*60}")
print(f"Date de départ (valeur = 0):    {date_depart.strftime('%d/%m/%Y')}")
print(f"Date actuelle:                  {date_actuelle.strftime('%d/%m/%Y')}")
print(f"Valeur actuelle X:              {valeur_actuelle}")
print(f"Valeur cible Z:                 {valeur_cible}")
print(f"\nMois écoulés depuis le départ:  {mois_ecoules} mois")
print(f"Progression actuelle:           {progression:.1f}% vers la cible")

if date_cible:
    print(f"\n✓ La valeur {valeur_cible} sera atteinte le: {date_cible.strftime('%d/%m/%Y')}")
    jours_manquants = (date_cible - date_actuelle).days
    print(f"  (dans {jours_manquants} jours, soit ~{jours_manquants//30} mois)")
else:
    print("\n✗ Impossible de calculer la date cible")

print(f"{'='*60}")