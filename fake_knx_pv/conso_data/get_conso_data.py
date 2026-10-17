from datetime import datetime
import math
import random
import logging


# Variables d'état pour le chauffe-eau
_chauffe_eau_active = False
_chauffe_eau_start = None
_chauffe_eau_end = None
_pac_active = False
_pac_start = None
_pac_end = None
_pac_p_cible = 0.0


def eclairage_profile(heure, mois, puissance_max_led_w=200):
    """Retourne la puissance consommée (W) par l'éclairage de la maison

    en fonction de l'heure (0.0 à 23.99) et du mois (1 à 12).

    - Puissance max simultanée (tout allumé) : 200 W (LEDs)
    - Prise en compte de la durée du jour selon la saison
    """
    h = heure % 24

    # 1. Détermination de l'heure du coucher / lever du soleil selon la saison
    # Hiver (mois 1, 12) : soleil ~08h00 à ~17h00
    # Été (mois 6, 7)   : soleil ~06h00 à ~22h00
    facteur_saison = math.cos((mois - 1) * math.pi / 6)  # 1 en Janvier, -1 en Juillet

    heure_coucher = 19.5 - (2.5 * facteur_saison)  # 17h en hiver, 22h en été
    heure_lever = 7.0 + (1.0 * facteur_saison)      # 8h en hiver, 6h en été

    puissance_base_w = 0.0

    # 2. Logique selon les périodes de la journée
    if 0.5 <= h < heure_lever - 1:
        # Nuit profonde : 0W, mais petite probabilité d'un éclairage ponctuel (passage WC/eau)
        if random.random() < 0.05:
            puissance_base_w = random.uniform(10, 30)

    elif heure_lever - 1 <= h < heure_lever + 1.5:
        # Matin : Réveil et préparation avant le départ
        # En hiver il fait nuit -> fort besoin. En été il fait jour -> très faible besoin.
        besoin_matin = 0.8 if h < heure_lever else 0.3
        puissance_base_w = puissance_max_led_w * 0.5 * besoin_matin

    elif heure_lever + 1.5 <= h < heure_coucher:
        # Journée : Lumière naturelle disponible.
        # Faible éclairage résiduel dans pièces sombres/bureau (10 à 20% du max)
        puissance_base_w = puissance_max_led_w * random.uniform(0.05, 0.15)

    elif heure_coucher <= h < 23.5:
        # Soirée : Soirée en famille, repas, détente (Pic principal)
        # La puissance augmente progressivement à mesure que la nuit tombe
        progression = min(1.0, (h - heure_coucher) + 0.5)

        # Pic maximum entre 19h et 22h (jusqu'à 70-90% de la puissance LED installée)
        facteur_presence = 0.85 if 19 <= h <= 22 else 0.5
        puissance_base_w = puissance_max_led_w * facteur_presence * progression

    else:
        # Fin de nuit (23h30 - 00h30) : Extinction progressive avant le coucher
        puissance_base_w = puissance_max_led_w * 0.15

    # 3. Ajout d'une instabilité/bruit aléatoire (allumage/extinction d'une pièce : ±20 W)
    bruit_w = random.uniform(-15, 15) if puissance_base_w > 0 else 0.0
    puissance_totale_w = max(0.0, min(puissance_max_led_w, puissance_base_w + bruit_w))

    return float(puissance_totale_w)


def pac_chauffage_profile(heure, mois, pmax_w=3000):
    """Retourne la puissance consommée (W) par la pompe à chaleur.

    Simule des cycles de chauffe quotidiens réalistes en hiver (pas 24h/24).
    """
    h = heure % 24

    # 1. Saisonnalité (1.0 en Janvier/Décembre, 0.0 en Juillet)
    facteur_saison = max(0.0, math.cos((mois - 1) * math.pi / 6))

    # Coupé de juin à août
    if facteur_saison < 0.15:
        return 0.0

    # 2. Définition des plages d'activation quotidiennes (Thermostat)
    # Matin (05h-09h), Midi (11h30-13h30), Soirée (17h-22h30), Relance nuit (02h-03h30)
    en_periode_chauffe = (
        (5.0 <= h < 9.0)
        or (11.5 <= h < 13.5)
        or (17.0 <= h < 22.5)
        or (2.0 <= h < 3.5)
    )

    if not en_periode_chauffe:
        # En dehors des créneaux : PAC à l'arrêt complet
        return 0.0

    # 3. Profil de besoin thermique selon l'heure (froid nocturne/matinal)
    besoin_horaire = 0.85 + 0.15 * math.cos((h - 5) * math.pi / 12)

    # 4. Puissance modulée (Inverter) selon le besoin et la saison
    puissance_cible = pmax_w * facteur_saison * besoin_horaire

    # 5. Ajout de bruit instantané (±100 W)
    bruit = random.uniform(-100, 100)
    puissance_instantanee = puissance_cible + bruit

    # Talon minimal de 600 W pendant qu'elle fonctionne
    return float(max(600.0, min(pmax_w, puissance_instantanee)))


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
    puissance_totale, puissance_ecs, puissance_pac, puissance_eclairage = profil_maison(
        datetime.now().hour,
        datetime.now().weekday(),
        pmax_w=power
    )
    autre = puissance_totale - (puissance_ecs + puissance_pac + puissance_eclairage)
    e_autre = autre * delta / 3600
    e_totale = puissance_totale * delta / 3600
    e_ecs = puissance_ecs * delta / 3600
    e_pac = puissance_pac * delta / 3600
    e_eclairage = puissance_eclairage * delta / 3600
    logging.info(
        "P totale:%sW, E totale:%sWh, P ECS:%sW, E ECS:%sWh, P PAC:%sW, E PAC:%sWh, P Eclairage:%sW, E Eclairage:%sWh, P Autre:%sW, E Autre:%sWh",
        puissance_totale,
        e_totale,
        puissance_ecs,
        e_ecs,
        puissance_pac,
        e_pac,
        puissance_eclairage,
        e_eclairage,
        autre,
        e_autre
    )
    return (
        round(puissance_totale, 2),
        e_totale, round(puissance_ecs, 2),
        e_ecs, round(puissance_pac, 2),
        e_pac,
        round(puissance_eclairage, 2),
        e_eclairage,
        round(autre, 2),
        e_autre
    )


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
    logging.info(
        "Puissance base: %sW, Heure: %s, Jour semaine: %s",
        puissance_base_w,
        h,
        jour_semaine
    )
    # 3. Ajout de la courbe chauffe-eau (déjà en Watts)
    puissance_ecs_w = chauffe_eau_profile(h)
    puissance_pac_w = pac_chauffage_profile(h, datetime.now().month)
    puissance_eclairage_w = eclairage_profile(h, datetime.now().month)
    puissance_w = puissance_base_w + puissance_ecs_w + puissance_pac_w + puissance_eclairage_w

    # 4. Ajout d'un bruit aléatoire (±300 W)
    bruit_w = random.uniform(0, 300)
    puissance_w += bruit_w

    # 5. Borne la puissance entre un talon minimum aléatoire (12 W à 48 W) et pmax_w
    talon_min_w = random.uniform(80, 240)
    puissance_totale_w = max(talon_min_w, min(pmax_w, puissance_w))

    return float(puissance_totale_w), float(puissance_ecs_w), float(puissance_pac_w), float(puissance_eclairage_w)


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
