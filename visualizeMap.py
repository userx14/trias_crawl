from svgpathtools        import parse_path, Line, CubicBezier, Arc
from svgpathtools        import Path as SvgPath
from svgpathtools.parser import parse_transform
from svgpathtools.path   import translate, rotate, scale
from datetime            import datetime, timezone, timedelta
from lineStations        import linesStations
from pathlib             import Path
import math, json, xmltodict, logging, copy, sqlite3, re

logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
dataFormatRevision     = "2026.03.11"
segmBetweenStops       = 3

def changeMapTitle(svgDict, newTitle):
    if isinstance(svgDict["svg"]["text"], list):
        for textElement in svgDict["svg"]["text"]:
            if textElement["@id"] == "title":
                textElement["#text"] = newTitle
                break
        else:
            logging.error("could not locate map title")
    elif "@id" in svgDict["svg"]["text"].keys() and svgDict["svg"]["text"]["@id"] == "title":
        svgDict["svg"]["text"]["#text"] = newTitle
    else:
        logging.error("could not locate map title")

def parseColormap(svgDict, colormapDict):
    floatRegex     = r"([+-]?([0-9]*[.])?[0-9]+)"
    minLegendText  = colormapDict["colormap_minText"]["tspan"]["#text"]
    minLegendValue = float(re.search(floatRegex, minLegendText).group(1))

    maxLegendText  = colormapDict["colormap_maxText"]["tspan"]["#text"]
    maxLegendValue = float(re.search(floatRegex, maxLegendText).group(1))

    gradientName = re.search(r"stroke:url\(#([\w]+)\)", colormapDict["colormap_gradient"]["@style"]).group(1)
    for gradient in svgDict["svg"]["defs"]["linearGradient"]:
        if gradientName == gradient["@id"]:
            gradientName = gradient["@xlink:href"][1:]
            break
    else:
        raise ValueError("Invalid gradient definition")
    for gradient in svgDict["svg"]["defs"]["linearGradient"]:
        if gradientName == gradient["@id"]:
            break
    else:
        raise ValueError("Invalid gradient definition")
    stopValues = []
    stopColors = []
    for stop in gradient["stop"]:
        stopColors.append(re.search(r"stop-color:(#[0-9a-fA-F]{6})", stop["@style"]).group(1))
        stopValues.append(float(stop["@offset"])*(maxLegendValue-minLegendValue)+minLegendValue)
    return makeColormap(stopValues, stopColors)

def parseSvg(inputSvgPath):
    with open(inputSvgPath, "r") as inputSvg:
        svgFile = inputSvg.read()
    svgDict = xmltodict.parse(svgFile, force_list=["g", "path", "text"])
    trainIconIds  = ["delay0", "delay3", "delay6", "delay15"]
    trainIconDict = dict()
    lineIds       = ["S1", "S2", "S3", "S4", "S5", "S6", "S60", "S62"]
    linesPathDict = dict()
    colormapIds   = ["colormap_gradient", "colormap_minText", "colormap_maxText"]
    colormapDict  = dict()
    #search for SBahn Line Paths and Train Arrows and store references
    for path in svgDict["svg"]["path"]: #in root paths
        pathId = path["@id"]
        if pathId in trainIconIds:
            trainIconDict[pathId] = path
        if pathId in lineIds:
            linesPathDict[pathId] = path
        if pathId in colormapIds:
            colormapDict[pathId]  = path
    for text in svgDict["svg"]["text"]:
        textId = text["@id"]
        if textId in colormapIds:
            colormapDict[textId] = text
    for group in svgDict["svg"]["g"]: #in paths that are grouped
        if "path" in group.keys():
            for path in group["path"]:
                if "@id" not in path.keys():
                    continue
                pathId = path["@id"]
                if pathId in trainIconIds:
                    trainIconDict[pathId] = path
                if pathId in lineIds:
                    linesPathDict[pathId] = path
                if pathId in colormapIds:
                    colormapDict[pathId]  = path
        if "text" in group.keys():
            for text in group["text"]:
                textId = text["@id"]
                if textId in colormapIds:
                    colormapDict[textId] = text

    colormap = None
    if colormapDict:
        colormap = parseColormap(svgDict, colormapDict)

    if len(lineIds) != len(linesPathDict):
        raise ValueError("Missing line or icon in svg")

    if len(trainIconIds) != len(trainIconDict):
        trainIconDict = None
    return svgDict, linesPathDict, trainIconDict, colormap


