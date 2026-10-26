"""Publish budget figures as Home Assistant sensors through the Supervisor API.

Only available when running as an add-on (SUPERVISOR_TOKEN set, homeassistant_api: true).
States set through the REST API are not restored by Home Assistant after a restart, so they
are re-published periodically as well as after every change in the web UI.
"""

import json
import logging
import re
import threading
import urllib.request
from datetime import datetime

import database as db
from app_types import Account
from budget import hidden_categories, main_value, monthly_balances, visible_subs

log = logging.getLogger(__name__)

_TRANSLITERATE = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower().translate(_TRANSLITERATE)).strip("_")


def account_states(database_path: str, account: Account, currency: str = "SEK",
                   now: datetime | None = None) -> dict[str, dict]:
    """The sensors for one account as {entity_id: {"state": ..., "attributes": {...}}}."""
    now = now or datetime.now()
    prefix = f"sensor.economics_{slugify(account.name)}"

    this_year = monthly_balances(database_path, account, now.year)
    current = this_year[now.month]
    if now.month > 1:
        previous = this_year[now.month - 1]
    else:
        previous = monthly_balances(database_path, account, now.year - 1, [12])[12]

    hidden = hidden_categories(db.get_categories(database_path, account.id))

    states: dict[str, dict] = {}
    for main in current.categories():
        subs = visible_subs(current, main, hidden)
        if not subs:  # hidden from the budget
            continue
        value = main_value(current, main, hidden)
        states[f"{prefix}_{slugify(main)}"] = {
            "state": round(value, 2),
            "attributes": {
                "friendly_name": f"{account.name} {main.capitalize()}",
                "unit_of_measurement": currency,
                "device_class": "monetary",
                "state_class": "total",
                "icon": "mdi:cash",
                "account": account.name,
                "month": now.strftime("%Y-%m"),
                "previous_month": round(main_value(previous, main, hidden), 2),
                "year_to_date": round(sum(main_value(b, main, hidden)
                                          for m, b in this_year.items() if m <= now.month), 2),
                "sub_categories": {sub: round(current.get_sub_category(main, sub), 2)
                                   for sub in subs},
            },
        }

    states[f"{prefix}_unclassified"] = {
        "state": db.count_unclassified_transactions(database_path, account.id),
        "attributes": {
            "friendly_name": f"{account.name} unclassified transactions",
            "icon": "mdi:tag-off-outline",
            "account": account.name,
        },
    }

    latest = db.latest_transaction_date(database_path, account.id)
    states[f"{prefix}_latest_transaction"] = {
        "state": latest or "unknown",
        "attributes": {
            "friendly_name": f"{account.name} latest transaction",
            "device_class": "date",
            "icon": "mdi:calendar-check",
            "account": account.name,
        },
    }
    return states


def all_states(database_path: str, currency: str = "SEK",
               now: datetime | None = None) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for account in db.get_accounts(database_path):
        states.update(account_states(database_path, account, currency, now))
    return states


class SensorPublisher:
    def __init__(self, database_path: str, token: str, interval_minutes: int = 15,
                 currency: str = "SEK", base_url: str = "http://supervisor/core/api",
                 debounce_seconds: float = 5):
        self.database_path = database_path
        self.token = token
        self.interval = max(1, interval_minutes) * 60
        self.currency = currency
        self.base_url = base_url.rstrip("/")
        self.debounce = debounce_seconds
        self._wake = threading.Event()

    def _post(self, entity_id: str, payload: dict):
        request = urllib.request.Request(
            f"{self.base_url}/states/{entity_id}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()

    def publish(self):
        try:
            states = all_states(self.database_path, self.currency)
        except Exception:
            log.exception("Could not calculate sensor states")
            return
        failed = 0
        for entity_id, payload in states.items():
            try:
                self._post(entity_id, payload)
            except Exception as e:
                failed += 1
                log.debug("Publishing %s failed: %s", entity_id, e)
        if failed:
            log.warning("Could not publish %d of %d sensors to Home Assistant", failed, len(states))
        else:
            log.info("Published %d sensors to Home Assistant", len(states))

    def notify(self):
        """Ask for a publish soon, e.g. after data changed."""
        self._wake.set()

    def _run(self):
        while True:
            self.publish()
            woken = self._wake.wait(self.interval)
            # Wait for a quiet moment so a burst of edits leads to a single publish.
            while woken:
                self._wake.clear()
                woken = self._wake.wait(self.debounce)

    def start(self):
        threading.Thread(target=self._run, name="ha-sensors", daemon=True).start()
