# fake_knx_pv

Simulateur de production photovoltaïque, de consommation électrique et de quelques équipements domestiques. Il envoie les valeurs sur un bus KNX/IP, conserve des index et un historique, et expose un tableau de bord HTTP.

## Prérequis

- Python 3.7 ou supérieur ;
- une passerelle KNX/IP accessible en tunneling ;
- une clé API OpenWeatherMap (facultative, mais nécessaire pour obtenir les données météo en ligne).

Les dépendances Python (`xknx`, `pytz`, `astral` et `requests`) sont déclarées dans le projet.

## Installation et démarrage

Depuis une copie du dépôt, installez le projet et lancez le programme depuis la racine :

```shell
python -m pip install .
python fake_knx_pv/cyclic_send_toknx_pv_data.py
```

Le programme lit sa configuration dans `fake_knx_pv/cyclic_send_toknx_pv_data.cfg`. Le fichier `fake_knx_pv/cyclic_send_toknx_pv_data.cfg.exemple` donne un modèle ; copiez-le vers le nom attendu, puis adaptez les valeurs avant le démarrage.

## Configuration

Le fichier est au format INI et contient trois sections :

### `[CONFIG]`

| Clé | Description |
| --- | --- |
| `lon`, `lat` | Longitude et latitude utilisées pour le calcul solaire et la météo |
| `panel_power` | Puissance nominale configurée des panneaux photovoltaïques, en watts |
| `household_power` | Puissance maximale de référence de la maison, en watts |

### `[KNX]`

| Clé | Description | Défaut |
| --- | --- | --- |
| `gateway_ip` | Adresse IP de la passerelle KNX | obligatoire |
| `gateway_port` | Port KNX/IP | `3671` |
| `send_cycle_s` | Intervalle entre deux cycles de simulation, en secondes | `300` |
| `save_cycle_s` | Intervalle minimal entre deux sauvegardes des index et de l’historique, en secondes | `3600` |
| `dry_run` | Active le mode sans envoi pour les télégrammes passant par le mécanisme d’envoi commun | `false` |

Toutes les adresses de groupe ci-dessous sont configurables dans `[KNX]`. Les valeurs indiquées sont celles utilisées par défaut si la clé est absente.

| Donnée | Puissance / commande | Énergie / état |
| --- | --- | --- |
| Consommation totale | `conso_power_group` — `6/1/10` | `conso_energy_group` — `6/2/10` |
| Production PV | `prod_power_group` — `6/1/11` | `prod_energy_group` — `6/2/11` |
| Injection | `inj_power_group` — `6/1/12` | `inj_energy_group` — `6/2/12` |
| Soutirage | `sout_power_group` — `6/1/13` | `sout_energy_group` — `6/2/13` |
| Injection / soutirage combinés | `inj_sout_power_group` — `6/1/14` | — |
| ECS | `ecs_power_group` — `6/1/15` | `ecs_energy_group` — `6/2/15` |
| PAC | `pac_power_group` — `6/1/16` | `pac_energy_group` — `6/2/16` |
| Éclairage | `eclairage_power_group` — `6/1/17` | `eclairage_energy_group` — `6/2/17` |
| Autres consommations | `autres_power_group` — `6/1/18` | `autres_energy_group` — `6/2/18` |
| Pression météo | `pressure_group` — `6/3/10` | — |
| Humidité météo | `humidity_group` — `6/3/11` | — |
| Température météo | `temperature_group` — `6/3/12` | — |
| Switch simulé | `switch_group` — `7/1/1` | `switch_state_group` — `7/1/2` |
| Volet (monter/descendre) | `volet_up_down_group_address` — `7/1/3` | — |
| Volet (arrêt) | `volet_stop_group_address` — `7/1/4` | — |
| Volet (consigne de position) | `volet_setposition_group_address` — `7/1/5` | `volet_position_group_address` — `7/1/6` |
| Présence | `occupancy_group` — `8/1/1` | — |
| Compteur d’eau (index) | `eau_index_group` — `9/1/1` | — |
| Compteur d’eau (débit) | `eau_debit_group` — `9/1/2` | — |

Par exemple, pour modifier un groupe :

```ini
[KNX]
gateway_ip = 192.168.1.50
gateway_port = 3671
send_cycle_s = 30
save_cycle_s = 3600
dry_run = true
eclairage_power_group = 6/1/17
eclairage_energy_group = 6/2/17
autres_power_group = 6/1/18
autres_energy_group = 6/2/18
```

`dry_run` ne garantit pas que tous les télégrammes soient supprimés : les envois directs de météo ne passent pas par le mécanisme commun qui applique cette option. Vérifiez le comportement sur votre installation avant utilisation.

### `[OPENWEATHERMAP]`

La clé `api_key` est utilisée pour interroger OpenWeatherMap. La météo fournit la couverture nuageuse, la température, l’humidité et la pression. En cas d’indisponibilité du service, les valeurs météo peuvent être absentes et le cycle ne pas aboutir. Ne publiez pas une vraie clé API dans le dépôt ; remplacez les exemples par votre propre clé dans la configuration locale.

## Simulation électrique

À chaque cycle, le simulateur estime la production solaire et les consommations, puis calcule le bilan réseau :

```text
puissance nette = production PV - consommation totale
```