def findStationNumber(lineName, stationRefOrName):
    if lineName not in linesStations.keys():
        return None #line not found
    currentLineStations = linesStations[lineName]
    stationRefList      = [station[0] for station in currentLineStations]
    stationNameList     = [station[1] for station in currentLineStations]
    if stationRefOrName in stationRefList:
        return stationRefList.index(stationRefOrName)
    elif stationRefOrName in stationNameList:
        return stationNameList.index(stationRefOrName)
    else:
        return None #station not found on this line

def getStopIndices(rawLineName, linesPathDict, currentStopRef, nextStopRef):
    currentStopRefWithoutPlatform = ":".join(currentStopRef.split(":")[:3])
    nextStopRefWithoutPlatform    = ":".join(nextStopRef.split(":")[:3])
    if nextStopRefWithoutPlatform ==  "de:08111:6115": #convert HBF oben to HBF tief
        nextStopRefWithoutPlatform = "de:08111:6118"
    if currentStopRefWithoutPlatform == "de:08111:6115": #convert HBF oben to HBF tief
        currentStopRefWithoutPlatform = "de:08111:6118"
    if rawLineName not in linesPathDict.keys():
        #handle replacement service
        #when line is S52, try to map to S5 and S2
        digits = [char for char in rawLineName if char.isdigit()]
        for digit in digits[:2]:
            lineName = "S"+digit
            currStationIdx = findStationNumber(lineName, currentStopRefWithoutPlatform)
            nextStationIdx = findStationNumber(lineName, nextStopRefWithoutPlatform)
            if (currStationIdx is None) or (nextStationIdx is None):
                continue
            break
        else:
            logging.error(f"Could not map train on line {lineName} to existing line")
            return None, None, None
    else:
        lineName = rawLineName
        currStationIdx = findStationNumber(lineName, currentStopRefWithoutPlatform)
        nextStationIdx = findStationNumber(lineName, nextStopRefWithoutPlatform)
        if currStationIdx is None:
            logging.error(f"Nonexistent stop {currentStopRefWithoutPlatform} on line {lineName}")
            return None, None, None
        if nextStationIdx is None:
            logging.error(f"Nonexistent stop {nextStopRefWithoutPlatform} on line {lineName}")
            return None, None, None
    return lineName, currStationIdx, nextStationIdx

def getStationPosAndTangFromPath(lineName, linesPathDict, currStationIdx):
    currentLineStations = linesStations[lineName]
    linePath = linesPathDict[lineName]
    parsedPath = parse_path(linePath["@d"])
    segmentIdx = segmBetweenStops*currStationIdx
    if segmentIdx != len(parsedPath):
        activeSegment = parsedPath[segmentIdx]
        position = activeSegment.point(0)
        tangent = activeSegment.derivative(1)
    else:
        activeSegment = parsedPath[segmentIdx - 1]
        position = activeSegment.point(1)
        tangent = activeSegment.derivative(1)
    return position, tangent

def makeColormap(stops, colors):
    colors = [tuple(int(c[i:i+2], 16) for i in (1, 3, 5)) for c in colors]
    def cmap(x):
        if x <= stops[0]:
            rgb = colors[0]
        elif x >= stops[-1]:
            rgb = colors[-1]
        else:
            for i in range(len(stops) - 1):
                if stops[i] <= x <= stops[i+1]:
                    t = (x - stops[i]) / (stops[i+1] - stops[i])
                    rgb = tuple(int(colors[i][j] + t * (colors[i+1][j] - colors[i][j])) for j in range(3))
                    break
        return "#{:02x}{:02x}{:02x}".format(*rgb)
    return cmap

