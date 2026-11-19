# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Email Autopilot finder: businesses from maps, web search, and public contact details from their own websites.

  uv run tools/finder.py maps "dentist" --location "Thessaloniki, Greece" [--limit 30]
  uv run tools/finder.py search "skincare brand founder Greece contact"           # web search (DuckDuckGo)
  uv run tools/finder.py site https://example.com                                  # emails, socials, what they do
  uv run tools/finder.py reviews "restaurant" --location "Athens, Greece"          # businesses with MANY bad reviews + what customers complain about (needs a Google Places key)

`maps` uses the official Google Places API when a key is saved (dashboard, "Google Maps key"), otherwise the free
OpenStreetMap data (no key, good coverage of shops, clinics, restaurants, gyms, hotels; thinner for small niches).
Everything prints JSON. Only publicly listed business contact details are collected, nothing behind a login.
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_KEY_FILE = ROOT / "data" / ".secrets" / "maps.json"
UA = "Mozilla/5.0 (compatible; EmailAutopilot/1.0; business-contact-research)"
API_UA = "EmailAutopilot/1.0 (business research tool)"  # open map servers reject browser-like agents


def out(o) -> None:
    print(json.dumps(o, ensure_ascii=False, indent=1))


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 25, limit: int = 1_500_000):
    h = {"User-Agent": UA, "Accept-Language": "en,el;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(limit)
        cs = r.headers.get_content_charset() or "utf-8"
        return raw.decode(cs, "replace"), r.geturl()


def public_url(url: str) -> str | None:
    """Only http(s) URLs that point to the public internet."""
    if not re.match(r"^[a-z]+://", url):
        url = "https://" + url
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return None
    except OSError:
        return None
    return url


# ---------------------------------------------------------------- maps
OSM_TAGS = {
    "dentist": ['"amenity"="dentist"', '"healthcare"="dentist"'], "dental": ['"amenity"="dentist"'],
    "οδοντ": ['"amenity"="dentist"'], "doctor": ['"amenity"="doctors"', '"healthcare"="doctor"'],
    "clinic": ['"amenity"="clinic"', '"healthcare"="clinic"'], "physio": ['"healthcare"="physiotherapist"'],
    "φυσιοθ": ['"healthcare"="physiotherapist"'], "veterin": ['"amenity"="veterinary"'], "κτηνι": ['"amenity"="veterinary"'],
    "pharmacy": ['"amenity"="pharmacy"'], "φαρμακ": ['"amenity"="pharmacy"'],
    "hair": ['"shop"="hairdresser"'], "κομμωτ": ['"shop"="hairdresser"'], "beauty": ['"shop"="beauty"'],
    "nail": ['"shop"="beauty"'], "spa": ['"leisure"="spa"', '"amenity"="spa"'], "gym": ['"leisure"="fitness_centre"'],
    "γυμναστ": ['"leisure"="fitness_centre"'], "fitness": ['"leisure"="fitness_centre"'], "yoga": ['"sport"="yoga"'],
    "restaurant": ['"amenity"="restaurant"'], "εστιατ": ['"amenity"="restaurant"'], "cafe": ['"amenity"="cafe"'],
    "καφέ": ['"amenity"="cafe"'], "bar": ['"amenity"="bar"'], "hotel": ['"tourism"="hotel"'], "ξενοδοχ": ['"tourism"="hotel"'],
    "boutique": ['"shop"="clothes"'], "clothing": ['"shop"="clothes"'], "ρούχα": ['"shop"="clothes"'],
    "jewel": ['"shop"="jewelry"'], "κοσμήματα": ['"shop"="jewelry"'], "florist": ['"shop"="florist"'],
    "bakery": ['"shop"="bakery"'], "φούρνος": ['"shop"="bakery"'], "bookstore": ['"shop"="books"'],
    "furniture": ['"shop"="furniture"'], "optic": ['"shop"="optician"'], "οπτικ": ['"shop"="optician"'],
    "lawyer": ['"office"="lawyer"'], "δικηγ": ['"office"="lawyer"'], "accountant": ['"office"="accountant"'],
    "λογιστ": ['"office"="accountant"'], "real estate": ['"office"="estate_agent"'], "architect": ['"office"="architect"'],
    "photograph": ['"craft"="photographer"', '"shop"="photo"'], "bike": ['"shop"="bicycle"'], "car": ['"shop"="car_repair"'],
    "winery": ['"craft"="winery"'], "κρασ": ['"craft"="winery"'], "school": ['"amenity"="school"', '"amenity"="language_school"'],
    "language": ['"amenity"="language_school"'], "travel": ['"shop"="travel_agency"'],
}


def maps_key() -> str:
    if os.environ.get("GOOGLE_MAPS_API_KEY"):
        return os.environ["GOOGLE_MAPS_API_KEY"]
    try:
        return json.loads(MAPS_KEY_FILE.read_text(encoding="utf-8-sig")).get("key", "")
    except Exception:  # noqa: BLE001
        return ""


def maps_google(query: str, location: str, limit: int, key: str) -> list[dict]:
    res: list[dict] = []
    token = None
    for _ in range(3):  # up to 3 pages x 20
        body = {"textQuery": f"{query} in {location}", "pageSize": 20}
        if token:
            body["pageToken"] = token
        txt, _ = http("https://places.googleapis.com/v1/places:searchText", json.dumps(body).encode(),
                      {"Content-Type": "application/json", "X-Goog-Api-Key": key,
                       "X-Goog-FieldMask": "places.displayName,places.websiteUri,places.formattedAddress,places.nationalPhoneNumber,"
                                           "places.primaryTypeDisplayName,places.rating,places.userRatingCount,places.googleMapsUri,nextPageToken"})
        d = json.loads(txt)
        for p in d.get("places", []):
            res.append({"name": p.get("displayName", {}).get("text", ""), "website": p.get("websiteUri", ""),
                        "address": p.get("formattedAddress", ""), "phone": p.get("nationalPhoneNumber", ""),
                        "category": p.get("primaryTypeDisplayName", {}).get("text", ""), "rating": p.get("rating"),
                        "reviews": p.get("userRatingCount"), "maps_url": p.get("googleMapsUri", ""), "email": "", "source": "google_places"})
        token = d.get("nextPageToken")
        if not token or len(res) >= limit:
            break
    return res[:limit]


def maps_osm(query: str, location: str, limit: int) -> list[dict]:
    geo, _ = http("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": location, "format": "json", "limit": 1}), headers={"User-Agent": API_UA})
    g = json.loads(geo)
    if not g:
        raise RuntimeError(f"location not found: {location}")
    s, n, w, e = g[0]["boundingbox"]
    box = f"({s},{w},{n},{e})"
    q = query.lower()
    filters: list[str] = []
    for k, v in OSM_TAGS.items():
        if k in q:
            filters += v
    parts = [f"nwr[{f}]{box};" for f in dict.fromkeys(filters)]
    if not parts:  # unknown niche: match the business name
        clean = re.sub(r"[^\w ]", "", q)
        parts = [f'nwr["name"~"{clean}",i]{box};']
    ql = f"[out:json][timeout:45];({''.join(parts)});out tags center {max(limit * 6, 120)};"
    txt = ""
    err: Exception | None = None
    mirrors = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
               "https://overpass.private.coffee/api/interpreter")
    for attempt in range(2):  # the free servers are sometimes busy: try every mirror twice
        for ep in mirrors:
            try:
                txt, _ = http(ep, urllib.parse.urlencode({"data": ql}).encode(), {"User-Agent": API_UA, "Accept": "application/json"}, timeout=90)
                break
            except Exception as ex:  # noqa: BLE001
                err = ex
        if txt:
            break
        time.sleep(5)
    if not txt:
        raise RuntimeError(f"map server busy: {err}")
    res = []
    for el in json.loads(txt).get("elements", []):
        t = el.get("tags", {})
        if not t.get("name"):
            continue
        web = t.get("website") or t.get("contact:website") or t.get("url") or ""
        mail = t.get("email") or t.get("contact:email") or ""
        if not (web or mail):
            continue  # nothing to email
        addr = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber"), t.get("addr:city")) if x)
        res.append({"name": t["name"], "website": web, "address": addr, "phone": t.get("phone") or t.get("contact:phone") or "",
                    "category": next((t[k] for k in ("amenity", "shop", "office", "healthcare", "leisure", "craft", "tourism") if k in t), ""),
                    "rating": None, "reviews": None, "maps_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                    "email": mail.split(";")[0].strip(), "source": "openstreetmap"})
    res.sort(key=lambda r: (not r["email"], not r["website"]))
    return res[:limit]


CACHE = ROOT / "data" / "cache"


def cmd_maps(a):
    key = maps_key()
    ck = CACHE / (re.sub(r"[^a-z0-9]+", "_", f"{a.query}_{a.location}_{a.limit}_{'g' if key else 'o'}".lower())[:120] + ".json")
    try:
        if ck.exists() and time.time() - ck.stat().st_mtime < 86400:  # same search within 24 h: reuse (saves the busy free servers)
            return out(json.loads(ck.read_text(encoding="utf-8")))
        res = maps_google(a.query, a.location, a.limit, key) if key else maps_osm(a.query, a.location, a.limit)
    except Exception as ex:  # noqa: BLE001
        return out({"ok": False, "error": f"{type(ex).__name__}: {ex}",
                    "hint": "If this says 403, the Google key is wrong or Places API (New) is not enabled." if key else "Try again in a minute (free map servers are busy at times)."})
    result = {"ok": True, "source": "google_places" if key else "openstreetmap", "count": len(res), "places": res}
    if res:
        CACHE.mkdir(parents=True, exist_ok=True)
        ck.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    out(result)


# ---------------------------------------------------------------- web search (DuckDuckGo html)
def cmd_search(a):
    try:
        txt, _ = http("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": a.query}))
    except Exception as ex:  # noqa: BLE001
        return out({"ok": False, "error": f"{type(ex).__name__}: {ex}"})
    res = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', txt, re.S):
        href = html.unescape(m.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q.get("uddg", [href])[0]
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
        res.append({"title": re.sub(r"<.*?>", "", html.unescape(m.group(2))).strip(), "url": url,
                    "snippet": re.sub(r"<.*?>", "", html.unescape(snip.group(1))).strip() if snip else ""})
        if len(res) >= a.limit:
            break
    out({"ok": bool(res), "count": len(res), "results": res,
         **({} if res else {"hint": "No results (the search engine may be rate limiting). Use your own web search tool instead."})})


# ---------------------------------------------------------------- site: emails + what they do
class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.meta: dict[str, str] = {}
        self.lang = ""
        self._skip = 0
        self._tag = ""
        self._href = None
        self._atext: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self._tag = tag
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "html" and d.get("lang"):
            self.lang = d["lang"][:5]
        if tag == "meta":
            k = (d.get("name") or d.get("property") or "").lower()
            if k in ("description", "og:description", "og:site_name", "og:title"):
                self.meta[k] = d.get("content", "")
        if tag == "a" and d.get("href"):
            self._href, self._atext = d["href"], []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._atext).strip()))
            self._href = None

    def handle_data(self, data):
        if self._tag == "title" and not self.title:
            self.title = data.strip()
        if self._skip:
            return
        s = data.strip()
        if s:
            self.text.append(s)
            if self._href is not None:
                self._atext.append(s)


