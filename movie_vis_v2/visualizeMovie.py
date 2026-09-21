import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
from datetime            import datetime, timezone, timedelta
from lineStations        import linesStations
from pathlib             import Path
from copy import deepcopy
import math, json, xmltodict, logging, copy, sqlite3, re
from dataclasses import dataclass, fields
import matplotlib.dates as mdates
import visualizeMap
from moviepy import VideoClip

logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
dataFormatRevision     = "2026.03.11"

inputSvgPath = "live_map_source_light.svg"

sBahnLineColors = {
    "S1": "#57ae41",
    "S2": "#ec1e2a",
    "S3": "#f27032",
    "S4": "#0066b3",
    "S5": "#00acdd",
    "S6": "#898d0b",
    "S60": "#844d00",
    "S62": "#c37930",
}
unknownLineColor = "#929598" #grey for all other unknown lines like S24
"""
def render_liveGraph(inputDataJsonPath, svgOutPath):
    sBahnDelays = {}
    with open(inputDataJsonPath) as inputfile:
        jsonData = json.loads(inputfile.read())
        if jsonData["info"]["attachedDataFormatRevision"] != dataFormatRevision:
            logging.error("incompatible json data file version")
            return
        runningTrainsDict = jsonData["journeys"]
    for journeyRef, journey in runningTrainsDict.items():
        if journey["isCancelled"]:
            sBahnDelays.setdefault(journey["lineName"], []).append(None)
        else:
            sBahnDelays.setdefault(journey["lineName"], []).append(journey["delayMinutes"])

    categories     = ["< 3", "3 - 5", "6 - 15", "> 15 Minuten", "ausgefallen"]
    categoryColors = ["#1de43c", "#e1e41d", "#e4801d", "#e41d22", "grey"]
    fig, ax = plt.subplots()

    sBahnDelayCatCounter = {}
    sBahnDelayAvg = {}
    sBahnDelayMax = {}
    for lineName, delays in dict(sorted(sBahnDelays.items())).items():
        delays = np.array(delays, dtype=float)
        sBahnDelayCatCounter[lineName] = [0,0,0,0,0]
        sBahnDelayAvg[lineName] = np.round(np.nanmean(delays), 1)
        sBahnDelayMax[lineName] = np.round(np.nanmax(delays),  1)
        for delay in delays:
            if np.isnan(delay):
                sBahnDelayCatCounter[lineName][4] += 1
            elif (delay < 3):
                sBahnDelayCatCounter[lineName][0] += 1
            elif (delay <= 5):
                sBahnDelayCatCounter[lineName][1] += 1
            elif (delay <= 15):
                sBahnDelayCatCounter[lineName][2] += 1
            else:
                sBahnDelayCatCounter[lineName][3] += 1

    delayCatArray2D = np.array(list(sBahnDelayCatCounter.values()))
    for catIdx, category in enumerate(categories):
        widths    = delayCatArray2D[:,catIdx]
        startVals = np.cumsum(list(sBahnDelayCatCounter.values()), axis=1)
        startVals = np.insert(startVals, 0, 0, axis=1)[:,catIdx]
        ax.barh(sBahnDelayCatCounter.keys(), widths, left=startVals, color=categoryColors[catIdx], label=category)

    ax.set_position([0.1, 0.20, 0.73, 0.70])
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin, xmax + 1)
    ax.set_xlabel("Zuganzahl")
    #ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    #ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.invert_yaxis() #warning, do not move, order matters!
    ax.grid(axis="x")
    ax.legend(loc='upper center', bbox_to_anchor=(0.55, -0.15), fancybox=True, shadow=True, ncol=5)

    #sbahn color boxes around y labels
    for label in ax.get_yticklabels():
        label.set_fontweight("bold")
        text = label.get_text()
        lineColor = sBahnLineColors.get(text, unknownLineColor)
        label.set_bbox(dict(
            boxstyle="round,pad=0.3",
            facecolor='none',
            edgecolor=lineColor,
            linewidth=3
        ))

    #average and max delays
    averageDelay = list(sBahnDelayAvg.values())
    maxDelay     = list(sBahnDelayMax.values())
    yTicks = ax.get_yticks()
    yLabelsFigCoord = fig.transFigure.inverted().transform(ax.transData.transform([(0, y) for y in yTicks]))
    for lineIdx, labelYPosition in enumerate(yLabelsFigCoord):
        fig.text(0.85, labelYPosition[1], f"ø: {averageDelay[lineIdx]}\nmax: {maxDelay[lineIdx]}", verticalalignment="center")

    #title
    dt = datetime.fromisoformat(jsonData['info']['responseTimestamp'].replace("Z", "+00:00"))
    pretty = dt.astimezone().strftime("%H:%M:%S am %d.%m.%Y")
    ax.set_title(f"Verspätung S-Bahn Stuttgart um {pretty}", fontsize=12, fontweight="bold")

    fig.savefig(svgOutPath)
"""