def analyze_data(callbackAnalysis, analysisDayStart, analysisDayEnd, perJourneyCallback = False):
    analysisDayStart = analysisDayStart.astimezone(timezone.utc)
    analysisDayEnd   = analysisDayEnd.astimezone(timezone.utc)
    analysisDayStart = analysisDayStart.replace(hour=0, minute=0, second=0, microsecond=0)
    analysisDayEnd   = analysisDayEnd.replace(hour=0, minute=0, second=0, microsecond=0)
    analysisDayStart = int(analysisDayStart.timestamp())
    analysisDayEnd   = int(analysisDayEnd.timestamp())
    connection       = sqlite3.connect(db_data_source)
    cursor           = connection.cursor()
    cursor.execute(f"SELECT * FROM journeys WHERE ?<=operatingDay AND operatingDay<=?;", (analysisDayStart,analysisDayEnd))
    journeys    = cursor.fetchall()
    if not journeys:
        logging.info(f"not data in db for this timespan")
        connection.close()
        return
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
        keysStop = list(map(lambda x: x[0], cursor.description))
        if perJourneyCallback:
            stopDictList = []
            for stopData in stops:
                stopDict = dict()
                for keyIdx, key in enumerate(keysStop):
                    stopDict[key] = stopData[keyIdx]
                stopDictList.append(stopDict)
            callbackAnalysis(journeyDict, stopDictList)
        else:
            for stopData in stops:
                stopDict = dict()
                for keyIdx, key in enumerate(keysStop):
                    stopDict[key] = stopData[keyIdx]
                callbackAnalysis(journeyDict, stopDict)
    connection.close()


def placeStationInfo(svgDict, linesPathDict, lineName, stationIdx, colormap, value, hoverText, direction=None):
    circleRad = 8
    position, tangent = getStationPosAndTangFromPath(lineName, linesPathDict, stationIdx)
    if direction == None:
        if "circle" not in svgDict["svg"].keys():
            svgDict["svg"]["circle"] = []
        circle = {
            "@cx":   position.real,
            "@cy":   position.imag,
            "@r":    str(circleRad),
            "@fill": colormap(value),
            "title": hoverText
        }
        svgDict["svg"]["circle"].append(circle)
        return
    tangent /= abs(tangent)
    if direction == "Fw":
        startPos = position+tangent*circleRad
        endPos   = position-tangent*circleRad
    elif direction == "Bw":
        startPos = position-tangent*circleRad
        endPos   = position+tangent*circleRad
    else:
        raise ValueError("unsupported direction argument")
    semicircleArc = Arc(start = startPos, radius = circleRad + 1j*circleRad, end = endPos,
                    rotation=0, large_arc=False, sweep=True)
    semicirclePath = SvgPath(semicircleArc, Line(start=endPos, end=startPos))
    semicirclePath.closed = True
    if "path" not in svgDict["svg"]:
        svgDict["svg"]["path"] = []

    svgDict["svg"]["path"].append({
        "@d":      semicirclePath.d(),
        "@fill":   colormap(value),
        "@stroke": "none",
        "title":   hoverText
    })
    return

