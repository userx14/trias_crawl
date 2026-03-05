from svgpathtools        import parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path   import translate, rotate, scale
from datetime            import datetime
from lineStations        import linesStations
import math, json, xmltodict, logging

dataFormatRevision = "2026.02.26"
segmBetweenStops = 3

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

def parseSvg(inputSvgPath):
    with open(inputSvgPath, "r") as inputSvg:
        svgFile = inputSvg.read()
    svgDict = xmltodict.parse(svgFile, force_list=["g", "path", "text"])
    trainIconIds  = ["delay0", "delay3", "delay6", "delay15"]
    trainIconDict = dict()
    lineIds       = ["S1", "S2", "S3", "S4", "S5", "S6", "S60", "S62"]
    linesPathDict = dict()
    #search for SBahn Line Paths and Train Arrows and store references
    for path in svgDict["svg"]["path"]: #in root paths
        pathId = path["@id"]
        if pathId in trainIconIds:
            trainIconDict[pathId] = path
        if pathId in lineIds:
            linesPathDict[pathId] = path
    for group in svgDict["svg"]["g"]: #in paths that are grouped
        if "path" not in group.keys():
            continue
        for path in group["path"]:
            if "@id" not in path.keys():
                continue
            pathId = path["@id"]
            if pathId in trainIconIds:
                trainIconDict[pathId]  = path
            if pathId in lineIds:
                linesPathDict[pathId]   = path
    if len(trainIconIds) != len(trainIconDict) or len(lineIds) != len(linesPathDict):
        raise ValueError("Missing line or icon in svg")
    return svgDict, linesPathDict, trainIconDict

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

def getStopIndices(trainData, linesPathDict):
    lineName = trainData["lineName"]
    currentStopRefWithoutPlatform = ":".join(trainData["currentStopRef"].split(":")[:3])
    nextStopRefWithoutPlatform    = ":".join(trainData["nextStopRef"].split(":")[:3])
    if nextStopRefWithoutPlatform ==  "de:08111:6115": #convert HBF oben to HBF tief
        nextStopRefWithoutPlatform = "de:08111:6118"
    if currentStopRefWithoutPlatform == "de:08111:6115": #convert HBF oben to HBF tief
        currentStopRefWithoutPlatform = "de:08111:6118"
    if lineName not in linesPathDict.keys():
        #handle replacement service
        #when line is S52, try to map to S5 and S2
        digits = [char for char in lineName if char.isdigit()]
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
        currStationIdx = findStationNumber(lineName, currentStopRefWithoutPlatform)
        nextStationIdx = findStationNumber(lineName, nextStopRefWithoutPlatform)
        if currStationIdx is None:
            logging.error(f"Nonexistent stop {currentStopRefWithoutPlatform} on line {lineName}")
            return None, None, None
        if nextStationIdx is None:
            logging.error(f"Nonexistent stop {nextStopRefWithoutPlatform} on line {lineName}")
            return None, None, None
    return lineName, currStationIdx, nextStationIdx

def placeTrains(svgDict, linesPathDict, trainIconDict, runningTrains):
    for trainData in runningTrains:
        lineName, cStatIdx, nStatIdx = getStopIndices(trainData, linesPathDict)
        if lineName is None:
            continue
        delay           = trainData["delay"]
        progress        = trainData["progressNextStop"]
        trainPos, angle = getPosAngleFromPath(lineName, linesPathDict, cStatIdx, nStatIdx, progress)
        trainIcon       = getTrainIcon(trainIconDict, delay, trainPos, angle)

        onHoverTooltip  = trainData["lineName"] + " von " + trainData["origin"]
        onHoverTooltip += " nach " + trainData["destination"] + "\n"
        onHoverTooltip += "Verspätung: " + str(int(trainData["delay"])) + " min" + "\n"
        if trainData["incidentText"] is not None:
            onHoverTooltip += "Grund: " + str(trainData["incidentText"])
        trainIcon["title"] = onHoverTooltip

        svgDict["svg"]["path"].append(trainIcon)

def render_liveMap(inputDataJsonPath, inputSvgPath, outputSvgPath):
    svgDict, linesPathDict, trainIconDict = parseSvg(inputSvgPath)
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
    render_liveMap("./currentRunningTrains.json", "./svg_source/live_map_source_dark_linecolor.svg", "live_map.svg")
