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
from svgpathtools        import parse_path, Line, CubicBezier, Arc

logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
inputSvgPath           = "universal_map_light.svg"
inputLegendSvgPath     = "legendDelay.svg"

def importLegend(posX, posY, svgPath):
    with open(svgPath, "r") as svgFile:
        importSvg = svgFile.read()
    importSvgDict = xmltodict.parse(importSvg, force_list=["g", "path", "text"])
    legendGroup = {"@id": "legend", "@transform": f"translate({posX},{posY})"}
    importedDict = importSvgDict["svg"]
    for key, value in importedDict.items():
        if key in ["path", "g", "rect"]:
            legendGroup[key] = value
    return legendGroup


def svgAnimatedTitle(startDatetime, endDatetime, timeCompression,
    offsetX = 500, offsetY = 150,
    textSize = 80):

    digitSpacing = textSize*0.55
    colonSpacing = textSize*0.3

    textElementsList = []
    textTemplateDict = {"@font-size": str(textSize), "@font-familiy": "sans-serif", "@x":None, "@y":offsetY, "#text": None, "@visibility": "hidden", "@fill": "#000000"}

    #calculate total duration
    repeatDurSec = (endDatetime-startDatetime).total_seconds()
    if repeatDurSec > 24*60*60:
        raise ValueError("Date range is larger than maximum supported timespan")
    repeatDurSec /= timeCompression

    #place title
    titleText = "Animierte S-Bahn Livekarte für Stuttgart am"
    textDict = textTemplateDict.copy()
    textDict["@x"] = offsetX
    textDict["@visibility"] = "visible"
    textDict["#text"] = titleText
    textElementsList.append(textDict)
    offsetX += textSize*0.51*len(titleText)

    #display date
    startDateStr = startDatetime.strftime("%d.%m.%Y")
    firstDayMidnight= (startDatetime + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    firstDayLen = (firstDayMidnight - startDatetime).total_seconds()/timeCompression
    endDateStr   = endDatetime.strftime("%d.%m.%Y")
    for startOrEndIdx, text in enumerate([startDateStr, endDateStr]):
        textDict = textTemplateDict.copy()
        textDict["@x"]      = offsetX
        textDict["#text"]   = text
        textDict["animate"] = {
            "@attributeName": "visibility",
            "@values":        ";".join(["visible","hidden"][::(1-startOrEndIdx*2)]),
            "@keyTimes":      ";".join(["0", str(firstDayLen/repeatDurSec)]),
            "@calcMode":      "discrete",
            "@begin":         f"{0}s",
            "@dur":           f"{repeatDurSec}s",
            "@repeatDur":     f"{repeatDurSec}s",
            "@fill":          "freeze",
        }
        textElementsList.append(textDict)
    offsetX += textSize*0.55*len(endDateStr)

    #clock
    #colons
    for digitX in [2*digitSpacing,4*digitSpacing+colonSpacing]:
        textDict = textTemplateDict.copy()
        textDict["@x"]          = digitX+offsetX
        textDict["@visibility"] = "visible"
        textDict["#text"]       = ":"
        textElementsList.append(textDict)
    #variable digits
    sinceMidnightSec = startDatetime.hour*60*60 + startDatetime.minute*60 + startDatetime.second
    digitDataList = [
        {"duration": 24*60*60, "step": 10*60*60, "startDigit": startDatetime.hour//10 }, #hour
        {"duration": 24*60*60, "step": 60*60 ,   "startDigit": startDatetime.hour%10  }, #hour
        {"duration": 60*60,    "step": 10*60,    "startDigit": startDatetime.minute//10 }, #minute
        {"duration": 10*60,    "step": 60 ,      "startDigit": startDatetime.minute%10  }, #minute
        {"duration": 60,       "step": 10,       "startDigit": startDatetime.second//10 }, #second
        {"duration": 10,       "step": 1 ,       "startDigit": startDatetime.second%10  }, #second
    ]
    sinceMidnightSec /= timeCompression
    for digitIdx, digitData in enumerate(digitDataList):
        digitData["posX"] = offsetX+digitIdx*digitSpacing+digitIdx//2*colonSpacing
        digitData["duration"] /= timeCompression
        digitData["step"] /= timeCompression
        maxDigit = min(10, math.ceil(digitData["duration"]/digitData["step"]))
        for digit in range(maxDigit):
            #calculate how long the individual digit is shown
            remainingDurationForDigit = max(0, (digit+1)*digitData['step'] - digitData['duration'])
            shownForNSec = digitData["step"] - remainingDurationForDigit
            #calculate if digit has to be shown multiple times, like lower hour digit 1 (01, 11, 21)
            numOccurences = (math.ceil(digitData["duration"]/digitData["step"]))/maxDigit
            numOccurences = math.floor(numOccurences + (maxDigit-1-digit)/maxDigit)
            keyTimes = []
            for occIdx in range(numOccurences):
                keyTimes.append(occIdx * maxDigit*digitData['step']/ digitData['duration'])
                keyTimes.append((shownForNSec +occIdx * maxDigit*digitData['step'])/ digitData['duration'])
            keyTimes = [str(time) for time in keyTimes]
            values = ["visible", "hidden"]*numOccurences
            beginSec = (-sinceMidnightSec+digit*digitData['step'])%digitData['duration']
            beginSec -= digitData['duration']
            textDict = textTemplateDict.copy()
            textDict["@x"]      = digitData["posX"]
            textDict["#text"]   = digit
            textDict["animate"] = {
                "@attributeName": "visibility",
                "@values":        ";".join(values),
                "@keyTimes":      ";".join(keyTimes),
                "@calcMode":      "discrete",
                "@begin":         f"{beginSec}s",
                "@dur":           f"{digitData["duration"]}s",
                "@repeatDur":     f"{repeatDurSec-beginSec}s",
                "@repeatCount":   "indefinite",
                "@fill":          "freeze",
            }
            textElementsList.append(textDict)
    offsetX += 6*digitSpacing + 3*colonSpacing

    #place timezone text
    textDict = textTemplateDict.copy()
    textDict["@x"] = offsetX
    textDict["@visibility"] = "visible"
    textDict["#text"] = "UTC"
    textElementsList.append(textDict)
    return textElementsList


def interpolateDelayColor(delayArray):
    colors = np.array([
        [29, 228, 60],
        [225, 228, 29],
        [228, 128, 29],
        [228, 29, 34]
    ])
    channels = [np.interp(delayArray, [0,3,6,15], colors[:, i]) for i in range(3)]
    rgbArray = np.rint(np.column_stack(channels)).astype(np.uint8)
    return np.array([f"#{r:02X}{g:02X}{b:02X}" for r, g, b in rgbArray])

    return rgbArray

def getPathStationLengthRatio(linesPathDict, lineName, stationRef):
    segmBetweenStops = 3
    if lineName not in linesPathDict.keys():
        print("unknown line!!!")
        return 0.0
    linePath = linesPathDict[lineName]
    parsedPath = parse_path(linePath["@d"])
    for stationIdx, station in enumerate(linesStations[lineName]):
        if station[0] in stationRef:
            break
    stationSegmentIdx       = segmBetweenStops*stationIdx
    pathLengthBeforeStation = [parsedPath[idx].length() for idx in range(stationSegmentIdx)]
    totalPathLength         = [segment.length() for segment in parsedPath]
    return sum(pathLengthBeforeStation) / sum(totalPathLength)

def remove_center_duplicates(timestamps, values):
    mask = np.ones(len(values), dtype=bool)
    mask[1:-1] = (
        (values[1:-1] != values[:-2]) |
        (values[1:-1] != values[2:])
    )
    return timestamps[mask], values[mask]

def render_mp4_for_date(startUnixTimestamp, endUnixTimestamp, timeCompression, outputSvgPath):
    #getting data around this
    startOpdayUnixTimestamp = startUnixTimestamp - 36*60*60 #one and a half day offset for operating day
    endOpdayUnixTimestamp   = endUnixTimestamp   + 36*60*60

    connection         = sqlite3.connect(db_data_source)
    cursor             = connection.cursor()
    cursor.execute("""
        SELECT j.*, s.*
        FROM journeys AS j
        JOIN stops    AS s
        ON    j.operatingDay = s.operatingDay
        AND   j.journeyRef   = s.journeyRef
        WHERE j.operatingDay BETWEEN ? AND ?
        ORDER BY j.operatingDay, j.journeyRef, s.stopIndex
    """, (startOpdayUnixTimestamp, endOpdayUnixTimestamp))
    journeysAndStops = np.array(cursor.fetchall())
    fieldNames = [description[0] for description in cursor.description]
    #split again into journey information and stop information arrays
    stopIndex   = journeysAndStops[:, fieldNames.index("stopIndex")].astype(int) - 1 #from 1 indexed to 0 indexed
    maxNumStops = np.amax(stopIndex) + 1
    opDayAndRef = np.asarray(journeysAndStops[:, :2], dtype="U100")
    uniqueJourneyKeys, uniqueIndices, stopToJourneyMapping = np.unique(opDayAndRef[:, :2], axis=0, return_index=True, return_inverse=True)
    stopArrayFields = [
        ("stopPointName",      "U100",          ""),
        ("stopPointRef",       "U50",           ""),
        ("isNotServiced",      "bool",          False),
        ("departureTimetable", "datetime64[s]", np.datetime64("NaT")),
        ("departureEstimate",  "datetime64[s]", np.datetime64("NaT")),
        ("arrivalTimetable",   "datetime64[s]", np.datetime64("NaT")),
        ("arrivalEstimate",    "datetime64[s]", np.datetime64("NaT")),
    ]
    dtype = [(name, nptype) for name, nptype,  _ in stopArrayFields]
    stopsArray2d = np.empty([len(uniqueJourneyKeys), maxNumStops], dtype=dtype)
    for name, _, default in stopArrayFields:
        sourceIdx = fieldNames.index(name)
        stopsArray2d[name][:,:]                             = default
        stopsArray2d[name][stopToJourneyMapping, stopIndex] = journeysAndStops[:, sourceIdx]
    journeysArray = journeysAndStops[uniqueIndices]

    #initialize svg
    print(f"inputSvgPath {inputSvgPath}")
    svgDict, linesPathDict, trainIconDict, _ = visualizeMap.parseSvg(inputSvgPath)
    pathList = []
    """
    for journeyIdx, journey in enumerate(journeysArray):
        print(journey[fieldNames.index("journeyRef")])
        stops = stopsArray2d[journeyIdx]
        filterDep = ~np.isnan(stops["departureEstimate"])
        filterArr = ~np.isnan(stops["arrivalEstimate"])
        depEs = (stops["departureEstimate"][filterDep].astype(int) - startUnixTimestamp)
        arrEs = (stops["arrivalEstimate"][filterArr].astype(int)   - startUnixTimestamp)
        depEsDel = (stops["departureEstimate"][filterDep].astype(int) - stops["departureTimetable"][filterDep].astype(int))/60
        arrEsDel = (stops["arrivalEstimate"][filterArr].astype(int)   - stops["arrivalTimetable"][filterArr].astype(int))/60

        #todo eliminate Nan values, that get mapped to int
        #select path, and get progress in said path
        stopRef = stops["stopPointRef"]
        lineName = journey[fieldNames.index("lineName")]

        interleavedTimestamps = np.empty(len(depEs)*2, dtype=int)
        if len(depEs) != len(arrEs):
            print("unequelLen!")
            continue
        interleavedTimestamps[0::2] = depEs
        interleavedTimestamps[1::2] = arrEs
        if np.any(interleavedTimestamps < 0):
            print("skip, one station too early")
            continue
        if np.any(interleavedTimestamps > int(endUnixTimestamp-startUnixTimestamp)):
            print("skip, one station too late")
            continue

        interleavedDelays = np.empty(interleavedTimestamps.shape, dtype=int)
        interleavedDelays[0::2] = depEsDel
        interleavedDelays[1::2] = arrEsDel

        pathKeyframes = np.empty(interleavedTimestamps.shape, dtype=float)
        delayColors   = interpolateDelayColor(interleavedDelays)
        for tsIdx, timestamp in enumerate(interleavedTimestamps):
            stopReference = stopRef[int((tsIdx+1)//2)]
            pathKeyframes[tsIdx] = getPathStationLengthRatio(linesPathDict, lineName, stopReference)
        pathId = lineName #todo change this to handle lines like S42
        animationStartTimeSec = interleavedTimestamps[0] / timeCompression
        animationDorationSec  = (interleavedTimestamps[-1] - interleavedTimestamps[0]) / timeCompression
        #determine icon rotation
        resolvedLineName, cIdx, nIdx = visualizeMap.getStopIndices(lineName, linesPathDict, stopRef[0], stopRef[1])
        if (cIdx < nIdx):
            symbolRotation = "auto"
        else:
            symbolRotation = "auto-reverse"
        animateVisibilityDict = {
            "@attributeName": "visibility",
            "@begin":         f"{animationStartTimeSec}s",
            "@dur":           f"{animationDorationSec}s",
            "@fill":          "remove", #restore original state
            "@values":        "visible",
            "@repeatCount":   1,
        }
        colorTimestamp, delayColors = remove_center_duplicates(interleavedTimestamps, delayColors)
        colorTimestamp = np.round((colorTimestamp-colorTimestamp[0])/(colorTimestamp[-1]-colorTimestamp[0]), 4)
        animateColorDict = {
            "@attributeName": "fill",
            "@begin":         f"{animationStartTimeSec}s",
            "@dur":           f"{animationDorationSec}s",
            "@keyTimes":      ";".join(colorTimestamp.astype(str)),
            "@values":        ";".join(delayColors),
            "@fill":          "remove", #keep final state of animation
            "@repeatCount":   1,
        }
        pathTimestamp, pathKeyframes = remove_center_duplicates(interleavedTimestamps, pathKeyframes)
        pathTimestamp = np.round((pathTimestamp-pathTimestamp[0])/(pathTimestamp[-1]-pathTimestamp[0]), 4)
        animateMotionDict = {
            "mpath":        {"@href": "#"+pathId},
            "@begin":       f"{animationStartTimeSec}s",
            "@dur":         f"{animationDorationSec}s",
            "@calcMode":    "linear",
            "@keyTimes":    ";".join(pathTimestamp.astype(str)),
            "@keyPoints":   ";".join(pathKeyframes.astype(str)),
            "@rotate":      symbolRotation,
            "@fill":        "remove", #keep final state of animation
            "@repeatCount": 1,
        }
        pathDict = {
            "@style": "fill:#11ff0a;stroke:#000000;stroke-width:1;stroke-linecap:square;stroke-linejoin:round;visibility:hidden",
            "@d": "M 20,0 -20,-15 -12,0 -20,15 z",
            "animate": [animateVisibilityDict, animateColorDict],
            "animateMotion": animateMotionDict,
        }
        pathList.append(pathDict)
        #print(pathDict)
    svgDict["svg"]["g"].append({
        "@id": "arrows",
        "path": pathList,
    })
    """

    #clock and title
    startDatetime = datetime.fromtimestamp(startUnixTimestamp, timezone.utc)
    endDatetime   = datetime.fromtimestamp(endUnixTimestamp, timezone.utc)
    svgDict["svg"]["g"].append({
        "@id": "title",
        "text": svgAnimatedTitle(startDatetime, endDatetime, timeCompression),
    })

    #legend
    svgDict["svg"]["g"].append(importLegend(50, 250, inputLegendSvgPath))

    #export
    with open("testAnimated.svg", "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))
        """"

        title = "Livekarte, aktualisiert "
        title += str(analysisTime.astype(datetime).strftime('%d.%m.%Y %H:%M:%S'))
        svgDictCopy = deepcopy(svgDict)
        visualizeMap.changeMapTitle(svgDictCopy, title)
    """


#timestamp = int(datetime.now(timezone.utc).timestamp())
timestamp = 1773100800
timeCompression = 600
render_mp4_for_date(timestamp-24*60*60, timestamp, timeCompression, "test.svg")