def placeSectionInfo(svgDict, linesPathDict, lineName, stationIdx, colormap, value, hoverText, direction=None):
    def getPathNormal(segment):
        segment.derivative()

    def getOffsetPath(parsedPath, tangentialOffset):
        offsetPathResult = []
        for segment in parsedPath:
            if isinstance(segment, Line):
                complexDer = segment.derivative(0)
                complexDer /= abs(complexDer)
                offsetVec  = complex(complexDer.imag, -complexDer.real)*tangentialOffset
                newLine    = Line(segment.start+offsetVec, segment.end+offsetVec)
                offsetPathResult.append(newLine)
            elif isinstance(segment, CubicBezier):
                complexDerStart = segment.derivative(0)
                complexDerStart /= abs(complexDerStart)
                complexDerStart  = complex(complexDerStart.imag, -complexDerStart.real)*tangentialOffset

                complexDerMiddle = segment.derivative(0.5)
                complexDerMiddle /= abs(complexDerMiddle)
                complexDerMiddle = complex(complexDerMiddle.imag, -complexDerMiddle.real)*tangentialOffset

                complexDerEnd   = segment.derivative(1)
                complexDerEnd  /= abs(complexDerEnd)
                complexDerEnd    = complex(complexDerEnd.imag, -complexDerEnd.real)*tangentialOffset
                newCBezier = CubicBezier(
                    segment.start    + complexDerStart,
                    segment.control1 + complexDerMiddle,
                    segment.control2 + complexDerMiddle,
                    segment.end      + complexDerEnd)
                offsetPathResult.append(newCBezier)
            else:
                raise ValueError("unsupported path segment type")
        return offsetPathResult
    #find group that contains S-Bahn paths
    for group in svgDict["svg"]["g"]:
        if group["@id"] == "g2":
            break
    linePath = linesPathDict[lineName]
    parsedPath = parse_path(linePath["@d"])
    originalStrokeWidth = int(linePath["@stroke-width"])
    startSegmentIdx = segmBetweenStops*stationIdx
    if direction == None:
        newStrokeWidth = originalStrokeWidth
        dString        = SvgPath(*parsedPath[startSegmentIdx:startSegmentIdx+3]).d()
    elif direction == "Fw":
        newStrokeWidth = 0.5 * originalStrokeWidth
        offsetPath     = getOffsetPath(parsedPath, -(originalStrokeWidth-newStrokeWidth)/2)
        dString        = SvgPath(*offsetPath[startSegmentIdx:startSegmentIdx+3]).d()
    elif direction == "Bw":
        newStrokeWidth = 0.5 * originalStrokeWidth
        offsetPath     = getOffsetPath(parsedPath, (originalStrokeWidth-newStrokeWidth)/2)
        dString        = SvgPath(*offsetPath[startSegmentIdx:startSegmentIdx+3]).d()
    style = re.sub(r"stroke:[^;]+", f"stroke:{colormap(value)}", linePath["@style"])

    group["path"].append({
        "@d":            dString,
        "@stroke":       linePath["@stroke"],
        "@style":        style,
        "@stroke-width": str(newStrokeWidth),
        "title":         hoverText,
    })

def render_nonServStatMap(startDay, endDay, inputSvgPath, outputSvgPath):

    svgDict, linesPathDict, _, cmap = parseSvg(inputSvgPath)
    title = "Ungeplant ausgefallene Halte, "
    if startDay.date() == endDay.date():
        title += f"am {startDay.strftime('%d.%m.%Y')}"
    else:
        title += f"vom {startDay.strftime('%d.%m.%Y')} "
        title += f"bis {endDay.strftime('%d.%m.%Y')}"
    changeMapTitle(svgDict, title)

    #to store delay data
    delaySectionDict = copy.deepcopy(linesStations)
    for lineStations in delaySectionDict.values():
        for station in lineStations:
            station.append([])

    def notServAnalysisCallback(journeyDict, stopDict):
        rawLineName             = journeyDict["lineName"]
        lineName, stationIdx, _ = getStopIndices(rawLineName, linesPathDict, stopDict["stopPointRef"], stopDict["stopPointRef"])
        if stationIdx is None:
            return
        if stopDict["isNotServiced"] == True:
            delaySectionDict[lineName][stationIdx][2].append(1)
        else:
            delaySectionDict[lineName][stationIdx][2].append(0)

    analyze_data(notServAnalysisCallback, startDay, endDay)
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            if len(station[2]) != 0:
                notServSum    = sum(station[2])
                numberOfStops = len(station[2])
                notServPerc   = 100*notServSum/numberOfStops
                placeStationInfo(svgDict, linesPathDict, lineName, stationIdx, cmap, notServPerc, f"Ausgefallen: {round(notServPerc,2)}%")
    with open(outputSvgPath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))


