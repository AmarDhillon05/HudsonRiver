import json

from dealalert.sources import bestbuy, slickdeals

FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title><![CDATA[Lenovo ThinkPad X1 Carbon Gen 14: 14" OLED, 32GB, 1TB $1,499.99 + Free Shipping ]]></title>
    <link>https://slickdeals.net/f/123-x1-carbon?utm_source=rss&amp;utm_medium=RSS2</link>
    <pubDate>Sun, 25 Oct 2026 12:53:42 +0000</pubDate>
  </item>
  <item>
    <title>Select HP OmniBook X 14" 32GB $2249.99, 64GB $2999.99</title>
    <link>https://slickdeals.net/f/456-omnibook</link>
  </item>
  <item><title></title><link>https://slickdeals.net/f/789</link></item>
</channel></rss>"""


def test_parse_price():
    assert slickdeals.parse_price("X1 Carbon G13 $1385") == 1385
    assert slickdeals.parse_price("$1999.99 | ThinkPad T16") == 1999.99
    assert slickdeals.parse_price("now $1,849 before taxes") == 1849
    assert slickdeals.parse_price("Save $50, laptop $1,099 + $5.99 shipping") == 1099
    assert slickdeals.parse_price("ThinkPad deal, see thread") is None


def test_parse_feed_strips_tracking_and_skips_empty():
    listings = slickdeals.parse_feed(FEED)
    assert [l.url for l in listings] == ["https://slickdeals.net/f/123-x1-carbon", "https://slickdeals.net/f/456-omnibook"]
    assert listings[0].price == 1499.99
    assert listings[0].posted.year == 2026
    assert listings[1].posted is None
    assert listings[1].price == 2249.99


def test_bestbuy_parse_and_url():
    body = json.dumps({"products": [
        {"sku": 1, "name": "HP EliteBook X G1a 14\"", "salePrice": 1199.99, "regularPrice": 1599.99, "url": "https://bestbuy.com/1"},
        {"sku": 2, "name": None, "salePrice": 10, "url": "https://bestbuy.com/2"},
    ]}).encode()
    listings = bestbuy.parse(body)
    assert len(listings) == 1
    assert listings[0].price == 1199.99 and listings[0].regular_price == 1599.99
    assert bestbuy._search_clause("elitebook x g1a") == "search=elitebook&search=x&search=g1a"


def test_parse_price_skips_discount_amounts():
    assert slickdeals.parse_price("ThinkPad X1 Carbon Gen 14 $400 off, now $1,449") == 1449
    assert slickdeals.parse_price("Save $500 on EliteBook X G1a: $1,199") == 1199
    assert slickdeals.parse_price("P14s Gen 6 AMD $1,279 w/ $300 instant savings") == 1279
    assert slickdeals.parse_price("Extra $350 off ThinkPads sitewide") is None
