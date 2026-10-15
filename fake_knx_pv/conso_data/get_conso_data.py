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
    puissance_totale, puissance_ecs = profil_maison(datetime.now().hour, datetime.now().weekday(), pmax_w=power)
    e_totale = puissance_totale * delta / 3600
    e_ecs = puissance_ecs * delta / 3600
    logging.info(
        "puissance totale:%sW, energie totale:%sWh, puissance ECS:%sW, energie ECS:%sWh",
        puissance_totale,
        e_totale,
        puissance_ecs,
        e_ecs
    )
    return round(puissance_totale, 2), e_totale, round(puissance_ecs, 2), e_ecs


def profil_maison(heure, jour_semaine, pmax_w=6000):
    """
    Retourne la puissance typique (en Watts) d'une maison
    selon l'heure et le jour de la semaine.
    jour_semaine : 0 = lundi, ..., 6 = dimanche
    pmax_w : Puissance maximale souscrite / autorisée en Watts (défaut: 6000 W = 6 kVA)
    """
    h = heure % 24

    # 1. Base commune des pics de consommation (directement en Watts)
    matin = 800 * math.exp(-(((h - 7) / 2) ** 2))
    midi = 400 * math.exp(-(((h - 12) / 3) ** 2))
    soir = 1200 * math.exp(-(((h - 19) / 2.5) ** 2))
    base_w = matin + midi + soir

    # 2. Facteur selon le jour et l'heure
    if jour_semaine < 5:  # Semaine (Lundi - Vendredi)
        facteur = 0.6 if 9 <= h <= 16 else 1.0
    else:  # Week-end (Samedi - Dimanche)
        facteur = 1.1 if 8 <= h <= 22 else 0.7

    puissance_base_w = base_w * facteur

    # 3. Ajout de la courbe chauffe-eau (déjà en Watts)
    puissance_ecs_w = chauffe_eau_profile(h)
    puissance_w = puissance_base_w + puissance_ecs_w

    # 4. Ajout d'un bruit aléatoire (±300 W)
    bruit_w = random.uniform(-300, 300)
    puissance_w += bruit_w

    # 5. Borne la puissance entre un talon minimum aléatoire (12 W à 48 W) et pmax_w
    talon_min_w = random.uniform(12, 120)
    puissance_totale_w = max(talon_min_w, min(pmax_w, puissance_w))

    return float(puissance_totale_w), float(puissance_ecs_w)


_last_water_call = datetime.now().timestamp()
_total_water_volume = 0.0


def get_water_meter_m3():
    """
    À chaque appel, retourne le débit instantané (m³/s, max 4L/min)
    et le volume total écoulé (m³).
    """
    global _last_water_call, _total_water_volume
    now = datetime.now().timestamp()
    # Débit simulé (aléatoire, max 4 L/min)
    debit_m3_s = random.uniform(0, 0.00004) * random.randint(0, 1)
    # Calcul du volume écoulé depuis le dernier appel
    delta_s = 0
    if _last_water_call is not None:
        delta_s = (now - _last_water_call)
        volume_m3 = debit_m3_s * delta_s  # conversion L -> m³
        _total_water_volume += volume_m3
    _last_water_call = now
    logging.info("Débit: %s m3/s, Volume: %s m3 en %ss", debit_m3_s, _total_water_volume, delta_s)
    return round(debit_m3_s, 6), round(_total_water_volume, 6)