- si la production dépasse la consommation, le surplus est une injection ;
- si la consommation dépasse la production, la différence est un soutirage ;
- injection et soutirage ne sont pas positifs simultanément.

L’énergie de chaque cycle est estimée à partir du temps écoulé depuis le cycle précédent :

```text
énergie (Wh) = puissance (W) × durée écoulée (secondes) / 3 600
```

La production PV dépend de la puissance configurée des panneaux, de la position du soleil, de la saison et de la couverture nuageuse. La consommation est composée d’un profil de base et de postes simulés : chauffe-eau (ECS), pompe à chaleur (PAC) et éclairage. Le poste « autres » est le reliquat de la consommation totale après ces trois postes. La consommation et la production varient au cours de la journée ; les profils comportent également une part aléatoire.

Le compteur d’eau est lui aussi simulé : le débit instantané est aléatoire et le volume est cumulé en mémoire puis sauvegardé dans l’index.

Dans `data.json`, les puissances `injection.W.value` et `soutirage.W.value` sont positives ou nulles. En revanche, l’injection est représentée avec un signe négatif dans `history.injection` et `inj_sout.W.value` ; le soutirage reste positif.

## Équipements et commandes KNX

- **Switch principal** : les commandes sont reçues sur `switch_group` et l’état est publié sur `switch_state_group`. L’état de simulation bascule automatiquement environ toutes les 12 minutes.
- **Volet** : le programme accepte les ordres monter/descendre, arrêt et position. La position publiée est aussi simulée automatiquement à chaque cycle : elle vaut 0 % entre 22 h et 7 h 30, et une valeur aléatoire entre 80 % et 100 % le reste du temps.
- **Présence** : l’état simulé est calculé à partir de la consommation totale ; il est considéré présent lorsque celle-ci atteint au moins 5 % de `household_power`.
- **Équipements virtuels** : les plages d’adresses ci-dessous sont écoutées par le programme. Une commande reçue renvoie une valeur sur l’adresse correspondante avec un décalage d’adresse de groupe.

| Équipement virtuel | Commandes reçues | Retours |
| --- | --- | --- |
| 20 switches ON/OFF | `11/0/0` à `11/0/19` | état sur `11/0/20` à `11/0/39` ; position 0/100 % sur `11/1/20` à `11/1/39` |
| 20 positions | `11/1/0` à `11/1/19` | position sur `11/1/20` à `11/1/39` ; état ON/OFF sur `11/0/20` à `11/0/39` |
| 20 couleurs RGB | `11/2/0` à `11/2/19` | couleur RGB sur `11/2/20` à `11/2/39` |

Les retours secondaires des switches et positions sont envoyés avec un délai de deux secondes. Les positions reçues sont converties de l’échelle KNX 0–255 en pourcentage.

## Tableau de bord et fichiers de données

Au démarrage, un serveur HTTP est lancé sur le port `8080` :

- `http://<adresse-du-serveur>:8080/` affiche le tableau de bord ;
- `http://<adresse-du-serveur>:8080/data.json` renvoie les données courantes au format JSON ;
- `http://<adresse-du-serveur>:8080/description.xml` fournit la description UPnP.

Le tableau de bord actualise les données toutes les cinq secondes. Le bouton **Actualiser** force une lecture immédiate. Le graphique présente la production, l’injection, le soutirage et les postes ECS, PAC, éclairage et autres. Les séries d’historique sont conservées jusqu’à 48 heures ; celles ajoutées récemment apparaissent au fil des cycles. Les commandes visibles dans la page (switch et volet) ne sont que des interactions de démonstration locales : elles ne transmettent pas d’ordre KNX.

Le fichier `data.json` est réécrit à chaque cycle réussi. Les index énergétiques et historiques sont sauvegardés dans `indexes.json` et `history.json` selon `save_cycle_s`. Si `/boot/firmware/` existe, ces trois fichiers sont placés dans ce répertoire ; sinon, ils sont placés à côté du programme. Sous Raspberry Pi, le fichier de configuration placé dans `/boot/firmware/` est utilisé s’il existe, sinon le programme cherche celui qui se trouve à côté du script.

## Raspberry Pi et services systemd

Le script `install-rpi.sh` installe les dépendances système, crée l’environnement virtuel `/home/pi/venv`, installe le paquet depuis `/home/pi/fakeknxpv`, puis installe et active les services systemd. Il doit être exécuté par l’utilisateur `pi` (sans `sudo`) sur un système où `sudo` est disponible. S’il n’existe pas encore, le dépôt est cloné à `/home/pi/fakeknxpv`. Si `/boot/firmware/` existe et qu’aucune configuration n’y est présente, le script y copie le fichier d’exemple sans remplacer une configuration existante.

Depuis le dépôt cloné :

```shell
chmod +x install-rpi.sh
./install-rpi.sh
```

Après l’installation, configurez la passerelle, les adresses KNX et la clé météo dans `/boot/firmware/cyclic_send_toknx_pv_data.cfg` si ce fichier a été créé ; sinon, modifiez `fake_knx_pv/cyclic_send_toknx_pv_data.cfg`. Le service `fakeknxpv` démarre automatiquement au boot. Le service `gitupdate` synchronise le dépôt au démarrage ; ses journaux ainsi que ceux du simulateur sont consultables avec `sudo journalctl -u gitupdate.service` et `sudo journalctl -u fakeknxpv.service -f`.
