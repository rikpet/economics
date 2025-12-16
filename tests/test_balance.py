

from balance import Balance


def test_placeholder():
    balance = Balance()

    balance.add("inkomst", "månadspeng", 1000)
    assert balance.get("inkomst") == 1000