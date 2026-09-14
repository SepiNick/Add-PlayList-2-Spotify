"""
CSV -> Spotify Playlist
------------------------
یک فایل CSV با ستون‌های Title و Artist می‌خونه، هر ردیف رو تو اسپاتیفای جستجو می‌کنه
و اگه پیدا شد به یک پلی‌لیست اضافه می‌کنه. آهنگ‌های پیدانشده در یک فایل گزارش
(CSV) ذخیره میشن.

نصب پیش‌نیاز:
    pip install spotipy

قبل از اجرا حتما بخش تنظیمات (CONFIG) پایین همین فایل رو پر کنید.
"""

import csv
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# =====================  CONFIG  =====================
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8080"
SPOTIFY_PLAYLIST_ID = ""            # اگه خالی باشه، یه پلی‌لیست جدید به اسم PLAYLIST_NAME ساخته میشه
PLAYLIST_NAME = "My CSV Playlist"   # اسم پلی‌لیست جدید (وقتی SPOTIFY_PLAYLIST_ID خالیه)
ADD_TO_LIKED_SONGS = True           # True = به‌جای پلی‌لیست، آهنگ‌ها رو به Liked Songs اضافه کن

INPUT_CSV = "tracklist.csv"         # فایل ورودی؛ باید ستون‌های Title, Artist داشته باشه
NOT_FOUND_REPORT = "not_found_tracks.csv"
SEARCH_CACHE = "search_cache.csv"   # نتیجه‌ی جستجوها اینجا ذخیره میشه تا اگه اسکریپت وسط کار قطع شد (مثلا rate limit) دوباره جستجو تکرار نشه

SPOTIFY_SCOPE = "playlist-modify-private playlist-modify-public user-library-modify"
REQUEST_DELAY = 0.15                # فاصله بین جستجوها (ثانیه) برای رعایت rate limit
# ======================================================


def read_tracks_from_csv(path):
    tracks = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("Title") or "").strip()
            artist = (row.get("Artist") or "").strip()
            if title:
                tracks.append({"title": title, "artist": artist})
    return tracks


def search_spotify_track(sp, title, artist):
    """جستجوی آهنگ تو اسپاتیفای؛ اول دقیق (artist+track)، بعد آزادتر."""
    queries = []
    if artist:
        queries.append(f'track:{title} artist:{artist}')
    queries.append(f"{artist} {title}".strip())

    for q in queries:
        try:
            result = sp.search(q=q, type="track", limit=1)
        except Exception:
            continue
        items = result.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"], items[0]["name"], items[0]["artists"][0]["name"]

    return None, None, None


def load_search_cache(path):
    cache = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                cache[(row["Title"], row["Artist"])] = (
                    row["URI"] or None, row["MatchedTitle"] or None, row["MatchedArtist"] or None,
                )
    except FileNotFoundError:
        pass
    return cache


def save_search_cache(path, cache):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Title", "Artist", "URI", "MatchedTitle", "MatchedArtist"])
        for (title, artist), (uri, matched_title, matched_artist) in cache.items():
            writer.writerow([title, artist, uri or "", matched_title or "", matched_artist or ""])


def add_tracks_in_chunks(sp, playlist_id, uris, chunk_size=100):
    for i in range(0, len(uris), chunk_size):
        sp.playlist_add_items(playlist_id, uris[i:i + chunk_size])


def add_to_liked_songs_in_chunks(sp, uris, chunk_size=20):
    for i in range(0, len(uris), chunk_size):
        sp.current_user_saved_tracks_add(uris[i:i + chunk_size])


def main():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise SystemExit("لطفا اول بخش تنظیمات اسپاتیفای رو تو فایل پر کنید.")

    tracks = read_tracks_from_csv(INPUT_CSV)
    print(f"{len(tracks)} ردیف از {INPUT_CSV} خونده شد.")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
    ))

    cache = load_search_cache(SEARCH_CACHE)
    found_uris = []
    not_found = []
    match_log = []

    for idx, track in enumerate(tracks, 1):
        key = (track["title"], track["artist"])
        label = f'{track["artist"]} - {track["title"]}'.strip(" -")

        if key in cache:
            uri, matched_title, matched_artist = cache[key]
        else:
            uri, matched_title, matched_artist = search_spotify_track(sp, track["title"], track["artist"])
            cache[key] = (uri, matched_title, matched_artist)
            save_search_cache(SEARCH_CACHE, cache)
            time.sleep(REQUEST_DELAY)

        if uri:
            found_uris.append(uri)
            match_log.append([track["title"], track["artist"], matched_title, matched_artist])
            print(f'[{idx}/{len(tracks)}] پیدا شد:  {label}  ->  {matched_artist} - {matched_title}')
        else:
            not_found.append(label)
            print(f'[{idx}/{len(tracks)}] پیدا نشد: {label}')

    if found_uris:
        if ADD_TO_LIKED_SONGS:
            add_to_liked_songs_in_chunks(sp, found_uris)
            print(f"\n{len(found_uris)} آهنگ به Liked Songs اضافه شد.")
        else:
            playlist_id = SPOTIFY_PLAYLIST_ID
            if not playlist_id:
                user_id = sp.current_user()["id"]
                playlist = sp.user_playlist_create(user_id, PLAYLIST_NAME, public=False)
                playlist_id = playlist["id"]
                print(f'پلی‌لیست «{PLAYLIST_NAME}» ساخته شد.')
            add_tracks_in_chunks(sp, playlist_id, found_uris)
            print(f"\n{len(found_uris)} آهنگ به پلی‌لیست اضافه شد.")

    if not_found:
        with open(NOT_FOUND_REPORT, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Track not found on Spotify"])
            for line in not_found:
                writer.writerow([line])
        print(f"{len(not_found)} آهنگ پیدا نشد؛ گزارش داخل «{NOT_FOUND_REPORT}» ذخیره شد.")
    else:
        print("همه‌ی آهنگ‌ها پیدا و اضافه شدن!")

    # گزارش تطبیق‌ها، برای اینکه ببینید هرکدوم دقیقاً چه ترکی از اسپاتیفای اضافه شده
    if match_log:
        with open("matched_tracks.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Original Title", "Original Artist", "Spotify Title", "Spotify Artist"])
            writer.writerows(match_log)
        print(f"جزئیات تطبیق‌ها هم تو «matched_tracks.csv» ذخیره شد؛ حتما یه نگاه بندازید"
              f" چون match ممکنه همیشه ۱۰۰٪ دقیق نباشه.")


if __name__ == "__main__":
    main()