EMAIL_FIND = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+")
JUNK = re.compile(r"(\.(png|jpe?g|gif|webp|svg|css|js)$)|sentry|wixpress|example\.|domain\.com|yourdomain|email\.com|noreply|no-reply|donotreply|@2x|u003e", re.I)
ROLE_RANK = ["partnership", "collab", "press", "business", "hello", "contact", "info", "office", "sales", "marketing", "team", "support"]
CONTACT_HINT = re.compile(r"contact|about|team|press|partner|collab|work-with|business|impressum|epikoinon|επικοιν|σχετικά|ομάδα|για-εμάς|about-us", re.I)
SOCIAL = {"instagram": "instagram.com", "linkedin": "linkedin.com", "facebook": "facebook.com", "youtube": "youtube.com",
          "tiktok": "tiktok.com", "x": "twitter.com", "x2": "x.com"}


def deobfuscate(t: str) -> str:
    t = re.sub(r"\s*[\[\(\{]\s*(at|AT)\s*[\]\)\}]\s*", "@", t)
    t = re.sub(r"\s*[\[\(\{]\s*(dot|DOT)\s*[\]\)\}]\s*", ".", t)
    return t


def rank(email: str, site_domain: str) -> tuple:
    user, _, dom = email.partition("@")
    same = dom == site_domain or dom.endswith("." + site_domain) or site_domain.endswith("." + dom)
    r = next((i for i, k in enumerate(ROLE_RANK) if k in user), len(ROLE_RANK))
    return (not same, r)


