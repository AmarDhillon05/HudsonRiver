from dealalert import watchlist
from dealalert.watchlist import matches

WL = watchlist.load()
ITEMS = {i.id: i for i in WL.items}


def test_shipped_watchlist_loads():
    assert set(ITEMS) == {"x1-carbon-gen14", "elitebook-x-g1a", "p14s-gen6-amd"}
    assert all(i.target > 0 for i in WL.items)


def test_x1_carbon_matches_only_gen_14():
    x1 = ITEMS["x1-carbon-gen14"]
    assert matches(x1, "Lenovo ThinkPad X1 Carbon Gen 14 Aura: 14\" 2.8K OLED, Ultra 7 356H $1,499", WL.exclude)
    assert not matches(x1, "Lenovo ThinkPad X1 Carbon G13: 14\" 2.8K OLED 120Hz $1385", WL.exclude)
    assert not matches(x1, "Lenovo ThinkPad X1 Carbon Gen 10 21CB00BVUS 14\" Touchscreen", WL.exclude)
    assert not matches(x1, "ASUS ROG Zephyrus G14 RTX 5070 $1,299", WL.exclude)


def test_p14s_requires_amd():
    p14s = ITEMS["p14s-gen6-amd"]
    assert matches(p14s, "ThinkPad P14s Gen 6 AMD Ryzen AI 9 HX PRO 370 32GB $1,249", WL.exclude)
    assert not matches(p14s, "Lenovo ThinkPad P14s Gen 6 21QT006WUS - Intel Core Ultra 7 255H - 32GB", WL.exclude)


def test_excludes_refurbished_and_expired():
    g1a = ITEMS["elitebook-x-g1a"]
    assert matches(g1a, "HP EliteBook X G1a 14\" Ryzen AI 9 HX 375 $1,199", WL.exclude)
    assert not matches(g1a, "Refurb: HP EliteBook X G1a 14\" Ryzen AI 9 $899", WL.exclude)
    assert not matches(g1a, "[Expired] HP EliteBook X G1a 14\" $999", WL.exclude)


def test_terms_respect_word_boundaries():
    p14s = ITEMS["p14s-gen6-amd"]
    assert not matches(p14s, "ThinkPad P14s G60 AMD", WL.exclude)
    # "used" must not knock out "focused".
    assert matches(ITEMS["elitebook-x-g1a"], "Business-focused HP EliteBook X G1a $1,100", WL.exclude)


def test_excludes_reconditioned_and_scratch_and_dent():
    g1a = ITEMS["elitebook-x-g1a"]
    assert not matches(g1a, "HP Elitebook X G1a 14\" Ryzen AI 9 HX Pro 375, 32GB (Factory Reconditioned) $975.99", WL.exclude)
    assert not matches(g1a, "HP EliteBook X G1a (S&D): 14\" OLED $899", WL.exclude)


def test_generation_spellings():
    x1 = ITEMS["x1-carbon-gen14"]
    for title in ("ThinkPad X1 Carbon 14th Gen $1,499", "X1 Carbon Gen14 Aura $1,499",
                  "X1 Carbon Generation 14 $1,499", "X1 Carbon G14 $1,499"):
        assert matches(x1, title, WL.exclude), title
    assert not matches(x1, "X1 Carbon Gen 1 $499", WL.exclude)
    assert not matches(x1, "X1 Carbon 13th Gen $1,299", WL.exclude)
