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
Après installation utilisez directement le simulateur avec la commande 
   ```
   python cyclic_send_toknx_pv_data.py 
   ```
## Configuration et KNX
les données des config sont a personnaliser dans  cyclic_send_toknx_pv_data.cfg


## Switch virtuels on/off
commandes reçues sur 11/0/0-11/0/19
etats renvoyés sur 11/0/20-11/0/39

## Poistion virtuels %
commandes reçues sur 11/1/0-11/1/19
etats renvoyés sur 11/1/20-11/1/39