def cmd_site(a):
    url = public_url(a.url)
    if not url:
        return out({"ok": False, "error": "not a public http(s) address"})
    try:
        txt, final = http(url, timeout=20)
    except Exception as ex:  # noqa: BLE001
        return out({"ok": False, "error": f"{type(ex).__name__}: {ex}", "url": url})
    base = urllib.parse.urlparse(final)
    dom = (base.hostname or "").lower().removeprefix("www.")
    pages = [(final, txt)]
    p0 = Page()
    p0.feed(txt)
    seen_urls = {final.rstrip("/")}
    cand = []
    for href, label in p0.links:
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        full = urllib.parse.urljoin(final, href).split("#")[0]
        u = urllib.parse.urlparse(full)
        if (u.hostname or "").lower().removeprefix("www.") != dom:
            continue
        if CONTACT_HINT.search(u.path + " " + label) and full.rstrip("/") not in seen_urls:
            seen_urls.add(full.rstrip("/"))
            cand.append(full)
    for extra in ("/contact", "/contact-us", "/about", "/epikoinonia"):
        full = urllib.parse.urljoin(final, extra)
        if full.rstrip("/") not in seen_urls and len(cand) < 6:
            seen_urls.add(full.rstrip("/"))
            cand.append(full)
    for c in cand[:4]:
        try:
            pages.append((c, http(c, timeout=15)[0]))
        except Exception:  # noqa: BLE001
            pass
    found: dict[str, str] = {}
    socials: dict[str, str] = {}
    body_text = ""
    for u, t in pages:
        pg = Page()
        pg.feed(t)
        if not body_text:
            body_text = " ".join(pg.text)
        for href, _ in pg.links:
            if href.lower().startswith("mailto:"):
                for e in EMAIL_FIND.findall(urllib.parse.unquote(href[7:].split("?")[0])):
                    found.setdefault(e.lower(), u)
            else:
                for k, host in SOCIAL.items():
                    if host in href and k not in socials and not any(x in href for x in ("/share", "/intent", "sharer")):
                        socials[k.rstrip("2")] = href.split("?")[0]
        for e in EMAIL_FIND.findall(deobfuscate(" ".join(pg.text))) + EMAIL_FIND.findall(deobfuscate(html.unescape(t))):
            found.setdefault(e.lower(), u)
    emails = sorted((e for e in found if not JUNK.search(e)), key=lambda e: rank(e, dom))
    p = p0
    out({"ok": True, "url": final, "domain": dom, "title": p.title[:150], "description": (p.meta.get("description") or p.meta.get("og:description") or "")[:300],
         "site_name": p.meta.get("og:site_name", ""), "lang": p.lang, "emails": [{"email": e, "found_on": found[e], "same_domain": rank(e, dom)[0] is False} for e in emails[:6]],
         "socials": socials, "excerpt": re.sub(r"\s+", " ", body_text)[:1500], "pages_read": len(pages)})


