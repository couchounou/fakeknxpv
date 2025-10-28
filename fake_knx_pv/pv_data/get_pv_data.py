import os
import sys
from datetime import datetime, timedelta, date, timezone
import time
import math
import pytz
import asyncio
from astral import LocationInfo
from astral.sun import sun
import random
import logging
from pv_data import clouds


def get_pv_data(
    latitude: float,
    longitude: float,
    mydate: datetime = None,
    power=4000,
    weather_api_key: str = None,
):
    loc = LocationInfo(latitude=latitude, longitude=longitude)
    s = sun(loc.observer, date=mydate)
    timezone = loc.timezone
    if not mydate:
        mydate = datetime.now(tz=pytz.timezone(timezone))
    else:
        mydate.astimezone(pytz.timezone(timezone))
    sunrise = s["sunrise"]
    sunset = s["sunset"]
    sunlight = 0
    logging.info(f"{timezone=} {sunset=} {sunrise=}")
    cloud_factor = 1
    myclouds = clouds.clouds(lat=latitude, lon=longitude, api_key=weather_api_key)
    if sunrise.timestamp() <= mydate.timestamp() <= sunset.timestamp():
        # Forme approximative d'un arc sinus (ensoleillement maximal à midi)
        if myclouds is None:
            myclouds = 0
        cloud_factor = (1 - myclouds) * 0.6 + (random.randint(0, 100) / 100) * 0.4
        angle = (mydate - sunrise).total_seconds() / (sunset - sunrise).total_seconds() * math.pi
        sunlight = math.sin(angle)
        # on applique le facteur de nuage sur 70% de la prod
        sunlight = sunlight *(0.3 + 0.70 * cloud_factor)
    day_of_year = mydate.timetuple().tm_yday
    seasonal_factor = 1 - 0.5 * math.cos(2 * math.pi * (day_of_year / 365.25))
    logging.info(f"{sunlight=} {seasonal_factor=}, {cloud_factor=}")
    sunlight = sunlight * seasonal_factor
    logging.info(f"{sunlight=} {seasonal_factor=}, {cloud_factor=}")
    index_file_path = "index_prod.txt"
    if os.path.exists(index_file_path):
        updated_timestamp = os.path.getmtime(index_file_path)
    else:
        updated_timestamp = datetime.now().timestamp()
        with open(index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write("0.0")
    delta = datetime.now().timestamp() - updated_timestamp
    p = round(sunlight * power, 2)
    e = p * delta / 3600
    logging.info(f"power:{p}W, energy:{e}Wh")
    old_index = 0.
    index = 0.
    with open(index_file_path, "r", encoding="UTF-8") as myfile:
        old_index = float(myfile.read())
        index = old_index + e
    with open(index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write(str(index))
    logging.info(f"prod index:{old_index}Wh, New index:{index}Wh")
    return p, index, myclouds, cloud_factor
