import logging
import requests


def clouds(lat, lon, api_key=None):
    try:
        API_KEY = api_key
        URL = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
        logging.info(URL)
        response = requests.get(URL)
        data = response.json()
        cloud_coverage = None
        if "clouds" in data:
            cloud_coverage = data["clouds"]["all"]
            logging.info(f"Couverture nuageuse : {cloud_coverage}%")
        else:
            logging.info("Impossible de récupérer les données météo.")
        return cloud_coverage / 100 if cloud_coverage else None
    except Exception as e:
        logging.info(f"Erreur lors de la récupération des données météo : {e}")
        return None

if __name__ == "__main__":
    logging.info(clouds(lat=48, lon=3))