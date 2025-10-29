import http.server
import socketserver

def run_simple_http_server(response_text="SimuPV device is online", port=80):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(response_text.encode("utf-8"))

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving HTTP on port {port}...")
        httpd.serve_forever()

import os
import asyncio
from xknx import XKNX
import logging
from xknx.telegram import GroupAddress, Telegram
from xknx.io import ConnectionConfig, ConnectionType, GatewayScanner
from xknx.dpt import (
    DPTPower,
    DPTActiveEnergy,
    DPTPressure2Byte,
    DPTTemperature,
    DPTHumidity,
    DPTString
)

from xknx.telegram.apci import GroupValueWrite
from datetime import datetime
from pv_data import get_pv_data
from conso_data import get_conso_data
from meteo_data import get_meteo_data
import configparser


last_updated_timestamp = last_saved_timestamp = datetime.now().timestamp()
inj_index = sout_index = conso_index = prod_index = 0.0
basepath = os.path.abspath(os.path.dirname(__file__))

# try use default raspberry config path
# create config dir if not exists
# else use local path

inj_index_file_path = "/boot/config_rw/index_inject.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_inject.txt")
sout_index_file_path = "/boot/config_rw/index_sout.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_sout.txt")
conso_index_file_path = "/boot/config_rw/index_conso.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_conso.txt")
prod_index_file_path = "/boot/config_rw/index_prod.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_prod.txt")

print(f"Using index files: \n {inj_index_file_path}\n {sout_index_file_path}\n {conso_index_file_path}\n {prod_index_file_path}")

# create index files if not exists and read values
if os.path.exists(inj_index_file_path):
    with open(inj_index_file_path, "r", encoding="UTF-8") as myfile:
        inj_index = float(myfile.read() or "0")
