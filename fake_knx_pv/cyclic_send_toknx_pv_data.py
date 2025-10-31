import http.server
from datetime import timedelta
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
    DPTSwitch,
    DPTScaling,
    DPTBinary,
    DPTArray,
    DPTOccupancy
)

import threading
from xknx.telegram.apci import GroupValueWrite
from datetime import datetime
from pv_data import get_pv_data
from conso_data import get_conso_data
from meteo_data import get_meteo_data
import configparser
import socket
from devices import volet
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
    import textwrap
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/description.xml":
                self.send_response(200)
                self.send_header("Content-type", "application/xml")
                self.end_headers()
                xml = textwrap.dedent(f"""\
                    <?xml version="1.0"?>
                    <root xmlns="urn:schemas-upnp-org:device-1-0">
                        <specVersion>
                            <major>1</major>
                            <minor>0</minor>
                        </specVersion>
                        <device>
                            <deviceType>urn:schemas-upnp-org:device:FakeKNXpv:1</deviceType>
                            <friendlyName>Fake KNX Device</friendlyName>
                            <manufacturer>Rexel</manufacturer>
                            <modelName>FakeKNXpv</modelName>
                            <UDN>uuid:FakeKNXpv</UDN>
                            <presentationURL>http://{get_local_ip()}:{port}</presentationURL>
                        </device>
                    </root>
                    """)
                self.wfile.write(xml.encode("utf-8"))
            elif self.path == "/data.json":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(json_status).encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = os.path.join(basepath, "html", "view.html")
                with open(html, "r", encoding="utf-8") as myfile:
                    self.wfile.write(myfile.read().encode("utf-8"))

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving HTTP on port {port}...")
        httpd.serve_forever()

json_status={
    "version": "0.4.0",
    "updated": "",
    "inj_sout": {"W": {},},
    "injection": {"W": {}, "Wh": {}},
    "soutirage": {"W": {}, "Wh": {}},
    "consommation": {"W": {}, "Wh": {}},
    "production": {"W": {}, "Wh": {}},
    "meteo": {
        "temperature": {},
        "humidity": {},
        "pressure": {}
    },
    "switch": {"group_address": "", "state_group_address": "", "state": False},
    "volet": {"up_down_group_address": "", "stop_group_address": "", "setposition_group_address": "", "position_group_address": ""},
    "occupancy": {"group_address": "", "state_group_address": "", "state": False},
    "history": {
        "production": [],
        "injection": [],
        "soutirage": []
    }
}

volet = volet()

last_updated_timestamp = last_saved_timestamp = datetime.now().timestamp()
inj_index = sout_index = conso_index = prod_index = 0.0
basepath = os.path.abspath(os.path.dirname(__file__))
knx_messages_log = ""


# try use default raspberry config path
# create config dir if not exists
# else use local path

inj_index_file_path = "/boot/firmware/index_inject.txt" if os.path.exists("/boot/firmware/") else os.path.join(basepath, "index_inject.txt")
sout_index_file_path = "/boot/firmware/index_sout.txt" if os.path.exists("/boot/firmware/") else os.path.join(basepath, "index_sout.txt")
conso_index_file_path = "/boot/firmware/index_conso.txt" if os.path.exists("/boot/firmware/") else os.path.join(basepath, "index_conso.txt")
prod_index_file_path = "/boot/firmware/index_prod.txt" if os.path.exists("/boot/firmware/") else os.path.join(basepath, "index_prod.txt")
config_file = "/boot/firmware/cyclic_send_toknx_pv_data.cfg" if os.path.exists("/boot/firmware/cyclic_send_toknx_pv_data.cfg") else os.path.join(basepath, "cyclic_send_toknx_pv_data.cfg")
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


def update_history(history_list, value, max_hours=48):
    now = datetime.now().isoformat()
    history_list.append({"timestamp": now, "value": value})
    # Supprime les entrées de plus de 48h
    cutoff = datetime.now() - timedelta(hours=max_hours)
    # On garde uniquement les entrées récentes
    history_list[:] = [item for item in history_list if datetime.fromisoformat(item["timestamp"]) >= cutoff]


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
        sout_power = abs(inj)
        diff_sout_index = energy

    return inj_power, diff_inj_index, sout_power, diff_sout_index


