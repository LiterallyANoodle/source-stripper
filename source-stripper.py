import json
import os
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import discord


class StripperConfigurationError(Exception):
    """Raised when the bot configuration cannot be loaded or is malformed."""


class StripperConfiguration:

    def __init__(self, path: str = "configuration.json") -> None:
        self.path = path
        self.configuration = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except OSError as exc:
            raise StripperConfigurationError(
                f"Unable to open configuration file {self.path!r}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise StripperConfigurationError(
                f"Configuration file {self.path!r} is not valid JSON: {exc}"
            ) from exc

        if not isinstance(config, dict):
            raise StripperConfigurationError(
                f"Configuration {self.path!r} must be a JSON object"
            )
        return config


class Stripper(discord.Client):
    # Suppress the error on the User attribute being None since it fills up later
    user: discord.ClientUser

    def __init__(self, domain_matchers=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-instance list (not a mutable class default) of domain matchers from
        # configuration: [{"domains": ["youtube.com", "youtu.be"],
        #                   "parameters": ["si", "feature"]}, ...]
        self.domain_matchers = domain_matchers or []

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def on_message(self, message):
        # We do not want the bot to reply to itself
        if message.author.id == self.user.id:
            return

        try:
            links = self.find_links(message.content)
            stripped_links = self.strip_source_indicators(links)
        except Exception as exc:
            # Never crash the bot on a single malformed message.
            print(f"Error processing message: {exc}")
            return

        if not stripped_links:
            return

        response = ""
        for link in stripped_links:
            response += link + "\n"

        # Truncate to Discord's 2000-char message limit so we never raise.
        if len(response) > 2000:
            response = response[:1997] + "..."

        await self._deliver(message, response)

    async def _deliver(self, message, response):
        """Suppress the original embeds and reply with cleaned links.

        Isolation from on_message: edit/reply can each raise `discord.Forbidden`
        (missing Manage Messages) or `discord.HTTPException` (e.g. the message
        was deleted before we replied); neither should crash the bot.
        """
        try:
            await message.edit(suppress=True)
        except discord.DiscordException as exc:
            print(f"Failed to suppress embeds: {exc}")
        try:
            await message.reply(response, mention_author=False)
        except discord.DiscordException as exc:
            print(f"Failed to reply: {exc}")

    def find_links(self, message):
        """Extract http(s) URLs from a message, stripping trailing punctuation.

        Returns a list of URL strings, deduplicated, in order of first appearance.
        """
        text = str(message).strip()
        if not text:
            return []

        links: list[str] = []
        seen: set[str] = set()

        # Split on whitespace into tokens; a URL is a token that starts with
        # http:// or https:// (case-insensitive). This intentionally does not
        # try to parse nested/redirect links — the caller matches against the
        # token as-is.
        for token in text.split():
            low = token.lower()
            # Locate the scheme within the token so leading punctuation
            # (e.g. "(https://x.com)") still yields a usable URL, matching the
            # original bot's behavior of slicing from the first "http".
            idx = low.find("://")
            if idx == -1:
                continue
            # Back up to the start of the scheme ("http" or "https").
            for scheme_len in (5, 4):  # https, http
                if idx >= scheme_len and low[idx - scheme_len:idx] == ("https" if scheme_len == 5 else "http"):
                    candidate = token[idx - scheme_len:]
                    break
            else:
                continue
            # Strip trailing punctuation that commonly glues onto pasted URLs.
            stripped = self._strip_trailing_punct(candidate)
            if not stripped:
                continue
            if stripped not in seen:
                seen.add(stripped)
                links.append(stripped)

        return links

    @staticmethod
    def _strip_trailing_punct(token: str) -> str:
        # Do not strip characters that can legitimately appear inside a URL:
        # `/ ? & = # % + - _ . ~`. Strip common sentence punctuation and
        # unbalanced closers.
        closers = ")]}>\"'"
        # Count parentheses to decide whether a trailing ')' is unbalanced.
        while token and (token[-1] in ",.;:!?" or token[-1] in closers):
            if token[-1] == ")" and token.count("(") >= token.count(")"):
                # ')' has a matching '(' — part of a URL path (balanced).
                break
            token = token[:-1]
        return token

    def strip_source_indicators(self, links):
        """Remove configured tracking parameters from a list of URLs.

        Returns a list of rewritten URLs for those links whose hostname matches
        one of the configured official domains and that had at least one
        parameter removed. Links on non-matching domains are left untouched
        (and not echoed), so we never re-share or alter an unrelated URL.
        """
        matchers = self.domain_matchers
        if not matchers:
            return []

        # Normalize matchers into (domains, param_names) pairs. Hostnames are
        # stored lowercase for case-insensitive matching.
        rules: list[tuple[list[str], set[str]]] = []
        for dm in matchers:
            domains = dm.get("domains", [])
            params = dm.get("parameters", [])
            if not domains or not params:
                continue
            param_names = {str(p) for p in params if p}
            if not param_names:
                continue
            hosts = []
            for domain in domains:
                host = str(domain).lower().strip().lstrip(".")
                if host and "*" not in host:
                    hosts.append(host)
            if hosts:
                rules.append((hosts, param_names))

        if not rules:
            return []

        stripped: list[str] = []
        for link in links:
            result = self._strip_one(link, rules)
            if result is not None:
                stripped.append(result)

        return stripped

    @staticmethod
    def _host_matches(host, domains):
        """True iff `host` equals a domain or is a subdomain of it.

        `host` and each domain are already lowercased. This rejects lookalike
        / suffix-adjacent hosts (e.g. `notyoutube.com`, `youtube.com.evil.net`)
        while accepting official subdomains (`www.youtube.com`, `m.youtube.com`)
        and true alternate registrations (`youtu.be`).
        """
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return True
        return False

    @staticmethod
    def _strip_one(link, rules):
        """Strip matching params from a single URL; return None if unchanged."""
        try:
            parts = urlsplit(link)
        except ValueError:
            return None

        scheme = (parts.scheme or "").lower()
        if scheme not in ("http", "https"):
            return None

        host = (parts.hostname or "").lower()
        if not host:
            return None

        param_names = None
        for domains, names in rules:
            if Stripper._host_matches(host, domains):
                param_names = names
                break
        if param_names is None:
            return None

        if not parts.query:
            return None

        # Preserve parameter order and duplicates; only drop exact name matches.
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        kept = [(k, v) for (k, v) in pairs if k not in param_names]
        if len(kept) == len(pairs):
            # Nothing was removed — do not echo a verbatim copy.
            return None

        new_query = urlencode(kept, doseq=True)
        rebuilt = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
        )
        return rebuilt


if __name__ == "__main__":
    config_path = os.environ.get("SOURCE_STRIPPER_CONFIG", "configuration.json")
    try:
        config = StripperConfiguration(config_path).configuration
    except StripperConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    intents = discord.Intents.default()
    intents.message_content = True

    client = Stripper(intents=intents, domain_matchers=config.get("domain_matchers", []))

    # The bot token is a runtime secret (injected as SOURCE_STRIPPER_TOKEN env in
    # the container, sealed in sops on the host); fall back to the config file's
    # bot_token only when the env var is absent (e.g. local dev).
    bot_token = os.environ.get("SOURCE_STRIPPER_TOKEN") or str(config.get("bot_token", ""))
    if not bot_token:
        print(
            "Error: no bot token (set SOURCE_STRIPPER_TOKEN or configuration.json bot_token)",
            file=sys.stderr,
        )
        sys.exit(1)

    client.run(bot_token)