# ---------------------------------------------------------------- reviews: businesses with many bad reviews
METHOD = ("Google gives each place an average rating, a review count and at most 5 sample reviews (no full distribution). "
          "1) Peers = the other places in this same search. 2) Adjusted rating = the rating pulled toward the peer average, harder when there are few reviews (weight 15), "
          "so 6 reviews at 3.0 stars is not treated like 300 reviews at 3.0. 3) Estimated bad reviews (3 stars or less) = review count x share, "
          "share = 4% + 24% per star below 4.7 (typical J-shaped review curve: 4.3 stars is about 14%, 3.8 about 26%, 3.2 about 40%). A rough estimate, not a count. "
          "4) 'Many' = at least min_negative estimated bad reviews AND rating at or below max_rating AND clearly below peers. "
          "5) Evidence = how many of the 5 sample reviews are bad and have text: themes are only reliable when evidence is strong.")


def neg_share(rating: float) -> float:
    return max(0.02, min(0.7, 0.04 + (4.7 - rating) * 0.24))


def score_places(places: list[dict], min_reviews: int = 30, max_rating: float = 4.1, min_negative: int = 15, prior: int = 15) -> list[dict]:
    rated = [p for p in places if p.get("rating") and (p.get("reviews_count") or 0) >= 10]
    peer = sum(p["rating"] for p in rated) / len(rated) if rated else 4.4
    out_rows = []
    for p in places:
        r, n = p.get("rating"), int(p.get("reviews_count") or 0)
        if not r or n <= 0:
            continue
        adj = (n * r + prior * peer) / (n + prior)
        est = round(n * neg_share(r))
        gap = round(peer - adj, 2)
        sample = [x for x in p.get("sample_reviews", []) if (x.get("stars") or 5) <= 3 and (x.get("text") or "").strip()]
        peers_ok = len(rated) >= 8
        qualifies = n >= min_reviews and r <= max_rating and est >= min_negative and (gap >= 0.2 or not peers_ok)
        row = {k: p.get(k) for k in ("name", "website", "address", "phone", "category", "maps_url")}
        row.update({"rating": r, "reviews_count": n, "adjusted_rating": round(adj, 2), "peer_average": round(peer, 2), "gap_vs_peers": gap,
                    "estimated_bad_reviews": est, "qualifies": qualifies, "pain_score": round(est * (1 + max(0, gap)), 1),
                    "evidence": "strong" if len(sample) >= 2 else "weak" if sample else "none",
                    "bad_sample_reviews": [{"stars": x["stars"], "when": x.get("when", ""), "text": x["text"][:500]} for x in sample]})
        out_rows.append(row)
    out_rows.sort(key=lambda x: (-x["qualifies"], -x["pain_score"]))
    return out_rows


