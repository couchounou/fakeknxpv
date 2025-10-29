import http.server
import socketserver
import os
import asyncio
import json
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
)

import threading
from xknx.telegram.apci import GroupValueWrite
from datetime import datetime
from pv_data import get_pv_data
from conso_data import get_conso_data
from meteo_data import get_meteo_data
import configparser
import socket

import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # On se connecte à une adresse externe sans envoyer de données
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def publish_upnp_service(ip, port=8080):
    import socket
    ssdp_message = (
        "NOTIFY * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "NT: upnp:rootdevice\r\n"
        "NTS: ssdp:alive\r\n"
        "USN: uuid:FakeKNXpv::upnp:rootdevice\r\n"
        f"LOCATION: http://{ip}:{port}/description.xml\r\n"
        "CACHE-CONTROL: max-age=1800\r\n"
        "SERVER: FakeKNXpv/1.0 UPnP/1.0\r\n"
        "\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.sendto(ssdp_message.encode("utf-8"), ("239.255.255.250", 1900))
    sock.close()

def run_simple_http_server(text="", port=80):
    global json_status
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/description.xml":
                self.send_response(200)
                self.send_header("Content-type", "application/xml")
                self.end_headers()
                xml = f"""\
                    <?xml version="1.0"?>
                    <root xmlns="urn:schemas-upnp-org:device-1-0">
                        <specVersion>
                            <major>1</major>
                            <minor>0</minor>
                        </specVersion>
                        <device>
                            <deviceType>urn:schemas-upnp-org:device:SimuPV:1</deviceType>
                            <friendlyName>SimuPV KNX Device</friendlyName>
                            <manufacturer>SimuPV</manufacturer>
                            <modelName>SimuPV KNX</modelName>
                            <UDN>uuid:SimuPV</UDN>
                            <presentationURL>http://{get_local_ip()}:{port}</presentationURL>
                        </device>
                    </root>
                    """
                self.wfile.write(xml.encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(json_status).encode("utf-8"))

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving HTTP on port {port}...")
        httpd.serve_forever()

json_status={
    "version": "0.4.0",
    "updated": "",
    "injection": {
        "W": {
            "group_address": "",
            "value": 0
        },
        "Wh": {
            "group_address": "",
            "value": 0
        }
    },
    "soutirage": {
        "W": {
            "group_address": "",
            "value": 0
        },
        "Wh": {
            "group_address": "",
            "value": 0
        }
    },
    "consommation": {
        "W": {
            "group_address": "",
            "value": 0
        },
        "Wh": {
            "group_address": "",
            "value": 0
        }
    },
    "production": {
        "W": {
            "group_address": "",
            "value": 0
        },
        "Wh": {
            "group_address": "",
            "value": 0
        }
    },
    "meteo": {
        "temperature": {
            "group_address": "",
            "value": 0
        },
        "humidity": {
            "group_address": "",
            "value": 0
        },
        "pressure": {
            "group_address": "",
            "value": 0
        }
    }
}


last_updated_timestamp = last_saved_timestamp = datetime.now().timestamp()
inj_index = sout_index = conso_index = prod_index = 0.0
basepath = os.path.abspath(os.path.dirname(__file__))
knx_messages_log = ""


# try use default raspberry config path
# create config dir if not exists
# else use local path

inj_index_file_path = "/boot/config_rw/index_inject.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_inject.txt")
sout_index_file_path = "/boot/config_rw/index_sout.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_sout.txt")
conso_index_file_path = "/boot/config_rw/index_conso.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_conso.txt")
prod_index_file_path = "/boot/config_rw/index_prod.txt" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "index_prod.txt")
config_file = "/boot/config_rw/cyclic_send_toknx_pv_data.cfg" if os.path.exists("/boot/config_rw/") else os.path.join(basepath, "cyclic_send_toknx_pv_data.cfg")
print(f"Using files: \n {inj_index_file_path}\n {sout_index_file_path}\n {conso_index_file_path}\n {prod_index_file_path}\n {config_file=}")

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
        try:
            publish_upnp_service(get_local_ip(), 8080)
        except Exception as e:
            print(f"Error publishing UPnP service: {e}")
            logging.error(f"Error publishing UPnP service: {e}")
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
    global last_updated_timestamp, last_saved_timestamp, inj_index, sout_index, conso_index, prod_index, json_status
    try:
        while True:
            knx_messages_log = ""  # Reset log at each loop
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
                knx_messages_log += f"Simu prod:  {round(production_W, 2)}W({round(production_wh, 2)}Wh)\n"
                knx_messages_log += f"Simu conso: {round(conso_w, 2)}W({round(conso_wh, 2)}Wh)\n"
                knx_messages_log += f"Simu Injection: {round(inj_w, 2)}W({round(inj_wh, 2)}Wh), Soutirage: {round(sout_w, 2)}W - {round(sout_wh, 2)}Wh\n"
                knx_messages_log += f"Meteo: clouds={myclouds  *100}%, temp={temperature}C, humidity={humidity}%, pressure={pressure}hPa\n"
                
                # Send prod data to KNX
                knx_messages_log += f"Send PROD {int(production_W)}W to group={prod_power_address} and {int(prod_index)}Wh to group={prod_energy_address}\n"
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

                json_status["production"]["W"]["group_address"] = prod_power_address
                json_status["production"]["W"]["value"] = int(production_W)
                json_status["production"]["Wh"]["group_address"] = prod_energy_address
                json_status["production"]["Wh"]["value"] = int(prod_index)

                # Send conso data to KNX
                knx_messages_log += f"Send CONSO {int(conso_w)}W to group={conso_power_address} and {int(conso_index)}Wh to group={conso_energy_address}\n"
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

                json_status["consommation"]["W"]["group_address"] = conso_power_address
                json_status["consommation"]["W"]["value"] = int(conso_w)
                json_status["consommation"]["Wh"]["group_address"] = conso_energy_address
                json_status["consommation"]["Wh"]["value"] = int(conso_index)

                # Send injection data to KNX
                knx_messages_log += f"Send INJ {int(-inj_w)}W to group={inj_power_address} and {int(inj_index)}Wh to group={inj_energy_address}\n"
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

                json_status["injection"]["Wh"]["group_address"] = inj_energy_address
                json_status["injection"]["Wh"]["value"] = int(inj_index)
                json_status["injection"]["W"]["group_address"] = inj_power_address
                json_status["injection"]["W"]["value"] = int(-inj_w)

                # Send soutirage data to KNX
                knx_messages_log += f"Send SOUT {int(sout_w)}W to group={sout_power_address} and {int(sout_index)}Wh to group={sout_energy_address}\n"
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

                json_status["soutirage"]["Wh"]["group_address"] = sout_energy_address
                json_status["soutirage"]["Wh"]["value"] = int(sout_index)
                json_status["soutirage"]["W"]["group_address"] = sout_power_address
                json_status["soutirage"]["W"]["value"] = int(sout_w)

                # Send meteo data to log
                knx_messages_log += f"Send METEO pressure={pressure}hPa to group={pressure_address}, temperature={temperature}C to group={temperature_address}, humidity={humidity}% to group={humidity_address}\n"
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
                json_status["meteo"]["pressure"]["group_address"] = pressure_address
                json_status["meteo"]["pressure"]["value"] = pressure
                json_status["meteo"]["temperature"]["group_address"] = temperature_address
                json_status["meteo"]["temperature"]["value"] = temperature
                json_status["meteo"]["humidity"]["group_address"] = humidity_address
                json_status["meteo"]["humidity"]["value"] = humidity
                json_status["updated"] = datetime.now().isoformat()
                last_saved_timestamp = save_indexes(save_cycle_s) or last_saved_timestamp
                print(knx_messages_log)
                logging.info(knx_messages_log)
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
        filename=config_file,
        filemode="a",
        format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    threading.Thread(target=run_simple_http_server, args=("SimuPV device is online", 8080), daemon=True).start()
    # asyncio.run(scan())  
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="UTF-8") as myfile:
            json_status["version"] = myfile.read().strip()
    else:
        json_status["version"] = "Unknown"
    json_status["gateway"] = str(conf["knx"]["gateway_ip"]) + ":" + str(conf["knx"]["gateway_port"])
    json_status["save_cycle_s"] = conf["knx"]["save_cycle_s"]
    json_status["send_cycle_s"] = conf["knx"]["send_cycle_s"]
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
            longitude=conf["lon"],
            latitude=conf["lat"],
            household_power=conf["household_power"],
            panel_power=conf["panel_power"],
            delay=conf["knx"]["send_cycle_s"],
            weather_api_key=conf["weather"]["api_key"],
            save_cycle_s=conf["knx"]["save_cycle_s"],
        )
    )