def render_mp4_for_date(startUnixTimestamp, endUnixTimestamp, outputSvgPath):
    #getting data around this
    startOpdayUnixTimestamp = startUnixTimestamp - 36*60*60 #one and a half day offset for operating day
    endOpdayUnixTimestamp   = endUnixTimestamp   + 36*60*60

    allTimestampsArray = np.arange(np.datetime64(startUnixTimestamp, "s"), np.datetime64(endUnixTimestamp, "s"), np.timedelta64(60, "s"))


    connection         = sqlite3.connect(db_data_source)
    cursor             = connection.cursor()
    cursor.execute(f"SELECT * FROM journeys WHERE ?<=operatingDay AND operatingDay<=?;", (startOpdayUnixTimestamp,endOpdayUnixTimestamp))
    journeys           = cursor.fetchall()
    journeys_fields    = [description[0] for description in cursor.description]
    operatingDays      = set([journey[0] for journey in journeys])

    cursor.execute(f"SELECT * FROM stops WHERE ?<=operatingDay AND operatingDay<=? ORDER BY journeyRef ASC, stopIndex ASC;", (min(operatingDays),max(operatingDays),))
    stops = cursor.fetchall()
    stops = np.array(stops)

    stopIndex   = stops[:, 2].astype(int) - 1
    maxNumStops = np.amax(stopIndex) + 1

    fields = [
        ("stopPointName",      "U100",          3, ""),
        ("stopPointRef",       "U50",           4, ""),
        ("isNotServiced",      "bool",          5, False),
        ("departureTimetable", "datetime64[s]", 6, np.datetime64("NaT")),
        ("departureEstimate",  "datetime64[s]", 7, np.datetime64("NaT")),
        ("arrivalTimetable",   "datetime64[s]", 8, np.datetime64("NaT")),
        ("arrivalEstimate",    "datetime64[s]", 9, np.datetime64("NaT")),
    ]
    dtype = [(name, nptype) for name, nptype, _, _ in fields]

    #unique filter for operatingDay and journeyReference
    journeyKeys = np.empty(len(stops),
        dtype = [
            ("operatingDay", "int64"),
            ("journeyRef",   "U100" ),
        ]
    )
    journeyKeys["operatingDay"] = stops[:, 0]
    journeyKeys["journeyRef"]   = stops[:, 1]
    uniqueJourneys, journeyPos  = np.unique(
        journeyKeys,
        return_inverse=True
    )

    #initialize array
    recordArray2d              = np.empty([len(uniqueJourneys), maxNumStops], dtype=dtype)
    for name, _, idx, default in fields:
        recordArray2d[name][:,:]                   = default
        recordArray2d[name][journeyPos, stopIndex] = stops[:, idx]

    #initialize svg
    svgDict, linesPathDict, trainIconDict, _ = visualizeMap.parseSvg(inputSvgPath)

    print(journeys_fields)

    def get_frame(t):
        analysisTime = np.datetime64(60*t*renderMinutesPerMovieSecond + startUnixTimestamp, "s")
        events = np.stack((recordArray2d["arrivalEstimate"],recordArray2d["departureEstimate"]), axis=2).reshape(recordArray2d.shape[0], -1)
        eventsDelta = events - analysisTime

        inFuture = ~np.isnat(eventsDelta) & (eventsDelta >= np.timedelta64(0, "s"))
        inPast   = ~np.isnat(eventsDelta) & (eventsDelta < np.timedelta64(0, "s"))
        journeyInProgress = np.any(inFuture, axis=1) & np.any(inPast, axis=1)

        nextEventIdx = np.argmax(inFuture[journeyInProgress], axis=1) #first index that is in the future
        prevEventIdx = maxNumStops*2 - 1 - np.argmax(inPast[journeyInProgress,::-1], axis=1)
        atStation    = (nextEventIdx % 2).astype("bool")              #true if at station, false if on track between

        if(np.sum(journeyInProgress)<1):
            return

        filteredEventsDelta = eventsDelta[journeyInProgress]
        arrivalMask         = np.arange(filteredEventsDelta.shape[1]) % 2 == 0
        arrivalInFuture     = ~np.isnat(filteredEventsDelta) & (filteredEventsDelta >= np.timedelta64(0, "s")) & arrivalMask[None, :]
        nextArrivalIdx      = np.argmax(arrivalInFuture[journeyInProgress], axis=1)

        recordArrayInProgress = recordArray2d[journeyInProgress]
        filteredEstimateEvents = events[journeyInProgress]
        filteredTimetableEvents = np.stack((recordArrayInProgress["arrivalTimetable"],recordArrayInProgress["departureTimetable"]), axis=2).reshape(recordArrayInProgress.shape[0], -1)

        rows = np.arange(len(prevEventIdx))
        timeBetweenStations = filteredEstimateEvents[rows,nextEventIdx] - filteredEstimateEvents[rows,prevEventIdx]
        timeAfterStation    = analysisTime - filteredEstimateEvents[rows,prevEventIdx]
        positionInterpol    = (timeAfterStation/timeBetweenStations)*(1-atStation) + (prevEventIdx//2)

        nextStopIdx = np.where(atStation, nextEventIdx, nextArrivalIdx)
        prevStopRef = recordArrayInProgress["stopPointRef"][rows, prevEventIdx//2]
        nextStopRef = recordArrayInProgress["stopPointRef"][rows, nextStopIdx//2]
        #print(f"recordArrayInProgress {recordArrayInProgress}")
        #print(f"interpol {positionInterpol}")

        #calculate delay
        delays = (filteredEstimateEvents[rows,prevEventIdx]-filteredTimetableEvents[rows,prevEventIdx]).astype("int")/60
        #print(f"delays {delays}")
        #print("\n")

        journeyRecords = [
            next(
                journey
                for journey in journeys
                if journey[0] == key["operatingDay"]
                and journey[1] == key["journeyRef"]
            )
            for key in uniqueJourneys[journeyInProgress]
        ]
        #print(journeyRecords)


        title = "Livekarte, aktualisiert "
        title += str(datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
        svgDictCopy = deepcopy(svgDict)
        visualizeMap.changeMapTitle(svgDictCopy, title)

        runningTrains = []
        for journeyIdx, journey in enumerate(journeyRecords):
            journDict = {}
            for fieldIdx, field in enumerate(journeys_fields):
                if field in ["lineName", "isCancelled", "origin", "destination", "incidentText"]:
                    journDict[field] = journey[fieldIdx]
            print(recordArrayInProgress["stopPointRef"].shape)
            print(prevEventIdx[journeyIdx]//2)
            print(nextEventIdx[journeyIdx]//2)
            journDict["currentStopRef"]   = str(prevStopRef[journeyIdx])
            journDict["nextStopRef"]      = str(nextStopRef[journeyIdx])
            journDict["delayMinutes"]     = delays[journeyIdx]
            journDict["progressNextStop"] = (positionInterpol%1)[journeyIdx]
            print(journDict)
            runningTrains.append(journDict)
        visualizeMap.placeTrains(svgDictCopy, linesPathDict, trainIconDict, runningTrains)
        png = cairosvg.svg2png(bytestring=xmltodict.unparse(svgDictCopy).encode())
        return np.array(Image.open(BytesIO(png)).convert("RGB"))
    renderDurationSeconds = allTimestampsArray[-1]-allTimestampsArray[0]
    renderMinutesPerMovieSecond = 60
    clip = VideoClip(get_frame, duration=(renderDurationSeconds/60)/renderMinutesPerMovieSecond)
    clip.write_videofile(f"{startUnixTimestamp}_{endUnixTimestamp}.mp4", fps=mp4fps)






#timestamp = int(datetime.now(timezone.utc).timestamp())
timestamp = 1773100800
render_mp4_for_date(timestamp-48*60*60, timestamp, "test.svg")