def places_with_reviews(query: str, location: str, limit: int, key: str) -> list[dict]:
    res: list[dict] = []
    token = None
    for _ in range(3):
        body = {"textQuery": f"{query} in {location}", "pageSize": 20}
        if token:
            body["pageToken"] = token
        txt, _ = http("https://places.googleapis.com/v1/places:searchText", json.dumps(body).encode(),
                      {"Content-Type": "application/json", "X-Goog-Api-Key": key,
                       "X-Goog-FieldMask": "places.displayName,places.websiteUri,places.formattedAddress,places.nationalPhoneNumber,"
                                           "places.primaryTypeDisplayName,places.rating,places.userRatingCount,places.googleMapsUri,places.reviews,nextPageToken"})
        d = json.loads(txt)
        for p in d.get("places", []):
            res.append({"name": p.get("displayName", {}).get("text", ""), "website": p.get("websiteUri", ""), "address": p.get("formattedAddress", ""),
                        "phone": p.get("nationalPhoneNumber", ""), "category": p.get("primaryTypeDisplayName", {}).get("text", ""),
                        "rating": p.get("rating"), "reviews_count": p.get("userRatingCount"), "maps_url": p.get("googleMapsUri", ""),
                        "sample_reviews": [{"stars": rv.get("rating"), "when": rv.get("relativePublishTimeDescription", ""),
                                            "text": (rv.get("originalText") or rv.get("text") or {}).get("text", "")} for rv in p.get("reviews", [])]})
        token = d.get("nextPageToken")
        if not token or len(res) >= limit:
            break
    return res[:limit]


def cmd_reviews(a):
    key = maps_key()
    if not key:
        return out({"ok": False, "error": "This needs a Google Places API key (the free OpenStreetMap data has no reviews). Save it in the dashboard, Ρυθμίσεις section 3.",
                    "hint": "Do not scrape Google Maps pages. Use the official key, or skip the review-pain filter."})
    try:
        places = places_with_reviews(a.query, a.location, a.limit, key)
    except Exception as ex:  # noqa: BLE001
        return out({"ok": False, "error": f"{type(ex).__name__}: {ex}", "hint": "403 = wrong key or Places API (New) not enabled."})
    rows = score_places(places, a.min_reviews, a.max_rating, a.min_negative)
    out({"ok": True, "searched": len(places), "qualifying": sum(1 for r in rows if r["qualifies"]), "method": METHOD,
         "note": "Reviewer names are not included. Paraphrase themes, never quote or name anyone. Only claim what the bad_sample_reviews support.", "places": rows})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("maps"); s.add_argument("query"); s.add_argument("--location", required=True); s.add_argument("--limit", type=int, default=30)
    s = sub.add_parser("reviews"); s.add_argument("query"); s.add_argument("--location", required=True); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--min-reviews", type=int, default=30); s.add_argument("--max-rating", type=float, default=4.1); s.add_argument("--min-negative", type=int, default=15)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("site"); s.add_argument("url")
    a = ap.parse_args()
    {"maps": cmd_maps, "search": cmd_search, "site": cmd_site, "reviews": cmd_reviews}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
