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



def get_pv_data(
    latitude: float,
    longitude: float,
    mydate: datetime = None,
    power=4000,
    updated_timestamp: float = datetime.now().timestamp(),
    myclouds: float = None
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

    if sunrise.timestamp() <= mydate.timestamp() <= sunset.timestamp():
        # Forme approximative d'un arc sinus (ensoleillement maximal à midi)
        if myclouds is None:
            myclouds = 0
        cloud_factor = (1 - myclouds) * 0.6 + (random.randint(0, 100) / 100) * 0.4
        angle = (mydate - sunrise).total_seconds() / (sunset - sunrise).total_seconds() * math.pi
        sunlight = math.sin(angle)
        # on applique le facteur de nuage sur 70% de la prod
        sunlight = sunlight * (0.3 + 0.70 * cloud_factor)
    day_of_year = mydate.timetuple().tm_yday
    seasonal_factor = 1 - 0.5 * math.cos(2 * math.pi * (day_of_year / 365.25))
    sunlight = sunlight * seasonal_factor
    logging.info(f"{sunlight=} {seasonal_factor=}, {cloud_factor=}")

    delta = datetime.now().timestamp() - updated_timestamp
    p = round(sunlight * power, 2)
    e = p * delta / 3600
    logging.info(f"Prod power:{p}W, diff energy:{e}Wh")
    return p, e, myclouds, cloud_factor