else:
    with open(inj_index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write("0.0")
if os.path.exists(sout_index_file_path):
    with open(sout_index_file_path, "r", encoding="UTF-8") as myfile:
        sout_index = float(myfile.read() or "0")
else:
    with open(sout_index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write("0.0")
if os.path.exists(conso_index_file_path):
    with open(conso_index_file_path, "r", encoding="UTF-8") as myfile:
        conso_index = float(myfile.read() or "0")
else:
    with open(conso_index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write("0.0")
if os.path.exists(prod_index_file_path):
    with open(prod_index_file_path, "r", encoding="UTF-8") as myfile:
        prod_index = float(myfile.read() or "0")
else:
    with open(prod_index_file_path, "w", encoding="UTF-8") as myfile:
        myfile.write("0.0")


def encode_dpt16(text: str) -> bytes:
    data = text.encode("latin-1")[:14]
    return data.ljust(14, b'\x00') 


def save_indexes(save_cycle_s):
    if last_saved_timestamp < datetime.now().timestamp() - save_cycle_s:
        with open(inj_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write(str(inj_index))
        with open(sout_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write(str(sout_index))
        with open(conso_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write(str(conso_index))
        with open(prod_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write(str(prod_index))
        print("Indexes saved to files.")
        logging.info("Indexes saved to files.")
        return datetime.now().timestamp()
    return None


def get_inj_data(conso: float = 0, prod: float = 0, updated_timestamp=datetime.now().timestamp()):
    delta = datetime.now().timestamp() - updated_timestamp
    inj = prod - conso
    sout_power = 0
    diff_sout_index = 0
    inj_power = 0
    diff_inj_index = 0
    energy = abs(inj) * delta / 3600

    if inj > 0:
        inj_power = inj
        diff_inj_index = energy
    else:
        sout_power = -inj
        diff_sout_index = energy

    return inj_power, diff_inj_index, sout_power, diff_sout_index


async def send_power_data(
    delay,
    gateway_ip,
    gateway_port,
    conso_power_address,
    conso_energy_address,
    prod_power_address,
    prod_energy_address,
    inj_power_address,
    inj_energy_address,
    sout_power_address,
    sout_energy_address,
    pressure_address,
    temperature_address,
    humidity_address,
    text_address,
    longitude,
    latitude,
    household_power,
    panel_power,
    weather_api_key=None,
    save_cycle_s=3600
):
    print(
        f"Start cyclic send to knxip {gateway_ip}:{gateway_port}"
        f" {prod_power_address=}, {prod_energy_address=}, {inj_power_address=}," 
        f" {inj_energy_address=}, {sout_power_address=}, {sout_energy_address=}"
    )

    # Configuration XKNX
    connection_config = ConnectionConfig(
        connection_type=ConnectionType.TUNNELING,
        gateway_ip=gateway_ip,
        gateway_port=gateway_port,
    )
    print(f"XKNX connecting to {gateway_ip}:{gateway_port}")
    xknx = XKNX(connection_config=connection_config)
    print("XKNX starting...")
    await xknx.start()
    print("XKNX started")
    global last_updated_timestamp, last_saved_timestamp, inj_index, sout_index, conso_index, prod_index
    try:
        while True:
            try:
                myclouds, temperature, humidity, pressure = get_meteo_data.get_meteo_data(
                    lat=latitude,
                    lon=longitude,
                    api_key=weather_api_key
                )

                production_W, production_wh, _, _ = get_pv_data.get_pv_data(
                    latitude=latitude,
                    longitude=longitude,
                    power=panel_power,
                    updated_timestamp=last_updated_timestamp,
                    myclouds=myclouds
                )

                conso_w, conso_wh = get_conso_data.get_conso_data(
                    power=household_power,
                    updated_timestamp=last_updated_timestamp
                )

                inj_w, inj_wh, sout_w, sout_wh = get_inj_data(
                    conso_w,
                    production_W,
                    updated_timestamp=last_updated_timestamp
                )
                myclouds = 0.8 if myclouds is None else myclouds
                last_updated_timestamp = datetime.now().timestamp()
                inj_index += inj_wh
                sout_index += sout_wh
                conso_index += conso_wh
                prod_index += production_wh
                print(
                    f"   Simu prod:  {round(production_W, 2)}W({round(production_wh, 2)}Wh)"
                )
                print(
                    f"   Simu conso: {round(conso_w, 2)}W({round(conso_wh, 2)}Wh)"
                )
                print(
                    f"   Simu Injection: {round(inj_w, 2)}W({round(inj_wh, 2)}Wh), Soutirage: {round(sout_w, 2)}W({round(sout_wh, 2)}Wh"
                )
                print(
                    f"   Meteo: clouds={myclouds  *100}%, temp={temperature}C, humidity={humidity}%, pressure={pressure}hPa"

                
                # Send prod data to KNX
                )
                print(
                    f"Send PROD {int(production_W)}W to prod_power_address={prod_power_address} and {int(prod_index)}Wh to energy_address={prod_energy_address}"
                )
                telegram = Telegram(
                    destination_address=GroupAddress(prod_energy_address),
                    payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(prod_index))),
                )
                await xknx.telegrams.put(telegram)

                telegram = Telegram(
                    destination_address=GroupAddress(prod_power_address),
                    payload=GroupValueWrite(DPTPower.to_knx(int(production_W))),
                )
                await xknx.telegrams.put(telegram)

                # Send conso data to KNX
                print(
                    f"Send CONSO {int(conso_w)}W to conso_power_address={conso_power_address} and {int(conso_index)}Wh to conso_energy_address={conso_energy_address}"
                )
                telegram = Telegram(
                    destination_address=GroupAddress(conso_energy_address),
                    payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(conso_index))),
                )
                await xknx.telegrams.put(telegram)

                telegram = Telegram(
                    destination_address=GroupAddress(conso_power_address),
                    payload=GroupValueWrite(DPTPower.to_knx(int(conso_w))),
                )
                await xknx.telegrams.put(telegram)

                # Send injection data to KNX
                print(
                    f"Send INJ {int(-inj_w)}W to inj_power_address={inj_power_address} and {int(inj_index)}Wh to inj_energy_address={inj_energy_address}"
                )
                telegram = Telegram(
                    destination_address=GroupAddress(inj_energy_address),
                    payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(inj_index))),
                )
                await xknx.telegrams.put(telegram)

                telegram = Telegram(
                    destination_address=GroupAddress(inj_power_address),
                    payload=GroupValueWrite(
                        DPTPower.to_knx(int(-inj_w))
                    ),
                )
                await xknx.telegrams.put(telegram)

                # Send soutirage data to KNX
                print(
                    f"Send SOUT {int(sout_w)}W to sout_power_address={sout_power_address} and {int(sout_index)}Wh to sout_energy_address={sout_energy_address}"
                )
                telegram = Telegram(
                    destination_address=GroupAddress(sout_energy_address),
                    payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(sout_index))),
                )
                await xknx.telegrams.put(telegram)

                telegram = Telegram(
                    destination_address=GroupAddress(sout_power_address),
                    payload=GroupValueWrite(
                        DPTPower.to_knx(int(sout_w))
                    ),
                )
                await xknx.telegrams.put(telegram)
                
                # Send meteo data to log
                print(
                    f"Send METEO pressure={pressure}hPa to pressure_address={pressure_address},"
                    f" temperature={temperature}C to temperature_address={temperature_address},"
                    f" humidity={humidity}% to humidity_address={humidity_address}"
                )
                if pressure:
                    telegram = Telegram(
                        destination_address=GroupAddress(pressure_address),
                        payload=GroupValueWrite(DPTPressure2Byte.to_knx(int(pressure * 100))),
                    )
                    await xknx.telegrams.put(telegram)
                if temperature:
                    telegram = Telegram(
                        destination_address=GroupAddress(temperature_address),
                        payload=GroupValueWrite(DPTTemperature.to_knx(float(temperature))),
                    )
                    await xknx.telegrams.put(telegram)
                if humidity:
                    telegram = Telegram(
                        destination_address=GroupAddress(humidity_address),
                        payload=GroupValueWrite(DPTHumidity.to_knx(int(humidity))),
                    )
                    await xknx.telegrams.put(telegram)
                last_saved_timestamp = save_indexes(save_cycle_s) or last_saved_timestamp
            except Exception as e:
                logging.info(f"Error in main loop: {e}")
            await asyncio.sleep(delay)
    except Exception as e:
        logging.info(e)
    finally:
        await xknx.stop()


