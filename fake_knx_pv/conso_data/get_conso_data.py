
import os
from datetime import datetime
import math
import random
import logging


def get_conso_data():
    index_file_path = "../index_conso.txt"
    # get last update timestamp
    if os.path.exists(index_file_path):
        updated_timestamp = os.path.getmtime(index_file_path)
    else:
        updated_timestamp = datetime.now().timestamp()
        with open(index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write("0.0")
    
    # integrate power over time delta
    delta = datetime.now().timestamp() - updated_timestamp
    p = round(profil_maison(datetime.now().hour, datetime.now().weekday()), 2)
    e = p * delta / 3600
    logging.info(f"power:{p}W, energie:{e}Wh")
    old_index = 0.
    index = 0.

    # read old index and update it
    with open(index_file_path, "r", encoding="UTF-8") as myfile:
        old_index = float(myfile.read())
        index = old_index + e
    with open(index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write(str(index))
    logging.info(f"Conso power {p}W, energie:{e}Wh New index:{index}Wh")
    return p, index


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

    # Normalisation à PUISSANCE_MAX
    puissance = min(puissance, pmax)

    # Ajout de bruit réaliste
    bruit = random.uniform(-0.3, 0.3)
    puissance = max(0.0, min(pmax, puissance + bruit))

    return float(puissance * 1000)


if __name__ == "__main__":
    print(get_conso_data())
