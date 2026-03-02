import xmltodict
from datetime import datetime, timezone, timedelta
from svgpathtools import CubicBezier, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import translate, rotate, scale
import math
import copy
import sqlite3
import logging
from pathlib import Path
from lineStations import linesStations

base_dir               = Path(__file__).parent
yearInt                = datetime.now().year
db_data_source         = base_dir/f'loggedJourney_{yearInt}.db'
svg_delay_in_dir       = base_dir/"stat_map_delay_source.svg"
svg_notServiced_in_dir = base_dir/"stat_map_notServiced_source.svg"

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

def stopPointRefToStationIdx(stopPointRef, stationsOnThisLine):
    stationIdList   = [station[0] for station in stationsOnThisLine]
    stationNameList = [station[1] for station in stationsOnThisLine]
    stopRefWithoutPlatform = ":".join(stopPointRef.split(":")[:3])
    if stopRefWithoutPlatform == "de:08111:6115": #convert HBF oben to HBF tief
        stopRefWithoutPlatform = "de:08111:6118"
    if stopRefWithoutPlatform in stationIdList:
        return stationIdList.index(stopRefWithoutPlatform)
    elif stopRefWithoutPlatform in stationNameList:
        return stationNameList.index(stopRefWithoutPlatform)
    else:
        logging.debug(f"station not found in this line {stopRefWithoutPlatform}, line: {list(linesStations.keys())[list(linesStations.values()).index(stationsOnThisLine)]}")
        return None


def make_colormap(stops, colors):
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

def colorTrainStation(lineName, stationRef, value, colormap):
    lineStations  = linesStations[lineName]
    linePath      = linesPathId[lineName]
    parsedPath    = parse_path(linePath["@d"])
    pathIdx       = 3*stopPointRefToStationIdx(stationRef, lineStations)
    if pathIdx < len(parsedPath):
        activeSegment = parsedPath[pathIdx]
        position      = activeSegment.point(0) #complex
    else:
        activeSegment = parsedPath[-1]
        position      = activeSegment.point(1) #complex
    circle = {
        "@cx": position.real,
        "@cy": position.imag,
        "@r": "8",
        "@fill": colormap(value),
    }
    return circle

def analyze_data(callbackAnalysis, analysisDayStart, analysisDayEnd):
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
    keysJourney = list(map(lambda x: x[0], cursor.description))
    for journeyData in journeys:
        journeyDict = dict()
        for keyIdx, key in enumerate(keysJourney):
            journeyDict[key] = journeyData[keyIdx]
        if "S" not in journeyDict["trainLineName"]:
            continue
        journeyRef      = journeyDict["journeyRef"]
        operatingDay    = journeyDict["operatingDay"]

        #get all stops
        cursor.execute(f"SELECT * FROM stops WHERE operatingDay=? AND journeyRef=? ORDER BY stopIndex ASC;", (operatingDay,journeyRef,))
        stops = cursor.fetchall()
        keysStop = list(map(lambda x: x[0], cursor.description))
        for stopData in stops:
            stopDict = dict()
            for keyIdx, key in enumerate(keysStop):
                stopDict[key] = stopData[keyIdx]
            callbackAnalysis(journeyDict, stopDict)


