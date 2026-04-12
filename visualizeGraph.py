import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
from datetime            import datetime, timezone, timedelta
from lineStations        import linesStations
from pathlib             import Path
import math, json, xmltodict, logging, copy, sqlite3, re
from crawler import Journey, Stop, LiveJourney, JourneyProcessError
from dataclasses import dataclass, fields
import matplotlib.dates as mdates

logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
dataFormatRevision     = "2026.03.11"


sBahnLineColors = {"S1": "#57ae41",
                  "S2": "#ec1e2a",
                  "S3": "#f27032",
                  "S4": "#0066b3",
                  "S5": "#00acdd",
                  "S6": "#898d0b",
                  "S60": "#844d00",
                  "S62": "#c37930"}
unknownLineColor = "#929598" #grey for all other unknown lines like S24

def render_liveGraph(inputDataJsonPath, svgOutPath):

    sBahnDelays = {}
    with open(inputDataJsonPath) as inputfile:
        jsonData = json.loads(inputfile.read())
        if jsonData["info"]["attachedDataFormatRevision"] != dataFormatRevision:
            logging.error("incompatible json data file version")
            return
        runningTrainsDict = jsonData["journeys"]
    for journeyRef, journey in runningTrainsDict.items():
        sBahnDelays.setdefault(journey["lineName"], []).append(journey["delayMinutes"])

    categories     = ["< 3 Min", "3 - 6 Min", "> 6 Min", "ausgefallen"]
    categoryColors = ["green", "orange", "red", "grey"]
    fig, ax = plt.subplots()

    sBahnDelayCatCounter = {}
    for lineName, delays in sBahnDelays.items():
        sBahnDelayCatCounter[lineName] = [0,0,0,0]
        for delay in delays:
            if delay is None:
                sBahnDelayCatCounter[lineName][3] += 1
            elif (delay < 3):
                sBahnDelayCatCounter[lineName][0] += 1
            elif (3 <= delay) and (delay < 6):
                sBahnDelayCatCounter[lineName][1] += 1
            else:
                sBahnDelayCatCounter[lineName][2] += 1
    sBahnDelayCatCounter = dict(sorted(sBahnDelayCatCounter.items()))
    array2D = np.array(list(sBahnDelayCatCounter.values()))
    for catIdx, category in enumerate(categories):
        widths    = array2D[:,catIdx]
        startVals = np.cumsum(list(sBahnDelayCatCounter.values()), axis=1)
        startVals = np.insert(startVals, 0, 0, axis=1)[:,catIdx]
        ax.barh(sBahnDelayCatCounter.keys(), widths, left=startVals, color=categoryColors[catIdx], label=category)

    ax.set_position([0.1, 0.15, 0.73, 0.75])
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.invert_yaxis() #warning, do not move, order matters!
    ax.grid(axis="x")
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.07), fancybox=True, shadow=True, ncol=5)

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
    averageDelay = np.round(np.mean(array2D, axis=1), 2)
    maxDelay = np.round(np.max(array2D, axis=1), 2)
    yTicks = ax.get_yticks()
    yLabelsFigCoord = fig.transFigure.inverted().transform(ax.transData.transform([(0, y) for y in yTicks]))
    for lineIdx, labelYPosition in enumerate(yLabelsFigCoord):
        fig.text(0.85, labelYPosition[1], f"ø: {averageDelay[lineIdx]}\nmax: {maxDelay[lineIdx]}", verticalalignment="center")

    #title
    dt = datetime.fromisoformat(jsonData['info']['responseTimestamp'].replace("Z", "+00:00"))
    pretty = dt.astimezone().strftime("%H:%M:%S am %d.%m.%Y")
    ax.set_title(f"Verspätung S-Bahn Stuttgart um {pretty}", fontsize=12, fontweight="bold")

    fig.savefig(svgOutPath)


@dataclass
class JourneyDefaultInit(Journey):
    pass

@dataclass
class StopDefaultInit(Stop):
    pass

