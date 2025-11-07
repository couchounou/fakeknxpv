
from datetime import timedelta
import random
from datetime import datetime
import configparser
import socket
import logging
import socketserver
import os
import asyncio
import json
import threading
import http.server
from xknx import XKNX
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
    DPTVolume,
    DPTVolumeFlux
)
from xknx.telegram.apci import GroupValueWrite
from pv_data import get_pv_data
from conso_data import get_conso_data
from meteo_data import get_meteo_data
from devices import volet


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


def run_simple_http_server(port=80):
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
                self.wfile.write(json.dumps(jstatus).encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = os.path.join(basepath, "html", "view.html")
                with open(html, "r", encoding="utf-8") as my_file:
                    self.wfile.write(my_file.read().encode("utf-8"))

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving HTTP on port {port}...")
        httpd.serve_forever()


jstatus = {
    "version": "0.4.0",
    "updated": "",
    "inj_sout": {
        "W": {"group_address": "", "value": 0},
    },
    "injection": {
        "W": {"group_address": "", "value": 0},
        "Wh": {"group_address": "", "value": 0}
    },
    "soutirage": {
        "W": {"group_address": "", "value": 0},
        "Wh": {"group_address": "", "value": 0}
    },
    "consommation": {
        "W": {"group_address": "", "value": 0},
        "Wh": {"group_address": "", "value": 0}
    },
    "production": {
        "W": {"group_address": "", "value": 0},
        "Wh": {"group_address": "", "value": 0}
    },
    "eau": {
        "index": {"group_address": "", "value": 0},
        "debit": {"group_address": "", "value": 0}
    },
    "meteo": {
        "temperature": {},
        "humidity": {},
        "pressure": {},
        "clouds": {}
    },
    "switch": {
        "group_address": "",
        "state_group_address": "",
        "state": False
    },
    "volet": {
        "up_down_group_address": "",
        "stop_group_address": "",
        "setposition_group_address": "",
        "position_group_address": ""
        },
    "occupancy": {
        "group_address": "",
        "state_group_address": "",
        "state": False
    },
    "history": {
        "production": [],
        "injection": [],
        "soutirage": [],
        "occupancy": [],
        "switch": []
    },
    "gateway": {
        "ip": "",
        "port": 3671
    },
    "send_cycle_s": 300,
    "save_cycle_s": 3600

}

volet = volet()

last_updated_timestamp = last_saved_timestamp = datetime.now().timestamp()
basepath = os.path.abspath(os.path.dirname(__file__))
knx_messages_log = ""


# try use default raspberry config path
# create config dir if not exists
# else use local path

index_file_path = (
    "/boot/firmware/indexes.json"
    if os.path.exists("/boot/firmware/")
    else os.path.join(basepath, "indexes.json")
)
history_file_path = (
    "/boot/firmware/history.json"
    if os.path.exists("/boot/firmware/")
    else os.path.join(basepath, "history.json")
)
config_file = (
    "/boot/firmware/cyclic_send_toknx_pv_data.cfg"
    if os.path.exists("/boot/firmware/cyclic_send_toknx_pv_data.cfg")
    else os.path.join(basepath, "cyclic_send_toknx_pv_data.cfg")
)
print(
    f"Using files: \n {index_file_path}\n {history_file_path}\n {config_file=}"
)

# create index files if not exists and read values
if os.path.exists(history_file_path):
    with open(history_file_path, "r", encoding="UTF-8") as myfile:
        try:
            jstatus['history'] = json.loads(myfile.read())
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON from history file")
            jstatus['history'] = {}

if os.path.exists(index_file_path):
    with open(index_file_path, "r", encoding="UTF-8") as myfile:
        data = json.load(myfile)
        jstatus["soutirage"]["Wh"]["value"] = data.get('sout_index', 0.0)
        jstatus["consommation"]["Wh"]["value"] = data.get('conso_index', 0.0)
        jstatus["production"]["Wh"]["value"] = data.get('prod_index', 0.0)
        jstatus["injection"]["Wh"]["value"] = data.get('inj_index', 0.0)
        jstatus["eau"]["index"]["value"] = data.get('eau_index', 0.0)


def update_history(history, key, value, max_hours=48):
    now = datetime.now().isoformat()
    if key not in history:
        history[key] = []
    history[key].append({"timestamp": now, "value": value})
    # Supprime les entrées de plus de 48h
    cutoff = datetime.now() - timedelta(hours=max_hours)
    # On garde uniquement les entrées récentes
    history[key][:] = [item for item in history[key] if datetime.fromisoformat(item["timestamp"]) >= cutoff]


def encode_dpt16(text: str) -> bytes:
    my_data = text.encode("latin-1")[:14]
    return my_data.ljust(14, b'\x00')


def save_indexes(save_cycle_s):
    logging.info("try Saving indexes to files...with last_saved_timestamp=%s", last_saved_timestamp)
    if last_saved_timestamp < datetime.now().timestamp() - save_cycle_s:
        with open(history_file_path, "w", encoding="UTF-8") as my_file:
            logging.info("  Saving history to %s", history_file_path)
            json.dump(jstatus["history"], my_file, ensure_ascii=False)
        with open(index_file_path, "w", encoding="UTF-8") as my_file:
            obj = {
                "inj_index": jstatus["injection"]["Wh"]["value"],
                "sout_index": jstatus["soutirage"]["Wh"]["value"],
                "conso_index": jstatus["consommation"]["Wh"]["value"],
                "prod_index": jstatus["production"]["Wh"]["value"],
                "eau_index": jstatus["eau"]["index"]["value"]
            }
            json.dump(obj, my_file, ensure_ascii=False)
            logging.info("  Saving index to %s", index_file_path)
        try:
            publish_upnp_service(get_local_ip(), 8080)
        except Exception as e:
            print(f"Error publishing UPnP service: {e}")
            logging.error(f"Error publishing UPnP service: {e}")
        return datetime.now().timestamp()
    return last_saved_timestamp


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
    logging.info("Inj power %sW diff inj_index:%sWh, Sout power:%sW diff sout_index:%sWh", inj_power, diff_inj_index, sout_power, diff_sout_index)
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


async def send_flux_telegram(
    xknx,
    group_address,
    value
):
    dpt = DPTVolumeFlux.to_knx(value)
    await send_telegram(xknx, group_address, dpt)


async def send_volume_telegram(
    xknx,
    group_address,
    value
):
    dpt = DPTVolume.to_knx(value)
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


async def send_occupancy_telegram(xknx, state, group_address):
    print(f"Sending occupancy state update to {group_address}: {state}")
    dpt = DPTBinary(1) if state else DPTBinary(0)
    await send_telegram(xknx, group_address, dpt)


async def send_cyclic_data(global_obj):

    # Configuration XKNX
    connection_config = ConnectionConfig(
        connection_type=ConnectionType.TUNNELING,
        gateway_ip=global_obj["gateway"]["ip"],
        gateway_port=global_obj["gateway"]["port"],
    )
    print(f"XKNX connecting to {global_obj['gateway']['ip']}:{global_obj['gateway']['port']}")
    xknx = XKNX(connection_config=connection_config)
    print("XKNX starting...")
    await xknx.start()
    print("XKNX started")

    global last_updated_timestamp, last_saved_timestamp
 
    def relay_listener(telegram):
        if (
            telegram.destination_address == GroupAddress(global_obj["switch"]["group_address"]) and
            isinstance(telegram.payload, GroupValueWrite)
        ):
            value = telegram.payload.value.value
            print(f"Relay command received value: {value}")
            switch_state = bool(value)
            global_obj["switch"]["state"] = switch_state
            print(
                f"Switch state changed to {switch_state}, "
                f"sending update to {global_obj['switch']['state_group_address']}"
            )
            asyncio.create_task(
                send_switch_telegram(
                    xknx,
                    switch_state,
                    global_obj['switch']['state_group_address']
                )
            )

    # Ajoute le listener à xknx
    xknx.telegram_queue.register_telegram_received_cb(relay_listener)

    def volet_up_down_listener(telegram):
        if (
            telegram.destination_address == GroupAddress(global_obj["volet"]["up_down_group_address"]) and
            isinstance(telegram.payload, GroupValueWrite)
        ):
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
        if (
            telegram.destination_address == GroupAddress(global_obj["volet"]["stop_group_address"]) and
            isinstance(telegram.payload, GroupValueWrite)
        ):
            print("Volet stop command received")
            volet.stop()
            position = volet.get_position()
            print(f"Volet position statusd: {position}%")
            global_obj["volet"]["position"] = position
            print(
                f"Volet position changed to {position}%, " 
                f"sending update to {global_obj['volet']['position_group_address']}"
            )
            asyncio.create_task(
                send_position_telegram(
                    xknx,
                    global_obj['volet']['position_group_address'],
                    position
                )
            )

    xknx.telegram_queue.register_telegram_received_cb(volet_stop_listener)

    def volet_position_listener(telegram):
        if (
            telegram.destination_address == GroupAddress(global_obj["volet"]["setposition_group_address"]) and
            isinstance(telegram.payload, GroupValueWrite)
        ):
            raw = telegram.payload.value.value
            position = int(raw[0] * 100 / 255)
            print(f"Volet position command received: {position}%")
            volet.set_position(position)
            global_obj["volet"]["position"] = position
            print(
                f"Volet position changed to {position}%, "
                f"sending update to {global_obj['volet']['position_group_address']}"
            )
            # Envoie la position réelle du volet encodée en DPTScaling
            asyncio.create_task(
                send_position_telegram(
                    xknx,
                    global_obj['volet']['position_group_address'],
                    position
                )
            )

    xknx.telegram_queue.register_telegram_received_cb(volet_position_listener)
    global_obj['switch']['last_action_time'] = datetime.now().isoformat()

    try:
        while True:
            try:
                myclouds, temperature, humidity, pressure = get_meteo_data.get_meteo_data(
                    lat=global_obj.get("latitude", 48.8566),
                    lon=global_obj.get("longitude", 2.3522),
                    api_key=global_obj.get("weather_api_key")
                )

                production_W, production_wh, _, _ = get_pv_data.get_pv_data(
                    latitude=global_obj.get("latitude", 48.8566),
                    longitude=global_obj.get("longitude", 2.3522),
                    power=global_obj.get("panel_power", 4000),
                    updated_timestamp=last_updated_timestamp,
                    myclouds=myclouds
                )

                conso_w, conso_wh = get_conso_data.get_conso_data(
                    power=global_obj.get("household_power", 0),
                    updated_timestamp=last_updated_timestamp
                )

                inj_w, inj_wh, sout_w, sout_wh = get_inj_data(
                    conso_w,
                    production_W,
                    updated_timestamp=last_updated_timestamp
                )

                myclouds = 0.8 if myclouds is None else myclouds
                last_updated_timestamp = datetime.now().timestamp()
                global_obj["injection"]["Wh"]["value"] += inj_wh
                global_obj["soutirage"]["Wh"]["value"] += sout_wh
                global_obj["consommation"]["Wh"]["value"] += conso_wh
                global_obj["production"]["Wh"]["value"] += production_wh
                inj_sout_power = -inj_w if inj_w else sout_w
                logging.info(
                    "Simu prod:  %.2fW(%.2fWh)",
                    round(production_W, 2), round(production_wh, 2)
                )
                logging.info(
                    "Simu conso: %.2fW(%.2fWh)",
                    round(conso_w, 2), round(conso_wh, 2)
                )
                logging.info(
                    "Simu Injection: %.2fW(%.2fWh), Soutirage: %.2fW - %.2fWh",
                    round(inj_w, 2), round(inj_wh, 2), round(sout_w, 2), round(sout_wh, 2)
                )
                logging.info(
                    "Meteo: clouds=%s%%, temp=%sC, humidity=%s%%, pressure=%shPa",
                    myclouds * 100, temperature, humidity, pressure
                )

                # Update history
                update_history(global_obj["history"], "production", int(production_W))
                update_history(global_obj["history"], "injection", int(-inj_w))
                update_history(global_obj["history"], "soutirage", int(sout_w))

                global_obj["inj_sout"]["W"]["value"] = int(-inj_w) if inj_w else int(sout_w)
                global_obj["production"]["W"]["value"] = int(production_W)
                global_obj["consommation"]["W"]["value"] = int(conso_w)
                global_obj["injection"]["W"]["value"] = int(abs(inj_w))
                global_obj["soutirage"]["W"]["value"] = int(sout_w)
                global_obj["meteo"]["pressure"]["value"] = pressure
                global_obj["meteo"]["temperature"]["value"] = temperature
                global_obj["meteo"]["humidity"]["value"] = humidity
                global_obj["meteo"]["clouds"]["value"] = myclouds * 100
                global_obj["updated"] = datetime.now().isoformat()
                if datetime.fromisoformat(global_obj["switch"].get("last_action_time", datetime.now().isoformat())) < (
                    datetime.now() - timedelta(minutes=12)
                ):
                    global_obj["switch"]["state"] = not global_obj["switch"].get("state", False)
                    global_obj["switch"]["last_action_time"] = datetime.now().isoformat()
                    logging.info(
                        "Change switch state to %s",
                        global_obj["switch"]["state"]
                    )
                    await send_switch_telegram(
                        xknx, False, global_obj["switch"]["state_group_address"]
                    )
                logging.info(
                    "Switch state is now %s",
                    global_obj["switch"].get("state", False)
                )

                update_history(global_obj["history"], "switch", int(global_obj["switch"].get("state", False)))

                # occupancy detection
                occupancy_state = False
                if conso_w < (global_obj["household_power"] * 0.05):
                    occupancy_state = False
                else:
                    occupancy_state = True
                global_obj["occupancy"]["state"] = occupancy_state
                update_history(global_obj["history"], "occupancy", occupancy_state)
                logging.info(
                    "Set presence to %s to group=%s",
                    occupancy_state,
                    global_obj['occupancy']['group_address']
                )
                await send_occupancy_telegram(
                    xknx, global_obj["occupancy"]["group_address"], occupancy_state
                )

                # volet status
                now = datetime.now()
                global_obj["volet"]["last_action_time"] = datetime.now().isoformat()
                global_obj["volet"]["position"] = (
                    0 if now.hour < 7 or (now.hour == 7 and now.minute < 30) or now.hour >= 22
                    else random.randint(80, 100)
                )
                logging.info(
                    "Volet position status: %d",
                    global_obj['volet']['position']
                )
                await send_position_telegram(
                    xknx, global_obj['volet']['position_group_address'],
                    global_obj['volet']['position']
                )

                # Send water meter data to KNX
                debit, volume = get_conso_data.get_water_meter_m3()
                global_obj["eau"]["debit"]["value"] = round(debit, 6)
                global_obj["eau"]["index"]["value"] += round(volume, 6)
                logging.info(
                    "Send EAU index %sm3 to group=%s and debit %sm3/h to group=%s",
                    global_obj['eau'].get('index', {}).get('value', 0),
                    global_obj['eau'].get('index', {}).get('group_address', ''),
                    global_obj['eau'].get('debit', {}).get('value', 0),
                    global_obj['eau'].get('debit', {}).get('group_address', '')
                )
                await send_volume_telegram(
                    xknx,
                    global_obj['eau']['index']['group_address'],
                    global_obj["eau"]["index"]["value"]
                )
                await send_flux_telegram(
                    xknx,
                    global_obj['eau']['debit']['group_address'],
                    global_obj["eau"]["debit"]["value"]
                )

                # Send inj-sout data to KNX
                logging.info(
                    "Send INJ-SOUT %dW to group=%s",
                    int(inj_sout_power),
                    global_obj['inj_sout']['W']['group_address']
                )
                await send_power_telegram(
                    xknx, global_obj["inj_sout"]["W"]["group_address"], inj_sout_power
                )

                # Send prod data to KNX
                logging.info(
                    "Send PROD %dW to group=%s and %dWh to group=%s",
                    int(production_W),
                    global_obj['production']['W']['group_address'],
                    int(global_obj['production']['Wh']['value']),
                    global_obj['production']['Wh']['group_address']
                )
                await send_energy_telegram(
                    xknx,
                    global_obj['production']['Wh']['group_address'],
                    global_obj["production"]["Wh"]["value"]
                )
                await send_power_telegram(
                    xknx,
                    global_obj['production']['W']['group_address'],
                    production_W
                )

                # Send conso data to KNX
                logging.info(
                    "Send CONSO %dW to group=%s and %dWh to group=%s",
                    int(conso_w),
                    global_obj['consommation']['W']['group_address'],
                    int(global_obj['consommation']['Wh']['value']),
                    global_obj['consommation']['Wh']['group_address']
                )
                await send_energy_telegram(
                    xknx,
                    global_obj['consommation']['Wh']['group_address'],
                    global_obj["consommation"]["Wh"]["value"]
                )
                await send_power_telegram(
                    xknx,
                    global_obj['consommation']['W']['group_address'],
                    conso_w
                )

                # Send injection data to KNX
                logging.info(
                    "Send INJ %dW to group=%s and %dWh to group=%s",
                    int(inj_w),
                    global_obj['injection']['W']['group_address'],
                    int(global_obj['injection']['Wh']['value']),
                    global_obj['injection']['Wh']['group_address']
                )
                await send_energy_telegram(
                    xknx,
                    global_obj['injection']['Wh']['group_address'],
                    global_obj["injection"]["Wh"]["value"]
                )
                await send_power_telegram(
                    xknx,
                    global_obj['injection']['W']['group_address'],
                    inj_w
                )

                # Send soutirage data to KNX
                logging.info(
                    "Send SOUT %dW to group=%s and %dWh to group=%s",
                    int(sout_w),
                    global_obj['soutirage']['W']['group_address'],
                    int(global_obj['soutirage']['Wh']['value']),
                    global_obj['soutirage']['Wh']['group_address']
                )
                await send_energy_telegram(
                    xknx,
                    global_obj['soutirage']['Wh']['group_address'],
                    global_obj["soutirage"]["Wh"]["value"]
                )
                await send_power_telegram(
                    xknx,
                    global_obj['soutirage']['W']['group_address'],
                    sout_w
                )

                # Send meteo data to log
                logging.info(
                    "Send METEO pressure=%shPa to group=%s, temperature=%sC to group=%s, humidity=%s%% to group=%s",
                    pressure,
                    global_obj['meteo']['pressure']['group_address'],
                    temperature,
                    global_obj['meteo']['temperature']['group_address'],
                    humidity,
                    global_obj['meteo']['humidity']['group_address']
                )
                if pressure:
                    telegram = Telegram(
                        destination_address=GroupAddress(global_obj["meteo"]["pressure"]['group_address']),
                        payload=GroupValueWrite(DPTPressure2Byte.to_knx(int(pressure * 100))),
                    )
                    await xknx.telegrams.put(telegram)
                if temperature:
                    telegram = Telegram(
                        destination_address=GroupAddress(global_obj["meteo"]["temperature"]['group_address']),
                        payload=GroupValueWrite(DPTTemperature.to_knx(float(temperature))),
                    )
                    await xknx.telegrams.put(telegram)
                if humidity:
                    telegram = Telegram(
                        destination_address=GroupAddress(global_obj["meteo"]["humidity"]['group_address']),
                        payload=GroupValueWrite(DPTHumidity.to_knx(int(humidity))),
                    )
                    await xknx.telegrams.put(telegram)

                last_saved_timestamp = save_indexes(global_obj["save_cycle_s"])
                print(knx_messages_log)
                logging.info(knx_messages_log)
            except Exception as e:
                logging.info("Error in main loop: %s", e)
            await asyncio.sleep(global_obj["send_cycle_s"])
    except Exception as e:
        logging.info(e)
    finally:
        await xknx.stop()


def load_config(global_obj, config_file):
    print(f"Loading config from {config_file}")
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file {config_file} not found")
    config.read(config_file)
    print(f"Config sections: {config.sections()}")
    global_obj["gateway"]["ip"] = config.get("KNX", "gateway_ip")
    global_obj["gateway"]["port"] = config.getint("KNX", "gateway_port", fallback=3671)
    global_obj["save_cycle_s"] = config.getint("KNX", "save_cycle_s", fallback=3600)
    global_obj["send_cycle_s"] = config.getint("KNX", "send_cycle_s", fallback=300)
    global_obj["inj_sout"]["W"]["group_address"] = config.get("KNX", "inj_sout_power_group", fallback="6/1/14")
    if not global_obj["inj_sout"]["W"]["group_address"]:
        global_obj["inj_sout"]["W"]["group_address"] = "6/1/14"
    global_obj["production"]["W"]["group_address"] = config.get("KNX", "prod_power_group", fallback="6/1/11")
    global_obj["production"]["Wh"]["group_address"] = config.get("KNX", "prod_energy_group", fallback="6/2/11")
    global_obj["consommation"]["W"]["group_address"] = config.get("KNX", "conso_power_group", fallback="6/1/10")
    global_obj["consommation"]["Wh"]["group_address"] = config.get("KNX", "conso_energy_group", fallback="6/2/10")
    global_obj["injection"]["Wh"]["group_address"] = config.get("KNX", "inj_energy_group", fallback="6/2/12")
    global_obj["injection"]["W"]["group_address"] = config.get("KNX", "inj_power_group", fallback="6/1/12")
    global_obj["soutirage"]["Wh"]["group_address"] = config.get("KNX", "sout_energy_group", fallback="6/2/13")
    global_obj["soutirage"]["W"]["group_address"] = config.get("KNX", "sout_power_group", fallback="6/1/13")
    global_obj["meteo"]["pressure"]["group_address"] = config.get("KNX", "pressure_group", fallback="6/3/10")
    global_obj["meteo"]["temperature"]["group_address"] = config.get("KNX", "temperature_group", fallback="6/3/12")
    global_obj["meteo"]["humidity"]["group_address"] = config.get("KNX", "humidity_group", fallback="6/3/11")
    global_obj["switch"]["group_address"] = config.get("KNX", "switch_group", fallback="7/1/1")
    global_obj["switch"]["state_group_address"] = config.get("KNX", "switch_state_group", fallback="7/1/2")
    global_obj["volet"]["up_down_group_address"] = config.get("KNX", "volet_up_down_group_address", fallback="7/1/3")
    global_obj["volet"]["stop_group_address"] = config.get("KNX", "volet_stop_group_address", fallback="7/1/4")
    global_obj["volet"]["setposition_group_address"] = config.get(
        "KNX",
        "volet_setposition_group_address",
        fallback="7/1/5"
    )
    global_obj["volet"]["position_group_address"] = config.get("KNX", "volet_position_group_address", fallback="7/1/6")
    global_obj["occupancy"]["group_address"] = config.get("KNX", "occupancy_group", fallback="8/1/1")
    global_obj["eau"]["index"]["group_address"] = config.get("KNX", "eau_index_group", fallback="9/1/1")
    global_obj["eau"]["debit"]["group_address"] = config.get("KNX", "eau_debit_group", fallback="9/1/2")
    global_obj["updated"] = datetime.now().isoformat()
    global_obj["longitude"] = config.getfloat("CONFIG", "lon")
    global_obj["latitude"] = config.getfloat("CONFIG", "lat")
    global_obj["panel_power"] = config.getint("CONFIG", "panel_power")
    global_obj["household_power"] = config.getint("CONFIG", "household_power")
    global_obj["ipaddress"] = get_local_ip()
    global_obj["weather_api_key"] = config.get("OPENWEATHERMAP", "api_key", fallback=None)


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
        print("⚠ No Gateways found")


if __name__ == "__main__":
    load_config(jstatus, config_file)
    logging.basicConfig(
        filename="cyclic_send_toknx_pv_data.log",
        filemode="a",
        format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    threading.Thread(
        target=run_simple_http_server,
        args=(8080,),
        daemon=True
    ).start()
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="UTF-8") as myfile:
            jstatus["version"] = myfile.read().strip()
    else:
        jstatus["version"] = "Unknown"
    try:
        publish_upnp_service(get_local_ip(), 8080)
    except Exception as e:
        print(f"Error publishing UPnP service: {e}")
    asyncio.run(
        send_cyclic_data(jstatus)
    )
