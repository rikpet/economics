"""Entry point for the Home Assistant add-on.

Reads the add-on options from /data/options.json, starts the HA sensor publisher and serves
the web interface on the Ingress port.
"""

import json
import logging
import os

from waitress import serve

from ha_sensors import SensorPublisher
from webapp import create_app

OPTIONS_PATH = "/data/options.json"
INGRESS_PORT = 8100  # must match ingress_port in config.yaml

log = logging.getLogger("economics")


def load_options(path: str = OPTIONS_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def main():
    options = load_options()
    logging.basicConfig(level=str(options.get("log_level", "info")).upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    database_path = options.get("database_path") or "/data/economics.db"
    log.info("Using database %s", database_path)

    on_change = None
    token = os.environ.get("SUPERVISOR_TOKEN")
    if options.get("publish_sensors", True):
        if token:
            publisher = SensorPublisher(
                database_path,
                token,
                interval_minutes=int(options.get("sensor_interval", 15)),
                currency=options.get("currency", "SEK"),
            )
            on_change = publisher.notify
        else:
            log.warning("SUPERVISOR_TOKEN is not set; Home Assistant sensors are disabled")

    app = create_app(database_path, on_change=on_change)
    if on_change:
        publisher.start()

    port = INGRESS_PORT
    log.info("Serving web interface on port %d", port)
    serve(app, host="0.0.0.0", port=port, threads=4, ident="economics")


if __name__ == "__main__":
    main()
