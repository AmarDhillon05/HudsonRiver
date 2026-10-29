# Laptop Deal Alert

Watches for deals on a short list of laptops and pushes them to your phone with
[ntfy](https://ntfy.sh).

```text
EventBridge (every 30 min) ─┐
EventBridge (weekly)       ─┴→ Lambda → Slickdeals RSS + Best Buy API
                                  ↓                ↓
                          DynamoDB (dedupe)   ntfy push
```

## What it costs

Nothing beyond AWS, and it is sized to sit inside AWS's always-free tiers:

| Resource | Usage | Free tier |
| --- | --- | --- |
| Lambda (128 MB, ARM) | ~1,500 runs/month, a few seconds each | 1M requests, 400k GB-s/month |
| DynamoDB (on-demand) | a few thousand reads/writes a month, a few KB | ~$0.01/month even without it |
| EventBridge scheduled rules | 2 | free |
| CloudWatch Logs | kept 7 days | 5 GB/month |

The price sources cost nothing: Slickdeals' RSS needs no key, and the Best Buy
Products API key (optional) is requested at developer.bestbuy.com with no
listed fee.

## Alerts

| Priority | When |
| --- | --- |
| High (4) | A new deal at or below your target price |
| Default (3) | A new deal within 10% of target, or a new Best Buy low within 10% |
| Low (2) | A matching deal was posted but its price isn't in the title |

Plus two alerts about the checker itself, so silence never means "broken":

| Priority | When |
| --- | --- |
| High (4) | A source (Slickdeals or Best Buy) has failed on every check for 3 hours |
| Low (2) | That source is working again |
| Low (2) | Sunday 17:00 UTC: "still running, N alerts this week" (High if no check has succeeded in 6 hours) |

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
  means "P14s, Gen 6, AMD". Generations are normalized first, so "gen 6" also
  matches "Gen6", "6th Gen" and "Generation 6".
- `exclude` (global): titles with any of these never match (refurbished, open
  box, expired...).

Edit it, run `make test`, and redeploy.

## Running it

```bash
make setup                # creates .venv and installs everything; no need to activate it
make test                 # unit tests + CDK synth assertions, no AWS needed
make dry-run              # one real check against the live feeds, prints alerts
make dry-run ARGS=--any-age   # same, including old posts (to see matching at work)
```

## Known gaps

- Lenovo.com and HP.com, where most of these laptops are sold, block automated
  requests, so their sales are only seen once someone posts them on Slickdeals.
- Titles that don't name the generation (e.g. "X1 Carbon Aura Edition") don't
  match, on purpose: they can't be told apart from older models.
- Prices are read from deal titles. Discount amounts ("$400 off") are skipped,
  but an unusual title can still be misread; every alert shows the full title.

## Deploying

Needs AWS credentials in your shell and Node (the Makefile runs the CDK CLI
through `npx` if `cdk` isn't installed).

```bash
make bootstrap                         # once per account/region
make deploy                            # Slickdeals only, to the ntfy topic "hudson-river"
make deploy BESTBUY_API_KEY=<key>      # plus Best Buy
```

Subscribe to `hudson-river` in the ntfy app. Optional: `NTFY_TOPIC=...` to use a
different topic, `INTERVAL_MINUTES=60` to check less often. Topics on ntfy.sh are
public: anyone who knows the name can read the alerts or post fake ones.

To remove everything: `make destroy`.

## Automatic deploys

After a one-time setup, every push to `main` runs the tests and redeploys
through GitHub Actions (`.github/workflows/deploy.yml`). No AWS keys are stored
in GitHub: the workflow signs in with GitHub's OIDC token, and the role it gets
trusts only this repo's `main` branch and can do nothing except run `cdk deploy`.

1. Create the role, once (reuses the GitHub OIDC provider the jobs repo already
   created; add `CREATE_OIDC_PROVIDER=1` in an account that has none):
   ```bash
   make deploy-github-role
   ```
2. Copy the `DeployRoleArn` it prints into GitHub: repo Settings → Secrets and
   variables → Actions → **Variables** → `AWS_DEPLOY_ROLE_ARN`.
3. Optional: a `BESTBUY_API_KEY` **secret**, an `AWS_REGION` variable (default
   `us-east-1`), an `NTFY_TOPIC` variable (default `hudson-river`).

Until `AWS_DEPLOY_ROLE_ARN` is set, the workflow only runs the tests. The
"Run workflow" button redeploys without a code change.
