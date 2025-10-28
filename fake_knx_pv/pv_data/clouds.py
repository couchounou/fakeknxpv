import logging
import requests


def clouds(lat, lon):
    API_KEY = "5090a14bf34a4879699a2418bf9b9913"
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

if __name__ == "__main__":
    logging.info(clouds(lat=48, lon=3))