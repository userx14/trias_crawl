import xmltodict
from datetime import datetime, timezone, timedelta
from svgpathtools import CubicBezier, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import translate, rotate, scale
import math
import copy
import sqlite3


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

linesStations = {
    "S1": [
        ["de:08115:4512", "Herrenberg"],
        ["de:08115:5775", "Nufringen"],
        ["de:08115:5774", "Gärtringen"],
        ["de:08115:5773", "Ehningen"],
        ["de:08115:7115", "Hulb"],
        ["de:08115:7100", "Böblingen"],
        ["de:08115:3212", "Goldberg"],
        ["de:08111:6001", "Rohr"],
        ["de:08111:6002", "Vaihingen"],
        ["de:08111:6027", "Österfeld"],
        ["de:08111:6008", "Universität"],
        ["de:08111:6052", "Schwabstraße"],
        ["de:08111:6221", "Feuersee"],
        ["de:08111:6056", "Stadtmitte"],
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"],
        ["de:08111:6333", "Bad Cannstatt"],
        ["de:08111:6080", "Neckarpark"],
        ["de:08111:6085", "Untertürkheim"],
        ["de:08111:6091", "Obertürkheim"],
        ["de:08116:1801", "Mettingen"],
        ["de:08116:7800", "Esslingen [N]"],
        ["de:08116:1802", "Oberesslingen"],
        ["de:08116:1803", "Zell"],
        ["de:08116:1800", "Altbach"],
        ["de:08116:7802", "Plochingen"],
        ["de:08116:4241", "Wernau [N]"],
        ["de:08116:4257", "Wendlingen [N]"],
        ["de:08116:4345", "Ötlingen"],
        ["de:08116:4211", "Kirchheim [T]"],
    ],
    "S2": [
        ["de:08119:7703", "Schorndorf"],
        ["de:08119:1704", "Weiler [R]"],
        ["de:08119:1705", "Winterbach"],
        ["de:08119:1702", "Geradstetten"],
        ["de:08119:1703", "Grunbach"],
        ["de:08119:3711", "Beutelsbach"],
        ["de:08119:7704", "Endersbach"],
        ["de:08119:1701", "Stetten-Beinstein"],
        ["de:08119:7701", "Rommelshausen"],
        ["de:08119:7604", "Waiblingen"],
        ["de:08119:6500", "Fellbach"],
        ["de:08111:1300", "Sommerrain"],
        ["de:08111:34",   "Nürnberger Straße"],
        ["de:08111:6333", "Bad Cannstatt"],
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"], 
        ["de:08111:6056", "Stadtmitte"], 
        ["de:08111:6221", "Feuersee"], 
        ["de:08111:6052", "Schwabstraße"],
        ["de:08111:6008", "Universität"],
        ["de:08111:6027", "Österfeld"],
        ["de:08111:6002", "Vaihingen"],
        ["de:08111:6001", "Rohr"],
        ["de:08116:2105", "Oberaichen"],
        ["de:08116:175",  "Leinfelden"],
        ["de:08116:7003", "Echterdingen"],
        ["de:08116:2103", "Flughafen/Messe"],
        ["de:08116:1905", "Filderstadt"],
    ], 
    "S3": [
        ["de:08119:7600", "Backnang"],
        ["de:08119:7601", "Maubach"],
        ["de:08119:1601", "Nellmersbach"],
        ["de:08119:7605", "Winnenden"],
        ["de:08119:1603", "Schwaikheim"],
        ["de:08119:1602", "Neustadt-Hohenacker"],
        ["de:08119:7604", "Waiblingen"],
        ["de:08119:6500", "Fellbach"],
        ["de:08111:1300", "Sommerrain"],
        ["de:08111:34",   "Nürnberger Straße"],
        ["de:08111:6333", "Bad Cannstatt"],
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"], 
        ["de:08111:6056", "Stadtmitte"], 
        ["de:08111:6221", "Feuersee"], 
        ["de:08111:6052", "Schwabstraße"],
        ["de:08111:6008", "Universität"],
        ["de:08111:6027", "Österfeld"],
        ["de:08111:6002", "Vaihingen"],
        ["de:08111:6001", "Rohr"],
        ["de:08116:2105", "Oberaichen"],
        ["de:08116:175",  "Leinfelden"],
        ["de:08116:7003", "Echterdingen"],
        ["de:08116:2103", "Flughafen/Messe"],
    ], 
    "S4": [
        ["de:08119:7600", "Backnang"], 
        ["de:08119:7500", "Burgstall [M]"], 
        ["de:08119:7502", "Kirchberg [M]"], 
        ["de:08118:3514", "Erdmannhausen"], 
        ["de:08118:7503", "Marbach [N]"], 
        ["de:08118:1500", "Benningen [N]"], 
        ["de:08118:1503", "Freiberg [N]"], 
        ["de:08118:7403", "Favoritepark"], 
        ["de:08118:7402", "Ludwigsburg"], 
        ["de:08118:1402", "Kornwestheim"], 
        ["de:08111:6465", "Zuffenhausen"], 
        ["de:08111:6157", "Feuerbach"], 
        ["de:08111:6295", "Nordbahnhof"], 
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"], 
        ["de:08111:6056", "Stadtmitte"], 
        ["de:08111:6221", "Feuersee"], 
        ["de:08111:6052", "Schwabstraße"],
    ],
    "S5":  [
        ["de:08118:1400", "Bietigheim"], 
        ["de:08118:7404", "Tamm"], 
        ["de:08118:7400", "Asperg"], 
        ["de:08118:7402", "Ludwigsburg"], 
        ["de:08118:1402", "Kornwestheim"], 
        ["de:08111:6465", "Zuffenhausen"], 
        ["de:08111:6157", "Feuerbach"], 
        ["de:08111:6295", "Nordbahnhof"], 
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"], 
        ["de:08111:6056", "Stadtmitte"], 
        ["de:08111:6221", "Feuersee"], 
        ["de:08111:6052", "Schwabstraße"],
    ],
    "S6":  [
        ["de:08115:1303", "Weil der Stadt"],
        ["de:08115:1301", "Malmsheim"],
        ["de:08115:7302", "Renningen"],
        ["de:08115:1302", "Rutesheim"],
        ["de:08115:7301", "Leonberg"],
        ["de:08115:1003", "Höfingen"],
        ["de:08118:7000", "Ditzingen"],
        ["de:08111:2270", "Weilimdorf Bf"],
        ["de:08118:7603", "Korntal"],
        ["de:08111:1403", "Neuwirtsh. [Porschep.]"],
        ["de:08111:6465", "Zuffenhausen"],
        ["de:08111:6157", "Feuerbach"],
        ["de:08111:6295", "Nordbahnhof"],
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"],
        ["de:08111:6056", "Stadtmitte"],
        ["de:08111:6221", "Feuersee"],
        ["de:08111:6052", "Schwabstraße"],
    ], 
    "S60": [
        ["de:08115:7100", "Böblingen"],
        ["de:08115:3201", "Sindelfingen"],
        ["de:08115:3198", "Maichingen"],
        ["de:08115:3197", "Maichingen Nord"],
        ["de:08115:3196", "Magstadt"],
        ["de:08115:3195", "Renningen Süd"],
        ["de:08115:7302", "Renningen"],
        ["de:08115:1302", "Rutesheim"],
        ["de:08115:7301", "Leonberg"],
        ["de:08115:1003", "Höfingen"],
        ["de:08118:7000", "Ditzingen"],
        ["de:08111:2270", "Weilimdorf Bf"],
        ["de:08118:7603", "Korntal"],
        ["de:08111:1403", "Neuwirtsh. [Porschep.]"],
        ["de:08111:6465", "Zuffenhausen"],
        ["de:08111:6157", "Feuerbach"],
        ["de:08111:6295", "Nordbahnhof"],
        ["de:08111:6118", "Stuttgart Hauptbahnhof [tief]"],
        ["de:08111:6056", "Stadtmitte"],
        ["de:08111:6221", "Feuersee"],
        ["de:08111:6052", "Schwabstraße"],
    ],
    "S62": [
        ["de:08115:1303", "Weil der Stadt"],
        ["de:08115:7301", "Leonberg"],
        ["de:08118:7000", "Ditzingen"],
        ["de:08111:2270", "Weilimdorf Bf"],
        ["de:08118:7603", "Korntal"],
        ["de:08118:6465", "Zuffenhausen"],
        ["de:08111:6157", "Feuerbach"],
    ],
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
        raise ValueError(f"station not found in this line {stopRefWithoutPlatform}")


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
    listOfCircles.append(circle)

#data analysis
analysisDay = datetime(2026,2,11,0,0,0)
connection  = sqlite3.connect('loggedJourney_2026.db')
cursor      = connection.cursor()
analysisDay = analysisDay.astimezone(timezone.utc)
analysisDay = analysisDay.replace(hour=0, minute=0, second=0, microsecond=0)
analysisDay = int(analysisDay.timestamp())
cursor.execute(f"SELECT * FROM journeys WHERE operatingDay=?;", (analysisDay,))
journeys    = cursor.fetchall()
keysJourney = list(map(lambda x: x[0], cursor.description))
notServicedSectionDict = copy.deepcopy(linesStations)
for lineStations in notServicedSectionDict.values():
    for station in lineStations:
        station.append([])
for journeyData in journeys:
    journeyRef      = journeyData[keysJourney.index("journeyRef")]
    incidentMessage = journeyData[keysJourney.index("trainIncidentMessage")]
    isCancelled     = journeyData[keysJourney.index("isCancelled")]
    trainLineName   = journeyData[keysJourney.index("trainLineName")]
    if "S" not in trainLineName:
        continue
    if isCancelled:
        continue
    #get all stops
    cursor.execute(f"SELECT * FROM stops WHERE operatingDay=? AND journeyRef=? ORDER BY stopIndex ASC;", (analysisDay,journeyRef,))
    stops = cursor.fetchall()
    keysStop = list(map(lambda x: x[0], cursor.description))
    isReversed = (journeyRef.split(":")[3]) == "R"
    stationsOnThisLine = linesStations[trainLineName]
    depTimetIdx = keysStop.index("departureTimetable")
    depEstimIdx = keysStop.index("departureEstimate")
    arrTimetIdx = keysStop.index("arrivalTimetable")
    arrEstimIdx = keysStop.index("arrivalEstimate")
    for stop in stops:
        if stop[depEstimIdx] is not None:
            delay = (stop[depEstimIdx] - stop[depTimetIdx])/60
        elif stop[arrEstimIdx] is not None:
            delay = (stop[arrEstimIdx] - stop[arrTimetIdx])/60
        else:
            continue
        stopPointRef = stop[keysStop.index("stopPointRef")]
        stationNr = stopPointRefToStationIdx(stopPointRef, stationsOnThisLine)
        notServicedSectionDict[trainLineName][stationNr][2].append(delay)

#data visualization
with open("stat_map_delay_source.svg", "r") as inputSvg:
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
cmap = make_colormap([0.0, 3.0, 6.0], ["12dc01", "e0ea00", "ff0e0e"])
listOfCircles = []
for lineName, lineStations in notServicedSectionDict.items():
    for stationIdx, station in enumerate(lineStations):
        if len(station[2]) != 0:
            ratioNotServiced = sum(station[2])/len(station[2])
            lineStations[stationIdx][2] = ratioNotServiced
        else:
            lineStations[stationIdx][2] = 0
        colorTrainStation(lineName, lineStations[stationIdx][0], lineStations[stationIdx][2], cmap)

svgDict["svg"]["circle"] = listOfCircles
with open("stat_map_delay.svg", "w") as outputSvg:
    outputSvg.write(xmltodict.unparse(svgDict))