def load_config():
    if os.path.exists("/boot/config_rw/cyclic_send_toknx_pv_data.cfg"):
        path = "/boot/config_rw/cyclic_send_toknx_pv_data.cfg"
    else:
        path = "cyclic_send_toknx_pv_data.cfg"
    config = configparser.ConfigParser()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file {path} not found")
    config.read(path)
    print(f"Config sections: {config.sections()}")
    # --- CONFIG section ---
    lon = config.getfloat("CONFIG", "lon")
    lat = config.getfloat("CONFIG", "lat")
    panel_power = config.getint("CONFIG", "panel_power")
    household_power = config.getint("CONFIG", "household_power")

    # --- KNX section ---
    knx = {
        "gateway_ip": config.get("KNX", "gateway_ip"),
        "gateway_port": config.getint("KNX", "gateway_port"),
        "send_cycle_s": config.getint("KNX", "send_cycle_s"),
        "save_cycle_s": config.getint("KNX", "save_cycle_s"),
        "conso_power_group": config.get("KNX", "conso_power_group"),
        "conso_energy_group": config.get("KNX", "conso_energy_group"),
        "prod_power_group": config.get("KNX", "prod_power_group"),
        "prod_energy_group": config.get("KNX", "prod_energy_group"),
        "inj_energy_group": config.get("KNX", "inj_energy_group"),
        "inj_power_group": config.get("KNX", "inj_power_group"),
        "sout_energy_group": config.get("KNX", "sout_energy_group"),
        "sout_power_group": config.get("KNX", "sout_power_group"),
        "pressure_group": config.get("KNX", "pressure_group", fallback=None),
        "temperature_group": config.get("KNX", "temperature_group", fallback=None),
        "humidity_group": config.get("KNX", "humidity_group", fallback=None),
        "text_group": config.get("KNX", "text_group", fallback=None),
    }

    # You can return a dict, a namedtuple, or just print for now
    return {
        "lon": lon,
        "lat": lat,
        "panel_power": panel_power,
        "household_power": household_power,
        "knx": knx,
        "weather": {"api_key": config.get("OPENWEATHERMAP", "api_key", fallback=None)},
    }

async def scan() -> None:
    """Search for available KNX/IP devices with GatewayScanner and print out result if a device was found."""
    xknx = XKNX()
    gatewayscanner = GatewayScanner(xknx)

    async for gateway in gatewayscanner.async_scan():
        print(f"{gateway.individual_address} {gateway.name}{gateway.ip_addr}:{gateway.port}")
        tunnelling = (
            "Secure"
            if gateway.tunnelling_requires_secure
            else "TCP"
            if gateway.supports_tunnelling_tcp
            else "UDP"
            if gateway.supports_tunnelling
            else "No"
        )
        print(f"  Tunnelling: {tunnelling}")
        routing = (
            "Secure"
            if gateway.routing_requires_secure
            else "Yes"
            if gateway.supports_routing
            else "No"
        )
        print(f"  Routing: {routing}")
    if not gatewayscanner.found_gateways:
        print("⚠ No Gateways found\n")    

if __name__ == "__main__":
    conf = load_config()
    logging.basicConfig(
        filename=os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "cyclic_send_toknx_pv_data.log"
        ),
        filemode="a",
        format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    run_simple_http_server("SimuPV device is online", port=80)
    # asyncio.run(scan())
    asyncio.run(
        send_power_data(
            gateway_ip=conf["knx"]["gateway_ip"],
            gateway_port=conf["knx"]["gateway_port"],
            conso_power_address=conf["knx"]["conso_power_group"],
            conso_energy_address=conf["knx"]["conso_energy_group"],
            prod_power_address=conf["knx"]["prod_power_group"],
            prod_energy_address=conf["knx"]["prod_energy_group"],
            inj_power_address=conf["knx"]["inj_power_group"],
            inj_energy_address=conf["knx"]["inj_energy_group"],
            sout_power_address=conf["knx"]["sout_power_group"],
            sout_energy_address=conf["knx"]["sout_energy_group"],
            pressure_address=conf["knx"]["pressure_group"],
            temperature_address=conf["knx"]["temperature_group"],
            humidity_address=conf["knx"]["humidity_group"],
            text_address=conf["knx"]["text_group"],
            longitude=conf["lon"],
            latitude=conf["lat"],
            household_power=conf["household_power"],
            panel_power=conf["panel_power"],
            delay=conf["knx"]["send_cycle_s"],
            weather_api_key=conf["weather"]["api_key"],
            save_cycle_s=conf["knx"]["save_cycle_s"],
        )
    )
