#!/usr/bin/env python
import argparse
import datetime
import threading
import subprocess
import time
import logging
import json
import pkg_resources
import pyscreenshot as ImageGrab

from PIL import Image
from PIL import ImageChops

with open("config.json", "r") as json_data_file:
    config = json.load(json_data_file)

logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                    filename=config['logfile'],
                    level=config['loglevel'],
                    datefmt='%Y-%m-%d %H:%M:%S')


def start_fcadefbneo(fcadefbneo_path=None, fc_challenge_id=None, game_name=None):
    logging.info(f"/usr/bin/wine {fcadefbneo_path}/fcadefbneo.exe quark:stream,{game_name},{fc_challenge_id}.2,7100 -w")
    fbneo_rc = subprocess.run(
        [
            '/usr/bin/wine',
            f'{fcadefbneo_path}/fcadefbneo.exe',
            f'quark:stream,{game_name},{fc_challenge_id}.2,7100',
            '-w'
        ]
    )


def start_obs():
    obs_rc = subprocess.run(
        [
            '/usr/bin/obs',
            '--minimize-to-tray',
            '--startrecording'
        ]
    )


def cleanup_tasks():
    # Need to kill a bunch of processes and restart pulseaudio
    subprocess.run(['pkill', '-9', 'fcadefbneo'])
    subprocess.run(['pkill', '-9', 'wine'])
    subprocess.run(['pkill', '-9', 'obs'])
    subprocess.run(['pkill', '-9', '-f', 'system32'])
    subprocess.run(['/usr/bin/pulseaudio', '-k'])


def main(fc_challange_id=None, fc_time=None, kill_time=None, fcadefbneo_path=None, fcreplay_path=None, game_name=None):
    logging.info('Starting pulseaudio')
    subprocess.run(['pulseaudio', '--daemon'])

    # Get start time
    begin_time = datetime.datetime.now()

    # Start ggpofbneo
    logging.info("Starting fcadefbneo thread")
    logging.debug(f"Arguments: {fcadefbneo_path}, {fc_challange_id}, {game_name}")

    ggpo_thread = threading.Thread(target=start_fcadefbneo, args=[
                                   fcadefbneo_path, fc_challange_id, game_name])
    ggpo_thread.start()
    logging.info("Started ggpofbneo")

    # Check to see if ggpofbneo is running. This seems to be quite hard since there arn't
    # any log files. Wait for wine to load emulator, then check the right portion of the
    # screen. If it's black, that means the emulator hasn't started playing the replay.
    # Tried monitoring sound and starting the record when sound plays, but that doesn't
    # work reliably. So going to grab the screen capture. This requires a few edge cases:
    # 1. Launch ggpofbneo
    #   1. Check to see if ggpofbneo is loaded
    #     1. Check to see if there are screen updates

    empty_capture = Image.open(pkg_resources.resource_filename(
        'fcreplay', 'data/empty_capture.png')).convert('RGB')
    ggpo_capture = Image.open(pkg_resources.resource_filename(
        'fcreplay', 'data/ggpo_capture.png')).convert('RGB')

    empty_capture.save('empty_capture.png')
    ggpo_capture.save('ggpo_capture.png')

    logging.info('Starting image capture loop')
    while True:
        running_time = (datetime.datetime.now() - begin_time).seconds

        screen_ggpo_capture = ImageGrab.grab(
            backend='maim',
            bbox=(485, 0, 514, 18)).convert('RGB')
        screen_capture1 = ImageGrab.grab(
            backend='maim',
            bbox=(800, 100, 950, 650)).convert('RGB')

        screen_ggpo_capture.save('screen_ggpo_capture.png')
        screen_capture1.save('screen_capture1.png')

        time.sleep(0.2)

        # Check if ggpo is running:
        diff = ImageChops.difference(screen_ggpo_capture, ggpo_capture)
        if not diff.getbbox():
            logging.info('Detected GGPO')

            # Check if screen is empty
            diff = ImageChops.difference(empty_capture, screen_capture1)

            # Something on screen
            if diff.getbbox():
                logging.info('Detected non-black GGPO screen')
                # Look for non-static image
                screen_capture2 = ImageGrab.grab(
                    backend='maim',
                    bbox=(800, 100, 950, 650))
                screen_capture2.save('screen_capture2.png')
                screen_capture2 = ImageGrab.grab(
                    backend='maim',
                    bbox=(800, 100, 950, 650)).convert('RGB')
                diff = ImageChops.difference(screen_capture1, screen_capture2)

                # Something has changes
                if diff.getbbox():
                    logging.info('Detected screen updates')
                    break
            else:
                logging.info('Detected black GGPO screen')

        if running_time > kill_time:
            logging.info('Match never started, exiting')
            cleanup_tasks()
            return "FailTimeout"

    logging.info("Starting obs")
    obs_thread = threading.Thread(target=start_obs)
    obs_thread.start()
    logging.info("Started obs")

    begin_time = datetime.datetime.now()
    while True:
        running_time = (datetime.datetime.now() - begin_time).seconds
        obs_running = '/usr/bin/obs' in str(subprocess.run(
            ['ps', '-ef'], stdout=subprocess.PIPE, stderr=subprocess.PIPE))

        if (running_time % 60) == 0:
            logging.info(
                f'Minute: {int(running_time/60)} of {int(fc_time/60)}')

        if running_time > fc_time:
            # We have reached the end of the video. Killing processes
            if obs_running:
                cleanup_tasks()
                return "Pass"
            else:
                logging.error(
                    "Timeout reached but obs isn't running. Something was broken")
                cleanup_tasks()
                return "FailNoOBS"
        if running_time > kill_time:
            # Check if OBS is running, if it isn't then we are broken :(
            if not obs_running:
                logging.error("Kill timeout reached killing processes")
                cleanup_tasks()
                return "FailTimeout"
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record fightcade replays")
    parser.add_argument('fc_challenge_id', help="Fightcade challenge id")
    parser.add_argument('fc_time', help="Length of time in seconds to record")
    parser.add_argument(
        'kill_timeout', help="How long to wait before killing processing")
    parser.add_argument('fcadefbneo_path', help='Path to ggpo')
    parser.add_argument('fcreplay_path', help='Path to fcreplay')
    parser.add_argument('game_name', help='Game name (Eg: sfiii3nr1)')
    args = parser.parse_args()
    main(
        fc_challange_id=args.fc_challenge_id,
        fc_time=int(args.fc_time),
        kill_time=int(args.kill_timeout),
        fcadefbneo_path=args.fcadefbneo_path,
        fcreplay_path=args.fcreplay_path,
        game_name=args.game_name)
