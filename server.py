#!sudo /usr/bin/env python

from slack import WebClient
from slack.errors import SlackApiError
from io import BytesIO
import json
import feedparser
from jsmin import jsmin
import threading
import glob
from time import sleep
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, make_response, request, redirect, url_for, send_from_directory, render_template, send_file
import logging
logging.basicConfig(level=logging.DEBUG)


globalTileSize = (300, 300)
globalSeverityLevel = "LOW"
globalLastUpdated = datetime.now()
globalLastChecked = datetime.now()
globalChannelId = "C00000000000"
globalSlackClient = ""

globalDictseverityLevels = {
    "CRITICAL"    : {
        "bgcolor" : ( 255, 0, 0),
        "title": "Critical",
        "def": "An an attack is highly\nlikely in the near future.",
        "titleFontSize": 60
        },
    "SEVERE"      : {
        "bgcolor" : (220,135,135),
        "title": "Severe",
        "def": "An attack is highly likely.",
        "titleFontSize": 60
        },
    "SUBSTANTIAL" : {
        "bgcolor" : (255,210,0),
        "title": "Substantial",
        "def": "An attack is likely.",
        "titleFontSize": 42
        },
    "MODERATE"    : {
        "bgcolor" : (0,170,215),
        "title": "Moderate",
        "def": "An attack is possible,\nbut not likely.",
        "titleFontSize": 50
        },
    "LOW"         : {
        "bgcolor" : (0,210,0),
        "title": "Low",
        "def": "An attack is highly\nunlikely.",
        "titleFontSize": 80
        }
}

def setupSlack():
    global globalChannelId, globalSlackClient
    slack_token = os.getenv("SLACK_TOKEN")
    globalSlackClient = WebClient(token=slack_token)
    try:
        response = globalSlackClient.conversations_list(types="public_channel", exclude_archived=1)
        for channel in response['channels']:
            print(f"Channel name = {channel['name']}")
            if channel['name'] == 'announcements':
                globalSlackClient.conversations_join(channel=channel['id'])
                globalChannelId = channel['id']
                break
    except SlackApiError as e:
        assert e.response["error"]

def postUpdateToSlack():
    global globalChannelId, globalDictseverityLevels, globalSeverityLevel, globalSlackClient
    bgcolor = globalDictseverityLevels[globalSeverityLevel]['bgcolor']
    try:
        img = Image.new('RGB', globalTileSize, color = bgcolor)

        response = globalSlackClient.files_upload(
            channels=globalChannelId,
            file=generateTile(img),
            title="The Current Serverity Level from MI5"
        )
        response = globalSlackClient.chat_postMessage(
            channel=globalChannelId,
            text=f"The current threat level from MI5 has been updated to {globalSeverityLevel}"
        )
    except SlackApiError as e:
        assert e.response["error"]

def generateTile(img):
    global globalDictseverityLevels, globalSeverityLevel, globalLastUpdated
    # bgColor = globalDictseverityLevels[globalSeverityLevel]["bgcolor"]
    title = globalDictseverityLevels[globalSeverityLevel]["title"]
    definition = globalDictseverityLevels[globalSeverityLevel]["def"]
    fgColor = (255,255,255)
    titleFontSize = globalDictseverityLevels[globalSeverityLevel]["titleFontSize"]

    titleFont = ImageFont.truetype('./lib/Ubuntu-B.ttf', titleFontSize)
    defFont = ImageFont.truetype('./lib/Ubuntu-B.ttf', 24)
    headingFont = ImageFont.truetype('./lib/Ubuntu-B.ttf', 16)
    textFont = ImageFont.truetype('./lib/Ubuntu-R.ttf', 18)

    d = ImageDraw.Draw(img)
    d.text((5,25), title, font=titleFont, fill=fgColor)
    d.multiline_text((5,125), definition, font=defFont, fill=fgColor)
    d.text((5,250), "Last Updated:", font=headingFont, fill=fgColor)
    d.text((5,270), globalLastUpdated.strftime("%Y/%m/%d, %H:%M"), font=textFont, fill=fgColor)

    # Save image to memory
    img_io = BytesIO()
    img.save(img_io, 'PNG', compress_level=0)
    img_io.seek(0)
    return img_io

def getSeverityLevel():
    global globalSeverityLevel, globalLastChecked, globalLastUpdated
    NewsFeed = feedparser.parse("https://www.mi5.gov.uk/UKThreatLevel/UKThreatLevel.xml")
    severityLevel = NewsFeed.entries[0].title.split(':')[1].strip()
    if severityLevel != globalSeverityLevel:
        globalSeverityLevel = severityLevel
        postUpdateToSlack()
        lastUpdateStr = NewsFeed.entries[0].published
        globalLastUpdated = datetime.strptime(lastUpdateStr, '%A, %B %d, %Y - %H:%M')
    globalLastChecked = datetime.now()

sched = BackgroundScheduler(daemon=True)
sched.add_job(getSeverityLevel,'interval',seconds=30)
sched.start()

class MyFlaskApp(Flask):
    def run(self, host=None, port=None, debug=None, load_dotenv=True, **options):
        if not self.debug or os.getenv('WERKZEUG_RUN_MAIN') == 'true':
            with self.app_context():
                setupSlack()
                getSeverityLevel()
        super(MyFlaskApp, self).run(host=host, port=port, debug=debug, load_dotenv=load_dotenv, **options)

app = MyFlaskApp(__name__)

#Non Api routes for the frontend
@app.route('/', methods=['GET'])
def root():
    global globalSeverityLevel, globalDictseverityLevels, globalLastChecked, globalLastUpdated
    severityLevelTitle = globalDictseverityLevels[globalSeverityLevel]["title"]
    severityLevelDefinition = globalDictseverityLevels[globalSeverityLevel]["def"]
    return render_template("index.html", severityLevel=severityLevelTitle,
        definition=severityLevelDefinition, lastChecked= globalLastChecked, lastUpdated=globalLastUpdated)

@app.route('/images/tile.png', methods=['GET'])
def getTile():
    global globalDictseverityLevels, globalSeverityLevel, globalTileSize
    bgcolor = globalDictseverityLevels[globalSeverityLevel]["bgcolor"]
    img = Image.new('RGB', globalTileSize, color = bgcolor)
    return send_file(generateTile(img), mimetype='image/png')

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

if __name__ == '__main__':
        app.run(host='0.0.0.0', debug=False)
