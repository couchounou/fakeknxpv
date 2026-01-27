
# Installation du package fake_knx_pv

## Prérequis
- Python 3.7 ou supérieur
- pip installé


## Installation
1. Téléchargez le fichier `.whl` fourni :
   - `fake_knx_pv-0.1.0-py3-none-any.whl`
2. Ouvrez un terminal dans le dossier contenant le fichier `.whl`.
3. Exécutez la commande suivante :
   
   ```
   pip install fake_knx_pv-0.1.0-py3-none-any.whl
   ```

## Utilisation
Après installation, utilisez directement le simulateur avec la commande :
   ```
   python cyclic_send_toknx_pv_data.py 
   ```
## Configuration et KNX
les données des config sont a personnaliser dans  cyclic_send_toknx_pv_data.cfg


## 20 Switch virtuels on/off
commandes reçues sur 11/0/0-11/0/19
etats renvoyés sur 11/0/20-11/0/39

## 20 Positions virtuels %
commandes reçues sur 11/1/0-11/1/19
etats renvoyés sur 11/1/20-11/1/39

## 20 RGB 3 bytes virtuels %
commandes reçues sur 11/2/0-11/1/19
etats renvoyés sur 11/2/20-11/1/39


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