
# Installation du package fake_knx_pv

## Prérequis
- Python 3.7 ou supérieur
- pip installé


## Installation
1. Téléchargez le fichier `.whl` fourni :
   - `fake_knx_pv-<version>-py3-none-any.whl`
2. Ouvrez un terminal dans le dossier contenant le fichier `.whl`.
3. Exécutez la commande suivante :
   
   ```
   pip install fake_knx_pv-<version>-py3-none-any.whl
   ```

## Utilisation
Après installation, utilisez directement le simulateur avec la commande :
   ```
   python cyclic_send_toknx_pv_data.py 
   ```
## Configuration et KNX
les données des config sont a personnaliser dans  cyclic_send_toknx_pv_data.cfg

## Postes de consommation

La consommation simulée est maintenant répartie entre la consommation totale, le chauffe-eau (ECS), la pompe à chaleur (PAC), l'éclairage et le poste « autres ». ECS, PAC et éclairage sont simulés séparément ; « autres » correspond à la puissance totale moins ces trois postes. Chaque poste possède une puissance instantanée (W) et un index énergétique cumulé (Wh).

Adresses de groupe KNX par défaut :

| Poste | Puissance (W) | Énergie (Wh) |
| --- | --- | --- |
| ECS | `6/1/15` | `6/2/15` |
| PAC | `6/1/16` | `6/2/16` |
| Éclairage | `6/1/17` | `6/2/17` |
| Autres | `6/1/18` | `6/2/18` |

Ces adresses peuvent être redéfinies dans la section `[KNX]` de `cyclic_send_toknx_pv_data.cfg` :

```ini
ecs_power_group = 6/1/15
ecs_energy_group = 6/2/15
pac_power_group = 6/1/16
pac_energy_group = 6/2/16
eclairage_power_group = 6/1/17
eclairage_energy_group = 6/2/17
autres_power_group = 6/1/18
autres_energy_group = 6/2/18
```

## Mécanique production, consommation et bilan réseau

À chaque cycle, le simulateur calcule la puissance PV et la consommation de la maison en watts (W), puis compare les deux :

```text
puissance nette = production PV - consommation totale
```

- Si la production dépasse la consommation, le surplus est compté comme **injection**.
- Si la consommation dépasse la production, la différence est comptée comme **soutirage**.
- Pour un même cycle, injection et soutirage ne sont pas positifs en même temps : l'un vaut zéro.

Exemple : avec 3 000 W de production et 2 400 W de consommation, l'injection est de 600 W et le soutirage de 0 W. Avec 1 800 W de production et 2 500 W de consommation, l'injection est de 0 W et le soutirage de 700 W.

L'énergie est estimée à chaque cycle à partir de la puissance et du temps écoulé depuis le cycle précédent :

```text
énergie (Wh) = puissance (W) × durée écoulée (secondes) / 3 600
```

Cette énergie est ajoutée aux index cumulés de production, consommation, injection et soutirage. Les index ECS, PAC, éclairage et autres sont calculés de la même manière. La production PV dépend de la puissance configurée des panneaux, de la position du soleil, de la saison et de la couverture nuageuse. La consommation de base varie selon l'heure et le jour de la semaine ; ECS, PAC et éclairage sont simulés séparément, puis le reliquat est affecté à « autres ».

Dans le JSON, `injection.W.value` et `soutirage.W.value` sont des puissances positives ou nulles. L'historique `history.injection` et la puissance combinée `inj_sout.W.value` utilisent, eux, un signe négatif pour l'injection ; le soutirage reste positif.


## Tableau de bord et données

Le serveur intégré fournit le tableau de bord sur le port `8080` et les données courantes sur `/data.json` (par exemple `http://<adresse-du-serveur>:8080/data.json`). La page relit ces données automatiquement toutes les 5 secondes. Le bouton **Actualiser** force une lecture immédiate sans recharger la page ; la sélection des séries visibles dans la légende du graphe est conservée au rafraîchissement.

Le graphe suit la production, l'injection, le soutirage, l'ECS, la PAC, l'éclairage et les autres consommations. Les points d'historique pour ces postes sont ajoutés à chaque cycle de simulation et conservés jusqu'à 48 heures. Les anciens historiques ne contiennent pas de points pour les postes ajoutés récemment : leurs courbes se rempliront au fil des cycles.

À chaque cycle réussi, l'état complet est aussi écrit dans `data.json`. Sur Raspberry Pi, le fichier est placé dans `/boot/firmware/data.json` si ce répertoire existe ; sinon, il est placé à côté du programme. Les index énergétiques et les historiques sont sauvegardés séparément dans `indexes.json` et `history.json` selon la durée `save_cycle_s`.


## 20 Switch virtuels on/off
commandes reçues sur 11/0/0-11/0/19
etats renvoyés sur 11/0/20-11/0/39

## 20 Positions virtuels %
commandes reçues sur 11/1/0-11/1/19
etats renvoyés sur 11/1/20-11/1/39

## 20 RGB 3 bytes virtuels %
commandes reçues sur 11/2/0-11/2/19
etats renvoyés sur 11/2/20-11/2/39


# Installation sur Raspberry Pi
Pour faciliter l'installation sur un Raspberry Pi, vous pouvez utiliser le script `install-rpi.sh` fourni dans le dépôt. Ce script automatise l'installation des dépendances nécessaires et du package.

## Service git-update
Le service `git-update` permet de maintenir automatiquement à jour le dépôt local en synchronisant régulièrement avec le dépôt distant. Il s'appuie sur le script `git-update.sh` et le fichier de service systemd `gitupdate.service`.


## Service fakeknxpv.service
Le service `fakeknxpv.service` permet de lancer automatiquement le simulateur KNX PV au démarrage du système, en arrière-plan, sous forme de service systemd. Il s'appuie sur le script principal `cyclic_send_toknx_pv_data.py` pour simuler et envoyer les données vers le bus KNX selon la configuration définie.
- Le service démarre le script de simulation au boot de la machine.
- Il assure le fonctionnement continu du simulateur, même après un redémarrage ou une coupure.
- Les logs du service peuvent être consultés via `journalctl` pour le suivi et le diagnostic.


### Utilisation du script d'installation
1. Rendez le script exécutable :
   ```
   chmod +x install-rpi.sh
   ```
2. Exécutez le script :
   ```
   ./install-rpi.sh
   ```
Le script installera automatiquement les dépendances et le package sur votre Raspberry Pi et les services associés.