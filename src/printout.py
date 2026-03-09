from datetime import datetime
from tabulate import tabulate


class Color:
    red = "\033[91m"
    green = "\033[92m"
    yellow = "\033[93m"
    blue = "\033[94m"
    magenta = "\033[95m"
    cyan = "\033[96m"
    reset = "\033[0m"

color = Color()

def generate_table(header, rows) -> str:
    return tabulate(rows, headers=header)
