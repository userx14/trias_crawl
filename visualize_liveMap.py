import xmltodict
from svgpathtools import CubicBezier, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import translate, rotate, scale
import math
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lineStations import linesStations

base_dir         = Path(__file__).parent
json_data_source = base_dir/"www/currentRunningTrains.json"
svg_in_dir       = base_dir/"live_map_source.svg"

def update_live_map(out_dir):
    svg_out_dir = out_dir/"live_map.svg"
    delayIconsId = {
        "delay0":  None,
        "delay3":  None,
        "delay6":  None,
        "delay15": None,
    }
    linesPathId  = {
        "S1":  None,
        "S2":  None,
        "S3":  None,
        "S4":  None,
        "S5":  None,
        "S6":  None,
        "S60": None,
        "S62": None,
    }

    def placeTrain(lineName, currentStation, reverseDirection, progress, delayMin):
        if lineName not in linesStations.keys():
            logging.debug(f"trainLineName {trainLineName} unknown")
            return
        lineStations = linesStations[lineName]
        linePath = linesPathId[lineName]
        parsedPath = parse_path(linePath["@d"])
        if reverseDirection:
            #print("revDir")
            parsedPath = parsedPath.reversed()
            stationIdList   = [station[0] for station in lineStations[::-1]]
            stationNameList = [station[1] for station in lineStations[::-1]]
        else:
            #print("normDir")
            stationIdList   = [station[0] for station in lineStations]
            stationNameList = [station[1] for station in lineStations]
        if currentStation in stationIdList:
            stationNr = stationIdList.index(currentStation)
        elif currentStation in stationNameList:
            stationNr = stationNameList.index(currentStation)
        else:
            logging.debug(f"station {currentStation} not found in this line")
            return

        startSegmentIdx = stationNr * 3
        if stationNr != len(lineStations)-1:

            pathLenghts = [parsedPath[startSegmentIdx+offsetIdx].length() for offsetIdx in range(3)]
            totalPathLength = sum(pathLenghts)
            pathRatios = [pathLen/totalPathLength for pathLen in pathLenghts]
            tempPathLength = 0
            for pathIdx, pathRatio in enumerate(pathRatios):
                tempPathLength += pathRatio
                if progress < tempPathLength:
                    break
            progressInCurrentPath = (progress - sum(pathRatios[:pathIdx]))/pathRatios[pathIdx]
        else:
            pathIdx = -1
            progressInCurrentPath = 1
        #print(f"progressInCurrentPath {progressInCurrentPath}")
        #print(pathIdx)
        activeSegment = parsedPath[startSegmentIdx+pathIdx]
        position = activeSegment.point(progressInCurrentPath)
        tangent = activeSegment.derivative(progressInCurrentPath)
        angle = math.atan2(tangent.imag, tangent.real)

        if delayMin <= 3:
            delayIcon = delayIconsId["delay0"]
        elif delayMin <= 6:
            delayIcon = delayIconsId["delay3"]
        elif delayMin <= 15:
            delayIcon = delayIconsId["delay6"]
        else:
            delayIcon = delayIconsId["delay15"]
        delayIcon     = delayIcon.copy()
        delayIconPath = parse_path(delayIcon['@d'])
        xmin, xmax, ymin, ymax = delayIconPath.bbox()
        centerX = (xmin + xmax) / 2
        centerY = (ymin + ymax) / 2

        transfMat  = parse_transform(delayIcon["@transform"])
        #oldRotScale = f"matrix({transfMat[0,0]} {transfMat[1,0]} {transfMat[0,1]} {transfMat[1,1]} 0 0)"
        delayIconPath = translate(delayIconPath, -centerX-1J*centerY)
        delayIconPath = scale(delayIconPath, (transfMat[0,1]**2 + transfMat[1,1]**2) ** 0.5)
        delayIconPath = rotate(delayIconPath, degs=180/math.pi*angle+90,  origin=0)
        delayIconPath = translate(delayIconPath, position)
        delayIcon["@d"] = delayIconPath.d()
        delayIcon.pop("@transform", None)
        delayIcon.pop("@inkscape:original-d", None)
        svgDict["svg"]["path"].append(delayIcon)
        #print(f"pos {position}")
        #print(f"station num {stationNr}")

    with open(svg_in_dir, "r") as inputSvg:
        svgFile = inputSvg.read()
    svgDict = xmltodict.parse(svgFile)
    for path in svgDict["svg"]["path"]:
        pathId = path["@id"]
        if pathId in linesPathId.keys():
            linesPathId[pathId]  = path
        if pathId in delayIconsId.keys():
            delayIconsId[pathId] = path
    for group in svgDict["svg"]["g"]:
        for path in group["path"]:
            pathId = path["@id"]
            if pathId in linesPathId.keys():
                linesPathId[pathId]  = path
            if pathId in delayIconsId.keys():
                delayIconsId[pathId] = path
    if any([item == None for item in delayIconsId.values()]):
        print(delayIconsId.values())
        raise ValueError("Delay icon not present in svg")

    if any([item == None for item in linesPathId.values()]):
        raise ValueError("Line path not present in svg")
    if isinstance(svgDict["svg"]["text"], list):
        for textElement in svgDict["svg"]["text"]:
            if textElement["@id"] == "title":
                textElement["tspan"]["#text"] = f"Livekarte, aktualisiert {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    else:
        svgDict["svg"]["text"]["tspan"]["#text"] = f"Livekarte, aktualisiert {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"

    with open(json_data_source) as inputfile, open(svg_out_dir, "w") as outputSvg:
        runningTrainsDict = json.loads(inputfile.read())["journeys"]
        for trainRefAndOpData, trainData in runningTrainsDict.items():
            if trainData["lineName"] not in linesPathId.keys():
                continue
            if trainData["cancelled"]:
                continue
            backwardsJourney = (trainRefAndOpData.split(":")[3] == "R")
            stopRefWithoutPlatform = ":".join(trainData["currentStopRef"].split(":")[:-2])
            if stopRefWithoutPlatform == "de:08111:6115": #convert HBF oben to HBF tief
                stopRefWithoutPlatform = "de:08111:6118"
            placeTrain(trainData["lineName"],
                    stopRefWithoutPlatform,
                    backwardsJourney,
                    trainData["progressNextStop"],
                    trainData["delay"])
        outputSvg.write(xmltodict.unparse(svgDict))