#data visualization delay
def update_stat_delay_map(analysisStartDay, analysisEndDay, outputFilePath):
    delaySectionDict = copy.deepcopy(linesStations)
    for lineStations in delaySectionDict.values():
        for station in lineStations:
            station.append([])
    def delayAnalysisFunction(journeyDict, stopDict):
        trainLineName = journeyDict["trainLineName"]
        if "S" not in trainLineName:
            return
        if trainLineName not in linesStations.keys():
            logging.debug(f"trainLineName {trainLineName} unknown")
            return
        if journeyDict["isCancelled"]:
            return
        isReversed = (journeyDict["journeyRef"].split(":")[3]) == "R"
        #incidentMessage = journeyDict["trainIncidentMessage"]
        stationsOnThisLine = linesStations[trainLineName]
        if stopDict["departureEstimate"] is not None:
            delay = (stopDict["departureEstimate"] - stopDict["departureTimetable"])/60
        elif stopDict["arrivalEstimate"] is not None:
            delay = (stopDict["arrivalEstimate"] - stopDict["arrivalTimetable"])/60
        else:
            return
        stationNr = stopPointRefToStationIdx(stopDict["stopPointRef"], stationsOnThisLine)
        if stationNr is None:
            return
        delaySectionDict[trainLineName][stationNr][2].append(delay)
    analyze_data(delayAnalysisFunction, analysisStartDay, analysisEndDay)
    with open(svg_delay_in_dir, "r") as inputSvg:
        svgFile = inputSvg.read()
    svgDict = xmltodict.parse(svgFile)
    for path in svgDict["svg"]["path"]:
        pathId = path["@id"]
        if pathId in linesPathId.keys():
            linesPathId[pathId]  = path
    for group in svgDict["svg"]["g"]:
        for path in group["path"]:
            pathId = path["@id"]
            if pathId in linesPathId.keys():
                linesPathId[pathId]  = path
    if any([item == None for item in linesPathId.values()]):
        raise ValueError("Line path not present in svg")
    cmap = make_colormap([0.0, 5.0, 10.0], ["#12dc01", "#e0ea00", "#ff0e0e"])
    listOfCircles = []
    for lineName, lineStations in delaySectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            if len(station[2]) != 0:
                ratioNotServiced = sum(station[2])/len(station[2])
                lineStations[stationIdx][2] = ratioNotServiced
                listOfCircles.append(colorTrainStation(lineName, lineStations[stationIdx][0], lineStations[stationIdx][2], cmap))
    svgDict["svg"]["circle"] = listOfCircles
    if analysisStartDay == analysisEndDay:
        titleText = f"Durchschnittliche Verspätung am Halt, am {analysisStartDay.strftime('%d.%m.%Y')}"
    else:
        titleText = f"Durchschnittliche Verspätung am Halt, vom {analysisStartDay.strftime('%d.%m.%Y')} bis {analysisEndDay.strftime('%d.%m.%Y')}"
    for textElement in svgDict["svg"]["text"]:
        if textElement["@id"] == "title":
            textElement["tspan"]["#text"] = titleText
    with open(outputFilePath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict))

def update_stat_notServiced_map(analysisStartDay, analysisEndDay, outputFilePath):
    notServicedSectionDict = copy.deepcopy(linesStations)
    for lineStations in notServicedSectionDict.values():
        for station in lineStations:
            station.append([])
    def notServicedAnalysisFunc(journeyDict, stopDict):
        trainLineName = journeyDict["trainLineName"]
        if trainLineName not in linesStations.keys():
            logging.debug(f"trainLineName {trainLineName} not found")
            return
        stationsOnThisLine = linesStations[trainLineName]
        stationNr     = stopPointRefToStationIdx(stopDict["stopPointRef"], stationsOnThisLine)
        if stationNr is None:
            return
        if stopDict["notServiced"]:
            notServicedSectionDict[trainLineName][stationNr][2].append(1)
        else:
            notServicedSectionDict[trainLineName][stationNr][2].append(0)

    analyze_data(notServicedAnalysisFunc, analysisStartDay, analysisEndDay)

    with open(svg_notServiced_in_dir, "r") as inputSvg:
        svgFile = inputSvg.read()
    svgDict = xmltodict.parse(svgFile)
    for path in svgDict["svg"]["path"]:
        pathId = path["@id"]
        if pathId in linesPathId.keys():
            linesPathId[pathId]  = path
    for group in svgDict["svg"]["g"]:
        for path in group["path"]:
            pathId = path["@id"]
            if pathId in linesPathId.keys():
                linesPathId[pathId]  = path
    if any([item == None for item in linesPathId.values()]):
        raise ValueError("Line path not present in svg")
    cmap = make_colormap([0.0, 0.1, 0.2], ["#12dc01", "#e0ea00", "#ff0e0e"])
    listOfCircles = []
    for lineName, lineStations in notServicedSectionDict.items():
        for stationIdx, station in enumerate(lineStations):
            if len(station[2]) != 0:
                ratioNotServiced = sum(station[2])/len(station[2])
                lineStations[stationIdx][2] = ratioNotServiced
                listOfCircles.append(colorTrainStation(lineName, lineStations[stationIdx][0], lineStations[stationIdx][2], cmap))
    svgDict["svg"]["circle"] = listOfCircles
    if analysisStartDay == analysisEndDay:
        titleText = f"Anteil ungeplant ausgefallener Halte, am {analysisStartDay.strftime('%d.%m.%Y')}"
    else:
        titleText = f"Anteil ungeplant ausgefallener Halte, vom {analysisStartDay.strftime('%d.%m.%Y')} bis {analysisEndDay.strftime('%d.%m.%Y')}"
    for textElement in svgDict["svg"]["text"]:
        if textElement["@id"] == "title":
            textElement["tspan"]["#text"] = titleText

    with open(outputFilePath, "w") as outputSvg:
        outputSvg.write(xmltodict.unparse(svgDict))

#visualize_delay(datetime(2026,2,11,0,0,0), datetime(2026,2,15,0,0,0))
#visualize_notServiced(datetime(2026,2,11,0,0,0), datetime(2026,2,15,0,0,0))
