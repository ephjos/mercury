from typing import Dict, List, Optional

import json
import logging
import math
import os
import pathlib
import shutil

import click
import requests
import qrcode

import matplotlib.pyplot as plt

from PIL import Image, ImageColor, ImageOps, ImageDraw, ImageFont


logger = logging.getLogger(__name__)

CARD_W = 1000
CARD_WH = CARD_W // 2
CARD_W6 = CARD_W // 6

FONT_SIZE = 32
FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Black.ttf", FONT_SIZE)
LARGE_FONT_SIZE = 112
LARGE_FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Black.ttf", LARGE_FONT_SIZE)

BG = "#E81828"
FG = "#fff"


def request_json(method: str, url: str, **kwargs) -> Dict[str,str]:
    res = requests.request(method, url, **kwargs)
    res.raise_for_status()
    return res.json()


def get_access_token(client_id: str, client_secret: str) -> str:
    data = request_json("post",'https://accounts.spotify.com/api/token', 
                        data = [("grant_type", "client_credentials"), ("client_id", client_id), ("client_secret",client_secret)])
    return data["access_token"]


def map_spotify_track(track_dict) -> Dict[str, str]:
    track = track_dict["track"]

    return {
            "name": track["name"],
            "url": track["external_urls"]["spotify"],
            "year": track["album"]["release_date"][0:4],
            "artists": ", ".join(map(lambda a: a["name"], track["artists"]))
            }


def get_playlist(client_id: str, client_secret: str, playlist_id: str, playlist_json: str) -> Dict[str, str]:
    logger.info("Fetching spotify access token...")
    access_token = get_access_token(client_id, client_secret)
    headers = { "Authorization": f"Bearer {access_token}" }
    logger.debug(f'Headers: {headers}')

    url = f'https://api.spotify.com/v1/playlists/{playlist_id}'

    # Get playlist name
    data = request_json("get", url, headers=headers, params=[("fields", "name")])
    name = data["name"]

    # Get playlist tracks
    next = f'{url}/tracks'
    playlist = {
            "name": name,
            "tracks": [],
            }

    fields = "next,items(track(name,album(release_date),external_urls(spotify),artists(name)))"
    while next:
        data = request_json("get", next, headers=headers, params=[("fields", fields)])
        playlist["tracks"] += list(map(map_spotify_track, data["items"]))
        next = data["next"]

    json.dump(playlist, open(playlist_json, "w"), indent = 2)
    return playlist


def generate_histogram(output_directory: str, playlist: Dict[str, str]):
    years = list(map(lambda t: t["year"], playlist["tracks"]))
    a = int(min(years))
    b = int(max(years))
    counts = [0 for _ in range(b-a+1)]
    labels = [i+a for i in range(b-a+1)]
    for year in years:
        counts[int(year)-a] += 1

    fig, ax = plt.subplots()

    ax.bar(labels, counts)
    ax.set_title(playlist["name"])
    plt.savefig(pathlib.Path(output_directory, "hist.png"))
    return


