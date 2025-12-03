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
                _chauffe_eau_end = (start_heater + duration_heater) % 24 \
                    if start_heater + duration_heater > 24 else start_heater + duration_heater
                _chauffe_eau_active = True
                break
    # Si chauffe en cours
    if _chauffe_eau_active:
        # Cas normal (pas de chevauchement minuit)
        if (_chauffe_eau_start <= h < _chauffe_eau_end if _chauffe_eau_start < _chauffe_eau_end
                else (h >= _chauffe_eau_start or h < _chauffe_eau_end)):
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
    logging.info("Conso power %sW, energie:%sWh diff index:%sWh", p, e, e)
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

    # on rajoute s'assure que la puissance est au dessus d'un minimum aléatoire
    puissance += max(random.uniform(0.012, 0.048), puissance)

    return float(puissance * 1000)


_last_water_call = None
_total_water_volume = 0.0


def get_water_meter_m3():
    """
    À chaque appel, retourne le débit instantané (m³/s, max 4L/min)
    et le volume total écoulé (m³).
    """
    global _last_water_call, _total_water_volume
    now = datetime.now().timestamp()
    # Débit simulé (aléatoire, max 4 L/min)
    debit_l_min = random.uniform(0, 2) * random.randint(0, 1)
    debit_m3_s = debit_l_min / 1000 / 60  # conversion L/min -> m³/s
    # Calcul du volume écoulé depuis le dernier appel
    delta_s = 0
    if _last_water_call is not None:
        delta_s = (now - _last_water_call)
        volume_m3 = debit_m3_s * delta_s  # conversion L -> m³
        _total_water_volume += volume_m3
    _last_water_call = now
    logging.info("Débit: %s m3/s, Volume: %s m3 en %ss", debit_m3_s, _total_water_volume, delta_s)
    return round(debit_m3_s, 6), round(_total_water_volume, 6)