async def send_power_telegram(
    xknx,
    group_address,
    value
):
    dpt = DPTPower.to_knx(int(value))
    await send_telegram(xknx, group_address, dpt)


async def send_energy_telegram(
    xknx,
    group_address,
    value
):
    dpt = DPTActiveEnergy.to_knx(int(value))
    await send_telegram(xknx, group_address, dpt)


async def send_position_telegram(
    xknx,
    group_address,
    value
):
    dpt = DPTScaling.to_knx(value)
    await send_telegram(xknx, group_address, dpt)


async def send_telegram(
    xknx,
    group_address,  
    dpt
):
    await xknx.telegrams.put(
        Telegram(
            destination_address=GroupAddress(group_address),
            payload=GroupValueWrite(dpt),
        )
    )


async def send_switch_telegram(xknx, relay_state, group_address):
    print(f"Sending relay state update to {group_address}: {relay_state}")
    dpt = DPTSwitch.to_knx(relay_state)
    await send_telegram(xknx, group_address, dpt)


async def send_occupancy_telegram(xknx, relay_state, group_address):
    print(f"Sending occupancy state update to {group_address}: {relay_state}")
    dpt = DPTOccupancy.to_knx(relay_state)
    await send_telegram(xknx, group_address, dpt)


async def send_power_data(
    delay,
    gateway_ip,
    gateway_port,
    inj_sout_power_address,
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

    # Relais virtuel KNX : écoute sur 15/1/1, retour d’état sur 15/1/2
    def relay_listener(telegram):
        if telegram.destination_address == GroupAddress(json_status["switch"]["group_address"]) and isinstance(telegram.payload, GroupValueWrite):
            value = telegram.payload.value.value
            print(f"Relay command received value: {value}") 
            switch_state = bool(value)
            json_status["switch"]["state"] = switch_state
            print(f"Switch state changed to {switch_state}, sending update to {json_status['switch']['state_group_address']}")
            asyncio.create_task(send_switch_telegram(xknx, switch_state, json_status['switch']['state_group_address']))

    # Ajoute le listener à xknx
    xknx.telegram_queue.register_telegram_received_cb(relay_listener)

    def volet_up_down_listener(telegram):
        if telegram.destination_address == GroupAddress(json_status["volet"]["up_down_group_address"]) and isinstance(telegram.payload, GroupValueWrite):
            knx_value = telegram.payload.value.value
            print(f"Volet up/down command received value: {knx_value}")
            if int(knx_value) == 0:
                print("Volet up command received")
                volet.monter()
            else:
                print("Volet down command received")
                volet.descendre()

    xknx.telegram_queue.register_telegram_received_cb(volet_up_down_listener)

    def volet_stop_listener(telegram):
        if telegram.destination_address == GroupAddress(json_status["volet"]["stop_group_address"]) and isinstance(telegram.payload, GroupValueWrite):
            print("Volet stop command received")
            volet.stop()
            position = volet.get_position()
            print(f"Volet position statusd: {position}%")
            json_status["volet"]["position"] = position
            print(f"Volet position changed to {position}%, sending update to {json_status['volet']['position_group_address']}")
            asyncio.create_task(send_position_telegram(xknx, json_status['volet']['position_group_address'], position))

    xknx.telegram_queue.register_telegram_received_cb(volet_stop_listener)

    def volet_position_listener(telegram):
        if telegram.destination_address == GroupAddress(json_status["volet"]["setposition_group_address"]) and isinstance(telegram.payload, GroupValueWrite):
            raw = telegram.payload.value.value
            position = int(raw[0] * 100 / 255)
            print(f"Volet position command received: {position}%")
            volet.set_position(position)
            json_status["volet"]["position"] = position
            print(f"Volet position changed to {position}%, sending update to {json_status['volet']['position_group_address']}")
            # Envoie la position réelle du volet encodée en DPTScaling
            asyncio.create_task(send_position_telegram(xknx, json_status['volet']['position_group_address'], position))

    xknx.telegram_queue.register_telegram_received_cb(volet_position_listener)


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
                inj_sout_power = -inj_w if inj_w else sout_w
                knx_messages_log += f"Simu prod:  {round(production_W, 2)}W({round(production_wh, 2)}Wh)\n"
                knx_messages_log += f"Simu conso: {round(conso_w, 2)}W({round(conso_wh, 2)}Wh)\n"
                knx_messages_log += f"Simu Injection: {round(inj_w, 2)}W({round(inj_wh, 2)}Wh), Soutirage: {round(sout_w, 2)}W - {round(sout_wh, 2)}Wh\n"
                knx_messages_log += f"Meteo: clouds={myclouds  *100}%, temp={temperature}C, humidity={humidity}%, pressure={pressure}hPa\n"
                
                # Update history
                update_history(json_status["history"]["production"], int(production_W))
                update_history(json_status["history"]["injection"], int(-inj_w))
                update_history(json_status["history"]["soutirage"], int(sout_w))
                
                json_status["inj_sout"]["W"]["value"] = int(-inj_w) if inj_w else int(sout_w)
                json_status["production"]["W"]["value"] = int(production_W)
                json_status["production"]["Wh"]["value"] = int(prod_index)
                json_status["consommation"]["W"]["value"] = int(conso_w)
                json_status["consommation"]["Wh"]["value"] = int(conso_index)
                json_status["injection"]["Wh"]["value"] = int(inj_index)
                json_status["injection"]["W"]["value"] = int(abs(inj_w))
                json_status["soutirage"]["Wh"]["value"] = int(sout_index)
                json_status["soutirage"]["W"]["value"] = int(sout_w)
                json_status["meteo"]["pressure"]["value"] = pressure
                json_status["meteo"]["temperature"]["value"] = temperature
                json_status["meteo"]["humidity"]["value"] = humidity
                json_status["updated"] = datetime.now().isoformat()


                # occupancy detection
                occupancy_state = False
                if conso_w < (household_power * 0.1):
                    occupancy_state = False
                else:
                    occupancy_state = True
                json_status["occupancy"]["state"] = occupancy_state
                knx_messages_log += f"Send PRESENCE {occupancy_state} to group={json_status['occupancy']['group_address']}\n"
                await send_occupancy_telegram(xknx, json_status["occupancy"]["group_address"], occupancy_state)

                # Send inj-sout data to KNX
                knx_messages_log += f"Send INJ-SOUT {int(inj_sout_power)}W to group={inj_sout_power_address}\n"
                await send_power_telegram(xknx, inj_sout_power_address, inj_sout_power)

                # Send prod data to KNX
                knx_messages_log += f"Send PROD {int(production_W)}W to group={prod_power_address} and {int(prod_index)}Wh to group={prod_energy_address}\n"
                await send_energy_telegram(xknx, prod_energy_address, prod_index)
                await send_power_telegram(xknx, prod_power_address, production_W)

                # Send conso data to KNX
                knx_messages_log += f"Send CONSO {int(conso_w)}W to group={conso_power_address} and {int(conso_index)}Wh to group={conso_energy_address}\n"
                await send_energy_telegram(xknx, conso_energy_address, conso_index)
                await send_power_telegram(xknx, conso_power_address, conso_w)

                # Send injection data to KNX
                knx_messages_log += f"Send INJ {int(inj_w)}W to group={inj_power_address} and {int(inj_index)}Wh to group={inj_energy_address}\n"
                await send_energy_telegram(xknx, inj_energy_address, inj_index)
                await send_power_telegram(xknx, inj_power_address, inj_w)

                # Send soutirage data to KNX
                knx_messages_log += f"Send SOUT {int(sout_w)}W to group={sout_power_address} and {int(sout_index)}Wh to group={sout_energy_address}\n"
                await send_energy_telegram(xknx, sout_energy_address, sout_index)
                await send_power_telegram(xknx, sout_power_address, sout_w)

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
    global json_status
    print(f"Loading config from {config_file}")
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file {config_file} not found")
    config.read(config_file)
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
        "inj_sout_power_group": config.get("KNX", "inj_sout_power_group"),
        "conso_power_group": config.get("KNX", "conso_power_group"),
        "conso_energy_group": config.get("KNX", "conso_energy_group"),
        "prod_power_group": config.get("KNX", "prod_power_group"),
        "prod_energy_group": config.get("KNX", "prod_energy_group"),
        "inj_energy_group": config.get("KNX", "inj_energy_group"),
        "inj_power_group": config.get("KNX", "inj_power_group"),
        "sout_energy_group": config.get("KNX", "sout_energy_group"),
        "sout_power_group": config.get("KNX", "sout_power_group"),
        "pressure_group": config.get("KNX", "pressure_group"),
        "temperature_group": config.get("KNX", "temperature_group"),
        "humidity_group": config.get("KNX", "humidity_group"),
        "switch_group": config.get("KNX", "switch_group", fallback="7/1/1"),
        "switch_state_group": config.get("KNX", "switch_state_group", fallback="7/1/2"),
        "volet_up_down_group_address": config.get("KNX", "volet_up_down_group_address", fallback="7/1/3"),
        "volet_stop_group_address": config.get("KNX", "volet_stop_group_address", fallback="7/1/4"),
        "volet_setposition_group_address": config.get("KNX", "volet_setposition_group_address", fallback="7/1/5"),
        "volet_position_group_address": config.get("KNX", "volet_position_group_address", fallback="7/1/6")
    }

    json_status["inj_sout"]["W"]["group_address"] = config.get("KNX", "inj_sout_power_group")
    json_status["production"]["W"]["group_address"] = config.get("KNX", "prod_power_group")
    json_status["production"]["Wh"]["group_address"] = config.get("KNX", "prod_energy_group")
    json_status["consommation"]["W"]["group_address"] = config.get("KNX", "conso_power_group")
    json_status["consommation"]["Wh"]["group_address"] = config.get("KNX", "conso_energy_group")
    json_status["injection"]["Wh"]["group_address"] = config.get("KNX", "inj_energy_group")
    json_status["injection"]["W"]["group_address"] = config.get("KNX", "inj_power_group")
    json_status["soutirage"]["Wh"]["group_address"] = config.get("KNX", "sout_energy_group")
    json_status["soutirage"]["W"]["group_address"] = config.get("KNX", "sout_power_group")
    json_status["meteo"]["pressure"]["group_address"] = config.get("KNX", "pressure_group")
    json_status["meteo"]["temperature"]["group_address"] = config.get("KNX", "temperature_group")
    json_status["meteo"]["humidity"]["group_address"] = config.get("KNX", "humidity_group")
    json_status["switch"]["group_address"] = config.get("KNX", "switch_group", fallback="7/1/1")
    json_status["switch"]["state_group_address"] = config.get("KNX", "switch_state_group", fallback="7/1/2")
    json_status["volet"]["up_down_group_address"] = config.get("KNX", "volet_up_down_group_address", fallback="7/1/3")
    json_status["volet"]["stop_group_address"] = config.get("KNX", "volet_stop_group_address", fallback="7/1/4")
    json_status["volet"]["setposition_group_address"] = config.get("KNX", "volet_setposition_group_address", fallback="7/1/5")
    json_status["volet"]["position_group_address"] = config.get("KNX", "volet_position_group_address", fallback="7/1/6")
    json_status["occupancy"]["group_address"] = config.get("KNX", "occupancy_group", fallback="8/1/1")
    json_status["updated"] = datetime.now().isoformat()
    json_status["longitude"] = lon
    json_status["latitude"] = lat
    json_status["panel_power"] = panel_power
    json_status["household_power"] = household_power
    json_status["ipaddress"] = get_local_ip()

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
        filename="cyclic_send_toknx_pv_data.log",
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
    try:
        publish_upnp_service(get_local_ip(), 8080)
    except Exception as e:
        print(f"Error publishing UPnP service: {e}")
    asyncio.run(
        send_power_data(
            inj_sout_power_address=conf["knx"]["inj_sout_power_group"],
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