def render_numberOfTrainsMap(startDay, endDay, inputSvgPath, outputSvgPath):
    svgDict, linesPathDict, _, cmap = parseSvg(inputSvgPath)
    title = "Anzahl Züge, "
    if startDay.date() == endDay.date():
        title += f"am {startDay.strftime('%d.%m.%Y')}"
    else:
        title += f"vom {startDay.strftime('%d.%m.%Y')} "
        title += f"bis {endDay.strftime('%d.%m.%Y')}"
    changeMapTitle(svgDict, title)

    #to store delay data, first list for tracks, second list for stations
    delaySectionDict = copy.deepcopy(linesStations)
    for lineStations in delaySectionDict.values():
        for station in lineStations:
            station.append(0)

    def delayAnalysisCallback(journeyDict, stopDictList):
        for currentStopIdx in range(len(stopDictList)-1):
            nextStopIdx = currentStopIdx + 1
            currentStopDict = stopDictList[currentStopIdx]
            nextStopDict = stopDictList[nextStopIdx]
            lineName, currentStationIdx, nextStationIdx = getStopIndices(journeyDict["lineName"], linesPathDict, currentStopDict["stopPointRef"], nextStopDict["stopPointRef"])
            if currentStationIdx < nextStationIdx:
                delaySectionDict[lineName][currentStationIdx][2] += 1
            else:
                delaySectionDict[lineName][nextStationIdx][2] += 1

    analyze_data(delayAnalysisCallback, startDay, endDay, perJourneyCallback = True)
    maxTrains = 0
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            maxTrains = max(maxTrains, station[2])
    if maxTrains == 0:
        logging.error("No data for number of trains")
        return
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            realtiveNumberOfTrains = station[2] / maxTrains
            placeSectionInfo(svgDict, linesPathDict, lineName, stationIdx, cmap, realtiveNumberOfTrains, None)

    with open(outputSvgPath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))

def render_delayChangeMap(startDay, endDay, inputSvgPath, outputSvgPath):
    svgDict, linesPathDict, _, cmap = parseSvg(inputSvgPath)
    title = "Verspätungsänderung, "
    if startDay.date() == endDay.date():
        title += f"am {startDay.strftime('%d.%m.%Y')}"
    else:
        title += f"vom {startDay.strftime('%d.%m.%Y')} "
        title += f"bis {endDay.strftime('%d.%m.%Y')}"
    changeMapTitle(svgDict, title)

    #to store delay data, first list for tracks, second list for stations
    delaySectionDict = copy.deepcopy(linesStations)
    for lineStations in delaySectionDict.values():
        for station in lineStations:
            station.append({"trackFw": [], "trackBw": [], "stationFw": [], "stationBw": []})

    def delayAnalysisCallback(journeyDict, stopDictList):
        for currentStopIdx in range(len(stopDictList) - 1):
            nextStopIdx = currentStopIdx + 1
            currentStopDict = stopDictList[currentStopIdx]
            nextStopDict = stopDictList[nextStopIdx]
            cArrES = currentStopDict["arrivalEstimate"]
            cArrTT = currentStopDict["arrivalTimetable"]
            cDepES = currentStopDict["departureEstimate"]
            cDepTT = currentStopDict["departureTimetable"]
            nArrES   = nextStopDict["arrivalEstimate"]
            nArrTT   = nextStopDict["arrivalTimetable"]
            lineName, currentStationIdx, nextStationIdx = getStopIndices(journeyDict["lineName"], linesPathDict, currentStopDict["stopPointRef"], nextStopDict["stopPointRef"])

            #per station delay
            if None not in [cDepES, cDepTT]:
                if None not in [cArrES, cArrTT]:
                    delayChangeStation = ((cDepES-cDepTT) - (cArrES-cArrTT))/60
                else:
                    delayChangeStation = (cDepES-cDepTT)/60
                if currentStationIdx < nextStationIdx:
                    delaySectionDict[lineName][currentStationIdx][2]["stationFw"].append(delayChangeStation)
                else:
                    delaySectionDict[lineName][currentStationIdx][2]["stationBw"].append(delayChangeStation)
            if None not in [cDepES, cDepTT, nArrES, nArrTT]:
                delayChangeTrack = ((nArrES-nArrTT) - (cDepES-cDepTT))/60
                if currentStationIdx < nextStationIdx:
                    delaySectionDict[lineName][currentStationIdx][2]["trackFw"].append(delayChangeTrack)
                else:
                    delaySectionDict[lineName][nextStationIdx][2]["trackBw"].append(delayChangeTrack)


    analyze_data(delayAnalysisCallback, startDay, endDay, perJourneyCallback = True)
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            for stationDir in ["stationFw", "stationBw"]:
                stationDelayList = station[2][stationDir]
                if len(stationDelayList) == 0:
                    continue
                averageDelayChange = sum(stationDelayList)/len(stationDelayList)
                placeStationInfo(svgDict, linesPathDict, lineName, stationIdx, cmap, averageDelayChange, None, direction=stationDir[-2:])
            for trackDir in ["trackFw", "trackBw"]:
                trackDelayList = station[2][trackDir]
                if len(trackDelayList) == 0:
                    continue
                averageDelayChange = sum(trackDelayList)/len(trackDelayList)
                placeSectionInfo(svgDict, linesPathDict, lineName, stationIdx, cmap, averageDelayChange, None, direction=trackDir[-2:])

    with open(outputSvgPath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))