def render_statGraph(startDay, endDay, outputSvgPath):
    def get_stateAtTime(analysisDateTime):
        operatingDayBefore = analysisDateTime - timedelta(days=1)
        operatingDayBefore = operatingDayBefore.astimezone(timezone.utc)
        operatingDayBefore = operatingDayBefore.replace(hour=0, minute=0, second=0, microsecond=0)
        operatingDayBefore = int(operatingDayBefore.timestamp())

        operatingDayAfter  = analysisDateTime + timedelta(days=1)
        operatingDayAfter  = operatingDayAfter.astimezone(timezone.utc)
        operatingDayAfter  = operatingDayAfter.replace(hour=0, minute=0, second=0, microsecond=0)
        operatingDayAfter = int(operatingDayAfter.timestamp())

        connection         = sqlite3.connect(db_data_source)
        cursor             = connection.cursor()
        cursor.execute(f"SELECT * FROM journeys WHERE ?<=operatingDay AND operatingDay<=?;", (operatingDayBefore,operatingDayAfter))
        journeys           = cursor.fetchall()
        if not journeys:
            logging.info(f"not data in db for this timespan {operatingDayBefore} , {operatingDayAfter}")
            connection.close()
            return

        allLiveJourneys    = []

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
                departureTimetable = stopDict.get("departureTimetable")
                departureEstimate  = stopDict.get("departureEstimate")
                arrivalTimetable   = stopDict.get("arrivalTimetable")
                arrivalEstimate    = stopDict.get("arrivalEstimate")
                stopDict["departureTimetable"] = datetime.fromtimestamp(departureTimetable, tz=timezone.utc) if departureTimetable else None
                stopDict["departureEstimate"]  = datetime.fromtimestamp(departureEstimate, tz=timezone.utc) if departureEstimate else None
                stopDict["arrivalTimetable"]   = datetime.fromtimestamp(arrivalTimetable, tz=timezone.utc) if arrivalTimetable else None
                stopDict["arrivalEstimate"]    = datetime.fromtimestamp(arrivalEstimate, tz=timezone.utc) if arrivalEstimate else None
                stopsList.append(StopDefaultInit(**stopDict))
            journeyDict["stops"] = stopsList
            journeyDict["operatingDay"] = datetime.fromtimestamp(journeyDict["operatingDay"], tz=timezone.utc)
            journeyObj = JourneyDefaultInit(**journeyDict)
            try:
                liveJourn = LiveJourney(journeyObj, analysisDateTime)
                allLiveJourneys.append(liveJourn)
            except JourneyProcessError as e:
                pass
        connection.close()
        return allLiveJourneys
    timesteps = np.arange(startDay, endDay, np.timedelta64(30, 'm'))
    averageDelayAllLines = []
    maxDelayAllLines     = []
    averageDelayPerLine  = dict()
    for timeIdx, time in enumerate(timesteps):
        print(time)
        time  = time.item().replace(tzinfo=timezone.utc)
        state = get_stateAtTime(time)
        currentTimestepDelayDict = {}
        for livejourn in state:
            currentTimestepDelayDict.setdefault(livejourn.lineName, []).append(livejourn.delayMinutes)
        allDelaysCombined = list(currentTimestepDelayDict.values())
        allDelaysCombined = [delay for lineDelay in allDelaysCombined for delay in lineDelay]
        averageDelayAllLines.append(np.mean(allDelaysCombined))
        maxDelayAllLines.append(np.max(allDelaysCombined) if allDelaysCombined else None)

        for newLineName in [lineName for lineName in currentTimestepDelayDict.keys() if lineName not in averageDelayPerLine.keys()]:
            averageDelayPerLine[newLineName] = [] + [None] * timeIdx
        for lineName in averageDelayPerLine.keys():
            if lineName not in currentTimestepDelayDict.keys():
                averageDelayPerLine[lineName].append(None)
            else:
                averageDelayPerLine[lineName].append(np.mean(currentTimestepDelayDict[lineName]))

    averageDelayPerLine = dict(sorted(averageDelayPerLine.items()))
    for lineName, delayTimestepList in averageDelayPerLine.items():
        print(f"{lineName} {len(delayTimestepList)}")

    fig, axs = plt.subplots(len(averageDelayPerLine)+1)
    axs[0].plot(timesteps, averageDelayAllLines, label="Alle Linien", color="black")
    axs[0].legend(loc="upper right")
    for axsIdx, (lineName, delaysOnLine) in enumerate(averageDelayPerLine.items()):
        color = sBahnLineColors.get(lineName, unknownLineColor)
        axs[axsIdx+1].plot(timesteps, delaysOnLine, label=f"{lineName}", color=color, linewidth=3)
        axs[axsIdx+1].legend(loc="upper right")
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y\n%H:%M'))
    plt.gcf().autofmt_xdate()  # dreht Labels automatisch
    fig.supylabel("Durchschnittsverspätung in Minuten")
    fig.tight_layout(pad=1.0)
    plt.subplots_adjust(hspace=0.4)
    plt.show()

    plt.figure()
    plt.plot(timesteps, maxDelayAllLines, label="Maximalverspätung")
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y\n%H:%M'))
    plt.gcf().autofmt_xdate()  # dreht Labels automatisch
    plt.legend()
    plt.show()


now       = datetime.now().astimezone()
yesterday = now+timedelta(days=-1)

render_statGraph(yesterday, now, "output.svg")
