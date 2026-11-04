# source-stripper

A Discord bot that strips source/tracking query parameters from links users
share in chat and replies with the cleaned URL.

## How it works

For every (non-self) message, the bot:

1. Extracts `http(s)://` URLs (case-insensitive, tolerant of trailing/leading
   punctuation and parentheses).
2. For each URL whose hostname is an *official* variant of a known domain
   (exact match or a subdomain of it — `youtube.com`, `youtu.be`, `www.youtube.com`,
   but NOT `notyoutube.com`), it removes any query parameter whose name is in
   that domain's configured strip list.
3. Replys with the rewritten URLs (and suppresses the original embeds).

## Configuration

`domain_matchers` (the sites and which params to strip from each) live in
`configuration-template.json` and are baked into the image as
`configuration.json` at build time — edit that template, not a runtime file.

The **bot token** is a secret and is NOT in the config. In production it is
injected via the `SOURCE_STRIPPER_TOKEN` environment variable; for local dev,
copy `configuration-template.json` to `configuration.json` and put the token
there (env var still takes precedence if both are set). The config file path
can be overridden with `SOURCE_STRIPPER_CONFIG`.

```json
{
  "bot_token": "your-token",
  "domain_matchers": [
    {
      "domains": ["youtube.com", "youtu.be"],
      "parameters": ["si", "feature", "pp", "kw", "gclid"]
    },
    {
      "domains": ["x.com", "twitter.com", "t.co"],
      "parameters": ["a", "s", "t", "cn", "ref_url", "ref_src", "src"]
    }
  ]
}
```

- `domains`: official hostnames for the site (including true alternate
  registrations like `youtu.be`, `t.co`, `amzn.to`). Subdomains of a listed
  domain are matched automatically; lookalike domains are not.
- `parameters`: query-parameter names to remove from matching URLs (exact,
  case-sensitive name match; values may be any length).

## Run

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 source-stripper.py
```

## Test

```sh
.venv/bin/python3 -m pytest test_source_stripper.py -q
```
