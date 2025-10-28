import os
import asyncio
from xknx import XKNX as XKNX
import logging
from xknx.telegram import GroupAddress, Telegram
from xknx.io import ConnectionConfig, ConnectionType, GatewayScanner
from xknx.dpt import DPTPower, DPTActiveEnergy
from xknx.telegram.apci import GroupValueWrite
from datetime import datetime
from pv_data import get_pv_data
from conso_data import get_conso_data
import configparser


def get_inj_data(conso: float = 0, prod: float = 0):
    inj_index_file_path = "index_inject.txt"
    sout_index_file_path = "index_sout.txt"
    updated_timestamp = datetime.now().timestamp()
    if os.path.exists(inj_index_file_path) & os.path.exists(sout_index_file_path):
        updated_timestamp = max(
            os.path.getmtime(inj_index_file_path),
            os.path.getmtime(sout_index_file_path),
        )
    else:
        with open(inj_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write("0.0")
        with open(sout_index_file_path, "w", encoding="UTF-8") as myfile:
            myfile.write("0.0")

    delta = datetime.now().timestamp() - updated_timestamp
    if delta > 3600:
        logging.warning("Trou de données... de %ss", delta)
        delta = 3600

    inj = prod - conso
    sout_power = 0
    sout_index = 0
    inj_power = 0
    inj_index = 0
    energy = abs(inj) * delta / 3600
    if inj > 0:
        inj_power = inj
        inj_index = energy
    else:
        sout_power = -inj
        sout_index = energy

    with open(inj_index_file_path, "r", encoding="UTF-8") as myfile:
        old_index = float(myfile.read())
        inj_index = old_index + inj_index
        logging.info("Inj index:%dWh, New index:%dWh", int(old_index), int(inj_index))

    with open(sout_index_file_path, "r", encoding="UTF-8") as myfile:
        old_index = float(myfile.read())
        sout_index = old_index + sout_index
        logging.info("Sout index:%dWh, New index:%dWh", int(old_index), int(sout_index))

    return inj_power, inj_index, sout_power, sout_index


async def send_power_data(
    delay,
    gateway_ip,
    gateway_port,
    power_address,
    energy_address,
    inj_power_address,
    inj_energy_address,
    sout_power_address,
    sout_energy_address,
    longitude,
    latitude,
    household_power,
    panel_power,
    weather_api_key=None,
):
    print(
        f"Start cyclic send to knxip {gateway_ip}:{gateway_port} {power_address=}, {energy_address=}, {inj_power_address=}, {inj_energy_address=}, {sout_power_address=}, {sout_energy_address=}"
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
    print("XKNX started")
    try:
        while True:
            production_W, production_wh, _, _ = get_pv_data.get_pv_data(
                latitude=latitude,
                longitude=longitude,
                power=panel_power,
                weather_api_key=weather_api_key,
            )
            print(
                f"Send PROD {int(production_W)}W to power_address={power_address} and {int(production_wh)}Wh to energy_address={energy_address}"
            )
            telegram = Telegram(
                destination_address=GroupAddress(energy_address),
                payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(production_wh))),
            )
            await xknx.telegrams.put(telegram)

            telegram = Telegram(
                destination_address=GroupAddress(power_address),
                payload=GroupValueWrite(DPTPower.to_knx(int(production_W))),
            )
            await xknx.telegrams.put(telegram)
            conso_w, conso_wh = get_conso_data.get_conso_data(power=household_power)
            inj_w, inj_wh, sout_w, sout_wh = get_inj_data(conso_w, production_W)
            print(
                f"   Simu prod:  {production_W}W({production_wh}Wh)"
            )
            print(
                f"   Simu conso: {conso_w}W({conso_wh}Wh)"
            )
            print(
                f"   Calc: Injection {inj_w}W - {inj_wh}Wh, Soutirage {sout_w}W - {sout_wh}Wh"
            )

            # Send injection data
            print(
                f"Send INJ {int(-inj_w if inj_w else 0)}W to inj_power_address={inj_power_address} and {int(inj_wh)}Wh to inj_energy_address={inj_energy_address}"
            )
            telegram = Telegram(
                destination_address=GroupAddress(inj_energy_address),
                payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(inj_wh))),
            )
            await xknx.telegrams.put(telegram)

            telegram = Telegram(
                destination_address=GroupAddress(inj_power_address),
                payload=GroupValueWrite(
                    DPTPower.to_knx(int(-inj_w if inj_w < 0 else 0))
                ),
            )
            await xknx.telegrams.put(telegram)

            # Send soutirage data
            print(
                f"Send SOUT {int(sout_w if sout_w > 0 else 0)}W to sout_power_address={sout_power_address} and {int(sout_wh)}Wh to sout_energy_address={sout_energy_address}"
            )
            telegram = Telegram(
                destination_address=GroupAddress(sout_energy_address),
                payload=GroupValueWrite(DPTActiveEnergy.to_knx(int(sout_wh))),
            )
            await xknx.telegrams.put(telegram)

            telegram = Telegram(
                destination_address=GroupAddress(sout_power_address),
                payload=GroupValueWrite(
                    DPTPower.to_knx(int(sout_w if sout_w > 0 else 0))
                ),
            )
            await xknx.telegrams.put(telegram)
            print(
                f"-> prod {int(production_W)}W - {int(production_wh)}Wh, "
                f"Injection {int(inj_w)}W - {int(inj_wh)}Wh, "
                f"Soutirage {int(sout_w)}W - {int(sout_wh)}Wh, "
                f"Conso {int(production_W - inj_w + sout_w)}W"
            )
            await asyncio.sleep(delay)  # Envoi toutes les 30 secondes
    except Exception as e:
        logging.info(e)
    finally:
        await xknx.stop()


def load_config(path="cyclic_send_toknx_pv_data.cfg"):
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
        "power_group": config.get("KNX", "power_group"),
        "energy_group": config.get("KNX", "energy_group"),
        "inj_energy_group": config.get("KNX", "inj_energy_group"),
        "inj_power_group": config.get("KNX", "inj_power_group"),
        "sout_energy_group": config.get("KNX", "sout_energy_group"),
        "sout_power_group": config.get("KNX", "sout_power_group"),
    }

    # You can return a dict, a namedtuple, or just print for now
    return {
        "lon": lon,
        "lat": lat,
        "panel_power": panel_power,
        "household_power": household_power,
        "knx": knx,
        "weather": {"api_key": config.get("WEATHER", "api_key", fallback=None)},
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
    asyncio.run(scan())
    asyncio.run(
        send_power_data(
            gateway_ip=conf["knx"]["gateway_ip"],
            gateway_port=conf["knx"]["gateway_port"],
            power_address=conf["knx"]["power_group"],
            energy_address=conf["knx"]["energy_group"],
            inj_power_address=conf["knx"]["inj_power_group"],
            inj_energy_address=conf["knx"]["inj_energy_group"],
            sout_power_address=conf["knx"]["sout_power_group"],
            sout_energy_address=conf["knx"]["sout_energy_group"],
            longitude=conf["lon"],
            latitude=conf["lat"],
            household_power=conf["household_power"],
            panel_power=conf["panel_power"],
            delay=conf["knx"]["send_cycle_s"],
            weather_api_key=conf["weather"]["api_key"],
        )
    )
