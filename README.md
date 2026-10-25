# Laptop Deal Alert

Watches for deals on a short list of laptops and pushes them to your phone with
[ntfy](https://ntfy.sh).

```text
EventBridge (every 30 min) → Lambda → Slickdeals RSS + Best Buy API
                               ↓                ↓
                       DynamoDB (dedupe)   ntfy push
```

## What it costs

Nothing beyond AWS, and it is sized to sit inside AWS's always-free tiers:

| Resource | Usage | Free tier |
| --- | --- | --- |
| Lambda (128 MB, ARM) | ~1,500 runs/month, a few seconds each | 1M requests, 400k GB-s/month |
| DynamoDB | 1 read + 1 write unit, a few KB | 25 + 25 units, 25 GB |
| EventBridge scheduled rule | 1 | free |
| CloudWatch Logs | kept 7 days | 5 GB/month |

The price sources are free: Slickdeals' RSS needs no key, and the Best Buy
Products API key is free (optional).

## Alerts

| Priority | When |
| --- | --- |
| High (4) | A new deal at or below your target price |
| Default (3) | A new deal within 10% of target, or a new Best Buy low within 10% |
| Low (2) | A matching deal was posted but its price isn't in the title |

Each Slickdeals post alerts once. A Best Buy price alerts once at target, then
again only if it drops further, or after it rises above target and drops back.
Tapping an alert opens the deal.

## The watchlist

`src/dealalert/watchlist.json`. For each laptop:

- `target`: alert at or below this price.
- `query`: what to search for on Slickdeals and Best Buy. Searches are fuzzy, so
  results are filtered with `match`.
- `match`: groups of terms. A listing matches when its title has at least one
  term from **every** group: `[["p14s"], ["gen 6", "g6"], ["amd", "ryzen"]]`
  means "P14s, Gen 6, AMD".
- `exclude` (global): titles with any of these never match (refurbished, open
  box, expired...).

Edit it, run `make test`, and redeploy.

## Running it

```bash
pip install -e ".[dev]"
make test                 # unit tests + CDK synth assertions, no AWS needed
make dry-run              # one real check against the live feeds, prints alerts
make dry-run ARGS=--any-age   # same, including old posts (to see matching at work)
```

## Deploying

Needs AWS credentials and the CDK CLI (`npm i -g aws-cdk`).

```bash
make bootstrap                                        # once per account/region
make deploy NTFY_TOPIC=<your-private-topic>           # Slickdeals only
make deploy NTFY_TOPIC=<topic> BESTBUY_API_KEY=<key>  # plus Best Buy
```

Optional: `INTERVAL_MINUTES=60` to check less often. Subscribe to your topic in
the ntfy app. Anyone who knows the topic name can read it, so pick something
unguessable.

To remove everything: `make destroy`.