def generate_cards(output_directory: str, playlist: Dict[str, str]):
    # Backs
    back_dir = pathlib.Path(output_directory, "backs")
    os.makedirs(back_dir)

    QR_W = 700

    for i, track in enumerate(playlist["tracks"]):
        qr = qrcode.make(track["url"]).resize((QR_W, QR_W))
        back = Image.new("RGB", (CARD_W, CARD_W), BG)
        a = (CARD_WH) - (QR_W // 2)
        back.paste(qr, (a, a))
        back.save(pathlib.Path(back_dir, f"back_{i:05d}.png"))

    # Fronts
    front_dir = pathlib.Path(output_directory, "fronts")
    os.makedirs(front_dir)

    TEXT_MARGIN = 100

    for i, track in enumerate(playlist["tracks"]):
        year = track["year"]
        artists = track["artists"]
        name = track["name"]

        front = Image.new("RGB", (CARD_W, CARD_W), BG)
        draw = ImageDraw.Draw(front)
        draw.text(((CARD_WH, CARD_WH)), year, fill=FG, font=LARGE_FONT, anchor="mm", align="center")
        draw.text(((CARD_WH, CARD_W6)), artists, fill=FG, font=FONT, anchor="mm", align="center")
        draw.text(((CARD_WH, 5*CARD_W6)), name, fill=FG, font=FONT, anchor="mm", align="center")

        bbox = draw.textbbox((0,0), year, font=LARGE_FONT)
        if bbox[2]-bbox[0] >= CARD_W - TEXT_MARGIN:
            logger.info(f'year "{year}" too long')
        bbox = draw.textbbox((0,0), artists, font=FONT)
        if bbox[2]-bbox[0] >= CARD_W - TEXT_MARGIN:
            logger.info(f'artists "{artists}" too long')
        bbox = draw.textbbox((0,0), name, font=FONT)
        if bbox[2]-bbox[0] >= CARD_W - TEXT_MARGIN:
            logger.info(f'name "{name}" too long')

        if False:
            draw.rectangle(((0, CARD_W6), (CARD_W, CARD_W6)))
            draw.rectangle(((0, CARD_WH), (CARD_W, CARD_WH)))
            draw.rectangle(((0, 5*CARD_W6), (CARD_W, 5*CARD_W6)))
            draw.rectangle(((CARD_WH, 0), (CARD_WH, CARD_W)))
        front.save(pathlib.Path(front_dir, f"front_{i:05d}.png"))
    return


def generate_box(output_directory: str, playlist: Dict[str, str]):
    name = playlist["name"]

    box = Image.new("RGB", (CARD_W, CARD_W), BG)
    draw = ImageDraw.Draw(box)

    length = math.ceil(draw.textlength(name, font=FONT))

    z = int(FONT_SIZE*1.5)
    for y in range(-CARD_W, CARD_W*2, z):
        for x in range(-CARD_W, CARD_W*2, length+z):
            draw.text(((x+y,y)), name, fill=FG, font=FONT, align="left")

    box.save(pathlib.Path(output_directory, f"box.png"))
    return


@click.group()
@click.option("--verbose", is_flag=True)
def main(verbose):
    level = logging.INFO
    if verbose:
        level = logging.DEBUG

    logging.basicConfig(format = '%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt = '%Y-%m-%d %H:%M:%S', level = level)


@main.command('get-playlist')
@click.option('--client-id', envvar='SPOTIFY_CLIENT_ID')
@click.option('--client-secret', envvar='SPOTIFY_CLIENT_SECRET')
@click.option('--playlist-json', default="./playlist.json")
def get_playlist_command(client_id: str, client_secret: str, playlist_id: str, playlist_json: str):
    logger.info("Fetching playlist...")
    playlist = get_playlist(client_id, client_secret, playlist_id, playlist_json)


@main.command('generate')
@click.option('--playlist-json', default="./playlist.json")
@click.option('--output-directory', default="./build")
def generate(playlist_json: str, output_directory: str):
    playlist = json.load(open(playlist_json, "r"))

    try:
        shutil.rmtree(output_directory)
    except:
        pass
    os.makedirs(output_directory)

    logger.info("Generating histogram...")
    generate_histogram(output_directory, playlist)

    logger.info("Generating cards...")
    generate_cards(output_directory, playlist)

    logger.info("Generating box...")
    generate_box(output_directory, playlist)


@main.command('all')
@click.option('--client-id', envvar='SPOTIFY_CLIENT_ID')
@click.option('--client-secret', envvar='SPOTIFY_CLIENT_SECRET')
@click.option('--playlist-json', default="./playlist.json")
@click.option('--output-directory', default="./build")
@click.argument('playlist_id')
def all(client_id: str, client_secret: str, output_directory: str, playlist_id: str, playlist_json: str):
    logger.info("Fetching playlist...")
    playlist = get_playlist(client_id, client_secret, playlist_id, playlist_json)

    try:
        shutil.rmtree(output_directory)
    except:
        pass
    os.makedirs(output_directory)

    logger.info("Generating histogram...")
    generate_histogram(output_directory, playlist)

    logger.info("Generating cards...")
    generate_cards(output_directory, playlist)

    logger.info("Generating box...")
    generate_box(output_directory, playlist)


if __name__ == "__main__":
    main()