def render_delayStatMap(startDay, endDay, inputSvgPath, outputSvgPath):

    svgDict, linesPathDict, _, cmap = parseSvg(inputSvgPath)
    title = "Durchschnittliche Verspätung an Haltestelle, "
    if startDay.date() == endDay.date():
        title += f"am {startDay.strftime('%d.%m.%Y')}"
    else:
        title += f"vom {startDay.strftime('%d.%m.%Y')} "
        title += f"bis {endDay.strftime('%d.%m.%Y')}"
    changeMapTitle(svgDict, title)

    #to store delay data
    delaySectionDict = copy.deepcopy(linesStations)
    for lineStations in delaySectionDict.values():
        for station in lineStations:
            station.append([])

    def delayAnalysisCallback(journeyDict, stopDict):
        if stopDict["isNotServiced"] == True:
            return
        if stopDict["departureEstimate"] is not None:
            delay = (stopDict["departureEstimate"] - stopDict["departureTimetable"])/60
        elif stopDict["arrivalEstimate"] is not None:
            delay = (stopDict["arrivalEstimate"] - stopDict["arrivalTimetable"])/60
        else:
            return
        rawLineName             = journeyDict["lineName"]
        lineName, stationIdx, _ = getStopIndices(rawLineName, linesPathDict, stopDict["stopPointRef"], stopDict["stopPointRef"])
        if stationIdx is None:
            return
        delaySectionDict[lineName][stationIdx][2].append(delay)

    analyze_data(delayAnalysisCallback, startDay, endDay)
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            if len(station[2]) != 0:
                combinedDelay = sum(station[2])
                numberOfStops = len(station[2])
                averageDelay  = combinedDelay/numberOfStops
                placeStationInfo(svgDict, linesPathDict, lineName, stationIdx, cmap, averageDelay, f"Durchschnittsverspätung: {round(averageDelay,2)} min")
    with open(outputSvgPath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))

def getTrainIcon(trainIconDict, delay, trainPosition, angle):
    if delay <= 3:
        trainIcon = trainIconDict["delay0"]
    elif delay <= 6:
        trainIcon = trainIconDict["delay3"]
    elif delay <= 15:
        trainIcon = trainIconDict["delay6"]
    else:
        trainIcon = trainIconDict["delay15"]
    trainIcon     = trainIcon.copy()
    delayIconPath = parse_path(trainIcon['@d'])
    xmin, xmax, ymin, ymax = delayIconPath.bbox()
    centerX = (xmin + xmax) / 2
    centerY = (ymin + ymax) / 2
    transfMat  = parse_transform(trainIcon["@transform"])
    delayIconPath = translate(delayIconPath, -centerX-1J*centerY)
    delayIconPath = scale(delayIconPath, (transfMat[0,1]**2 + transfMat[1,1]**2) ** 0.5)
    delayIconPath = rotate(delayIconPath, degs=180/math.pi*angle+90, origin=0)
    delayIconPath = translate(delayIconPath, trainPosition)
    trainIcon["@d"] = delayIconPath.d()
    trainIcon.pop("@transform", None)
    trainIcon.pop("@inkscape:original-d", None)
    return trainIcon


