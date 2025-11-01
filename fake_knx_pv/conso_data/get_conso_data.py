import os
from datetime import datetime
import math
import random
import logging


# Variables d'état pour le chauffe-eau
_chauffe_eau_active = False
_chauffe_eau_start = None
_chauffe_eau_end = None


def chauffe_eau_profile(heure):
    """
    Retourne la puissance du chauffe-eau (W) à une heure donnée.
    Chauffe-eau 2500W, démarre à 22h30  ou entre 12h et 15h
    pour une durée aléatoire entre 45min et 180min.
    Lors du premier appel dans la période de chauffe,
    choisit une durée aléatoire.
    Pendant cette durée, retourne 2500W +/- 150W. Sinon retourne 0.
    """
    global _chauffe_eau_active, _chauffe_eau_start, _chauffe_eau_end
    h = heure % 24
    chauffe_eau_puissance = 2500  # W
    start_periods = [22.5]  # 22h30
    # Ajout de la période de chauffe possible entre 12h et 15h
    if 12 <= h < 14:
        start_periods.append(12)
    # Si on n'est pas en chauffe, vérifier si on entre dans une période
    if not _chauffe_eau_active:
        for start_heater in start_periods:
            if h >= start_heater and h < start_heater + 3:
                # On démarre une nouvelle chauffe
                duration_heater = random.uniform(0.75, 3)  # heures (45min à 180min)
                _chauffe_eau_start = h
                _chauffe_eau_end = (start_heater + duration_heater) % 24 if start_heater + duration_heater > 24 else start_heater + duration_heater
                _chauffe_eau_active = True
                break
    # Si chauffe en cours
    if _chauffe_eau_active:
        # Cas normal (pas de chevauchement minuit)
        if _chauffe_eau_start <= h < _chauffe_eau_end if _chauffe_eau_start < _chauffe_eau_end else (h >= _chauffe_eau_start or h < _chauffe_eau_end):
            bruit = random.uniform(-150, 150)
            return chauffe_eau_puissance + bruit
        else:
            # Fin de chauffe
            _chauffe_eau_active = False
            _chauffe_eau_start = None
            _chauffe_eau_end = None
    return 0.0


def get_conso_data(power=6000, updated_timestamp=datetime.now().timestamp()):
    # integrate power over time delta
    delta = datetime.now().timestamp() - updated_timestamp
    p = round(profil_maison(datetime.now().hour, datetime.now().weekday(), pmax=power/1000), 2)
    e = p * delta / 3600
    logging.info(f"Conso power {p}W, energie:{e}Wh diff index:{e}Wh")
    return p, e


def profil_maison(heure, jour_semaine, pmax=6):
    """
    Retourne la puissance typique (kW) d'une maison
    selon l'heure et le jour de la semaine.
    jour_semaine : 0 = lundi, ..., 6 = dimanche
    """

    h = heure % 24

    # --- Base commune (2 pics de conso : matin + soir) ---
    matin = 0.8 * math.exp(-((h - 7) / 2) ** 2)
    midi = 0.4 * math.exp(-((h - 12) / 3) ** 2)
    soir = 1.2 * math.exp(-((h - 19) / 2.5) ** 2)
    base = matin + midi + soir

    # --- Ajustement selon le jour ---
    if jour_semaine < 5:  # Lundi à vendredi
        facteur = 1.0
        # Moins d'activité en journée (travail)
        if 9 <= h <= 16:
            facteur = 0.6
    else:  # Samedi ou dimanche
        # Plus d'activité toute la journée
        facteur = 1.1 if 8 <= h <= 22 else 0.7

    puissance = base * facteur

    # Ajout de la courbe chauffe-eau séparée
    puissance += chauffe_eau_profile(h) / 1000  # conversion W -> kW

    # Normalisation à PUISSANCE_MAX
    puissance = min(puissance, pmax)

    # Ajout de bruit réaliste
    bruit = random.uniform(-0.3, 0.3)
    puissance = max(0.0, min(pmax, puissance + bruit))

    return float(puissance * 1000)


if __name__ == "__main__":
    print(get_conso_data())
