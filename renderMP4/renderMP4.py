import math, json, logging, xmltodict, copy, sqlite3, re
from datetime            import datetime, timezone, timedelta
from pathlib             import Path
from dataclasses import dataclass, fields
from io import BytesIO
import cairosvg
import numpy as np
from PIL import Image
from moviepy import VideoClip

from trias_crawl.lineStations import linesStations
from trias_crawl.crawler import Journey, Stop, LiveJourney, JourneyProcessError

logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
dataFormatRevision     = "2026.03.11"


@dataclass
class JourneyDefaultInit(Journey):
    pass

@dataclass
class StopDefaultInit(Stop):
    pass

stateCache = {
    "opdayBefore":    None,
    "opdayAfter":     None,
    "journeyObjList": None,
}

def get_stateAtTime(analysisDateTime):
    opdayBefore = analysisDateTime - timedelta(days=1)
    opdayBefore = opdayBefore.astimezone(timezone.utc)
    opdayBefore = opdayBefore.replace(hour=0, minute=0, second=0, microsecond=0)
    opdayBefore = int(opdayBefore.timestamp())

    opdayAfter  = analysisDateTime + timedelta(days=1)
    opdayAfter  = opdayAfter.astimezone(timezone.utc)
    opdayAfter  = opdayAfter.replace(hour=0, minute=0, second=0, microsecond=0)
    opdayAfter  = int(opdayAfter.timestamp())

    #check if cache is valid
    if stateCache["opdayBefore"] == opdayBefore and stateCache["opdayAfter"] == opdayAfter:
        journeyObjList = stateCache["journeyObjList"]
    else:
        connection         = sqlite3.connect(db_data_source)
        cursor             = connection.cursor()
        cursor.execute(f"SELECT * FROM journeys WHERE ?<=operatingDay AND operatingDay<=?;", (opdayBefore, opdayAfter))
        journeys           = cursor.fetchall()
        if not journeys:
            logging.info(f"no data in db for this timespan {opdayBefore} , {opdayAfter}")
            connection.close()
            return


        journeyObjList = []
        keysJourney = list(map(lambda x: x[0], cursor.description))
        for journeyData in journeys:
            journeyDict = dict()
            for keyIdx, key in enumerate(keysJourney):
                journeyDict[key] = journeyData[keyIdx]
            journeyRef      = journeyDict["journeyRef"]
            operatingDay    = journeyDict["operatingDay"]

            #get all stops
            cursor.execute(f"SELECT * FROM stops WHERE operatingDay=? AND journeyRef=? ORDER BY stopIndex ASC;", (operatingDay,journeyRef,))
            stops = cursor.fetchall()
            stopsList = []
            keysStop = list(map(lambda x: x[0], cursor.description))
            for stopData in stops:
                stopDict = dict()
                for keyIdx, key in enumerate(keysStop):
                    stopDict[key] = stopData[keyIdx]
                stopDict.pop("journeyRef")
                stopDict.pop("operatingDay")
                for depArrEventName in ["departureTimetable", "departureEstimate", "arrivalTimetable", "arrivalEstimate"]:
                    depArrEvent = stopDict.get(depArrEventName)
                    if depArrEvent:
                        stopDict[depArrEventName] = datetime.fromtimestamp(depArrEvent, tz=timezone.utc)
                    else:
                        stopDict[depArrEventName] = None
                stopsList.append(StopDefaultInit(**stopDict))
            journeyDict["stops"] = stopsList
            journeyDict["operatingDay"] = datetime.fromtimestamp(journeyDict["operatingDay"], tz=timezone.utc)
            journeyObjList.append(JourneyDefaultInit(**journeyDict))
        connection.close()
        #update cache
        stateCache["journeyObjList"] = journeyObjList
        stateCache["opdayBefore"]    = opdayBefore
        stateCache["opdayAfter"]     = opdayAfter

    allLiveJourneys = []
    for journeyObj in journeyObjList:
        try:
            liveJourn = LiveJourney(journeyObj, analysisDateTime)
            allLiveJourneys.append(liveJourn)
        except JourneyProcessError as e:
            pass
        except Exception as e:
            logging.error(f"could not initialize live journey {e} {journeyDict["journeyRef"]}")
    return allLiveJourneys

from trias_crawl.visualizeMap import *
cacheSvg = parseSvg("./trias_crawl/svg_source/live_map_source_light.svg")
def getLivemapSvg(runningTrainsDict, analysisDateTime):
    svgDict, linesPathDict, trainIconDict, _ = cacheSvg
    title = "Livekarte, aktualisiert "
    title += str(analysisDateTime.strftime('%d.%m.%Y %H:%M:%S'))
    changeMapTitle(svgDict, title)
    placeTrains(svgDict, linesPathDict, trainIconDict, runningTrainsDict.values())
    return xmltodict.unparse(svgDict, pretty=True)

def getMP4(startTime, endTime, frameRate = 30):
    def get_frame(t):
        analysisDateTime = timedelta(minutes = t*frameRate) + startTime
        print(analysisDateTime)
        state = get_stateAtTime(analysisDateTime)
        if state is None:
            state = {}
        svg = getLivemapSvg(state, analysisDateTime)
        png = cairosvg.svg2png(bytestring=svg.encode())
        return np.array(Image.open(BytesIO(png)).convert("RGB"))
    clip = VideoClip(get_frame, duration=(endTime-startTime).total_seconds()/60/frameRate)
    clip.write_videofile(f"{startTime}_{endTime}.mp4", fps=frameRate)

getMP4(datetime.now(timezone.utc
)-timedelta(hours=24), datetime.now(timezone.utc)-timedelta(hours=23))