def getPosAngleFromPath(lineName, linesPathDict, currStationIdx, nextStationIdx, progress):
    currentLineStations = linesStations[lineName]
    linePath = linesPathDict[lineName]
    parsedPath = parse_path(linePath["@d"])
    if nextStationIdx < currStationIdx:
        startSegmentIdx = segmBetweenStops*(len(currentLineStations) - (currStationIdx + 1))
        endSegmentIdx   = segmBetweenStops*(len(currentLineStations) - (nextStationIdx + 1))
        parsedPath = parsedPath.reversed()
    else:
        startSegmentIdx = segmBetweenStops*currStationIdx
        endSegmentIdx   = segmBetweenStops*nextStationIdx
    pathLengths = [parsedPath[idx].length() for idx in range(startSegmentIdx, endSegmentIdx)]
    totalPathLength = sum(pathLengths)
    pathRatios = [pathLen/totalPathLength for pathLen in pathLengths]
    tempPathLength = 0
    for pathIdx, pathRatio in enumerate(pathRatios):
        tempPathLength += pathRatio
        if progress < tempPathLength:
            break
    progressInCurrentPath = (progress - sum(pathRatios[:pathIdx]))/pathRatios[pathIdx]
    activeSegment = parsedPath[startSegmentIdx+pathIdx]
    trainPosition = activeSegment.point(progressInCurrentPath)
    trainTangent  = activeSegment.derivative(progressInCurrentPath)
    angle         = math.atan2(trainTangent.imag, trainTangent.real)
    return trainPosition, angle


def placeTrains(svgDict, linesPathDict, trainIconDict, runningTrains):
    for trainData in runningTrains:
        rawLineName = trainData["lineName"]
        cStopRef    = trainData["currentStopRef"]
        nStopRef    = trainData["nextStopRef"]
        lineName, cStatIdx, nStatIdx = getStopIndices(rawLineName, linesPathDict, cStopRef, nStopRef)
        if lineName is None:
            continue
        delay           = trainData["delayMinutes"]
        progress        = trainData["progressNextStop"]
        trainPos, angle = getPosAngleFromPath(lineName, linesPathDict, cStatIdx, nStatIdx, progress)
        trainIcon       = getTrainIcon(trainIconDict, delay, trainPos, angle)

        onHoverTooltip  = trainData["lineName"] + " von " + trainData["origin"]
        onHoverTooltip += " nach " + trainData["destination"] + "\n"
        onHoverTooltip += "Verspätung: " + str(int(trainData["delayMinutes"])) + " min" + "\n"
        if trainData["incidentText"] is not None:
            onHoverTooltip += "Grund: " + str(trainData["incidentText"])
        trainIcon["title"] = onHoverTooltip

        svgDict["svg"]["path"].append(trainIcon)

def render_liveMap(inputDataJsonPath, inputSvgPath, outputSvgPath):
    svgDict, linesPathDict, trainIconDict, _ = parseSvg(inputSvgPath)
    title = "Livekarte, aktualisiert "
    title += str(datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
    changeMapTitle(svgDict, title)
    with open(inputDataJsonPath) as inputfile:
        jsonData = json.loads(inputfile.read())
        if jsonData["info"]["attachedDataFormatRevision"] != dataFormatRevision:
            logging.error("incompatible json data file version")
            return
        runningTrainsDict = jsonData["journeys"]
    placeTrains(svgDict, linesPathDict, trainIconDict, runningTrainsDict.values())
    with open(outputSvgPath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict, pretty=True))

if __name__ == "__main__":
    render_liveMap("./currentRunningTrains.json", "./svg_source/live_map_source_light.svg", "live_map.svg")

    now = datetime.now()

    render_delayStatMap(now ,                   now,                    "./svg_source/stat_map_delay_source.svg", "./stat_map_delay_today.svg")
    render_delayStatMap(now+timedelta(days=-1), now+timedelta(days=-1), "./svg_source/stat_map_delay_source.svg", "./stat_map_delay_yesterday.svg")
    render_delayStatMap(now+timedelta(days=-7), now,                    "./svg_source/stat_map_delay_source.svg", "./stat_map_delay_lastWeek.svg")

    render_nonServStatMap(now,                    now,                    "./svg_source/stat_map_delay_source.svg", "./stat_map_nonServ_today.svg")
    render_nonServStatMap(now+timedelta(days=-1), now+timedelta(days=-1), "./svg_source/stat_map_delay_source.svg", "./stat_map_nonServ_yesterday.svg")
    render_nonServStatMap(now+timedelta(days=-7), now,                    "./svg_source/stat_map_delay_source.svg", "./stat_map_nonServ_lastWeek.svg")

    render_delayChangeMap(now, now, "./svg_source/stat_map_delayChange_source.svg", "./stat_map_delay_section_today.svg")
