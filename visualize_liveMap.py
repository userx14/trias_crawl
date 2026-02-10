import xmltodict
from svgpathtools import CubicBezier, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import translate, rotate, scale
import math

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
        ("de:08115:4512", "Herrenberg"),
        ("de:08115:5775", "Nufringen"),
        ("de:08115:5774", "Gärtringen"),
        ("de:08115:5773", "Ehningen"),
        ("de:08115:7115", "Hulb"),
        ("de:08115:7100", "Böblingen"),
        ("de:08115:3212", "Goldberg"),
        ("de:08111:6001", "Rohr"),
        ("de:08111:6002", "Vaihingen"),
        ("de:08111:6027", "Österfeld"),
        ("de:08111:6008", "Universität"),
        ("de:08111:6052", "Schwabstraße"),
        ("de:08111:6221", "Feuersee"),
        ("de:08111:6056", "Stadtmitte"),
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"),
        ("de:08111:6333", "Bad Cannstatt"),
        ("de:08111:6080", "Neckarpark"),
        ("de:08111:6085", "Untertürkheim"),
        ("de:08111:6091", "Obertürkheim"),
        ("de:08116:1801", "Mettingen"),
        ("de:08116:7800", "Esslingen (N)"),
        ("de:08116:1802", "Oberesslingen"),
        ("de:08116:1803", "Zell"),
        ("de:08116:1800", "Altbach"),
        ("de:08116:7802", "Plochingen"),
        ("de:08116:4241", "Wernau (N)"),
        ("de:08116:4257", "Wendlingen (N)"),
        ("de:08116:4345", "Ötlingen"),
        ("de:08116:4211", "Kirchheim (T)"),
    ],
    "S2": [
        ("de:08119:7703", "Schorndorf"),
        ("de:08119:1704", "Weiler (R)"),
        ("de:08119:1705", "Winterbach"),
        ("de:08119:1702", "Geradstetten"),
        ("de:08119:1703", "Grunbach"),
        ("de:08119:3711", "Beutelsbach"),
        ("de:08119:7704", "Endersbach"),
        ("de:08119:1701", "Stetten-Beinstein"),
        ("de:08119:7701", "Rommelshausen"),
        ("de:08119:7604", "Waiblingen"),
        ("de:08119:6500", "Fellbach"),
        ("de:08111:1300", "Sommerrain"),
        ("de:08111:34",   "Nürnberger Straße"),
        ("de:08111:6333", "Bad Cannstatt"),
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), 
        ("de:08111:6056", "Stadtmitte"), 
        ("de:08111:6221", "Feuersee"), 
        ("de:08111:6052", "Schwabstraße"),
        ("de:08111:6008", "Universität"),
        ("de:08111:6027", "Österfeld"),
        ("de:08111:6002", "Vaihingen"),
        ("de:08111:6001", "Rohr"),
        ("de:08116:2105", "Oberaichen"),
        ("de:08116:175",  "Leinfelden"),
        ("de:08116:7003", "Echterdingen"),
        ("de:08116:2103", "Flughafen/Messe"),
        ("de:08116:1905", "Filderstadt"),
    ], 
    "S3": [
        ("de:08119:7600", "Backnang"),
        ("de:08119:7601", "Maubach"),
        ("de:08119:1601", "Nellmersbach"),
        ("de:08119:7605", "Winnenden"),
        ("de:08119:1603", "Schwaikheim"),
        ("de:08119:1602", "Neustadt-Hohenacker"),
        ("de:08119:7604", "Waiblingen"),
        ("de:08119:6500", "Fellbach"),
        ("de:08111:1300", "Sommerrain"),
        ("de:08111:34",   "Nürnberger Straße"),
        ("de:08111:6333", "Bad Cannstatt"),
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), 
        ("de:08111:6056", "Stadtmitte"), 
        ("de:08111:6221", "Feuersee"), 
        ("de:08111:6052", "Schwabstraße"),
        ("de:08111:6008", "Universität"),
        ("de:08111:6027", "Österfeld"),
        ("de:08111:6002", "Vaihingen"),
        ("de:08111:6001", "Rohr"),
        ("de:08116:2105", "Oberaichen"),
        ("de:08116:175",  "Leinfelden"),
        ("de:08116:7003", "Echterdingen"),
        ("de:08116:2103", "Flughafen/Messe"),
    ], 
    "S4": [
        ("de:08119:7600", "Backnang"), 
        ("de:08119:7500", "Burgstall (M)"), 
        ("de:08119:7502", "Kirchberg (M)"), 
        ("de:08118:3514", "Erdmannhausen"), 
        ("de:08118:7503", "Marbach (N)"), 
        ("de:08118:1500", "Benningen (N)"), 
        ("de:08118:1503", "Freiberg (N)"), 
        ("de:08118:7403", "Favoritepark"), 
        ("de:08118:7402", "Ludwigsburg"), 
        ("de:08118:1402", "Kornwestheim"), 
        ("de:08111:6465", "Zuffenhausen"), 
        ("de:08111:6157", "Feuerbach"), 
        ("de:08111:6295", "Nordbahnhof"), 
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), 
        ("de:08111:6056", "Stadtmitte"), 
        ("de:08111:6221", "Feuersee"), 
        ("de:08111:6052", "Schwabstraße"),
    ],
    "S5":  [
        ("de:08118:1400", "Bietigheim"), 
        ("de:08118:7404", "Tamm"), 
        ("de:08118:7400", "Asperg"), 
        ("de:08118:7402", "Ludwigsburg"), 
        ("de:08118:1402", "Kornwestheim"), 
        ("de:08111:6465", "Zuffenhausen"), 
        ("de:08111:6157", "Feuerbach"), 
        ("de:08111:6295", "Nordbahnhof"), 
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), 
        ("de:08111:6056", "Stadtmitte"), 
        ("de:08111:6221", "Feuersee"), 
        ("de:08111:6052", "Schwabstraße"),
    ],
    "S6":  [
        ("de:08115:1303", "Weil der Stadt"),
        ("de:08115:1301", "Malmsheim"),
        ("de:08115:7302", "Renningen"),
        ("de:08115:1302", "Rutesheim"),
        ("de:08115:7301", "Leonberg"),
        ("de:08115:1003", "Höfingen"),
        ("de:08118:7000", "Ditzingen"),
        ("de:08111:2270", "Weilimdorf Bf"),
        ("de:08118:7603", "Korntal"),
        ("de:08111:1403", "Neuwirtsh. (Porschep.)"),
        ("de:08111:6465", "Zuffenhausen"),
        ("de:08111:6157", "Feuerbach"),
        ("de:08111:6295", "Nordbahnhof"),
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"),
        ("de:08111:6056", "Stadtmitte"),
        ("de:08111:6221", "Feuersee"),
        ("de:08111:6052", "Schwabstraße"),
    ], 
    "S60": [
        ("de:08115:7100", "Böblingen"),
        ("de:08115:3201", "Sindelfingen"),
        ("de:08115:3198", "Maichingen"),
        ("de:08115:3197", "Maichingen Nord"),
        ("de:08115:3196", "Magstadt"),
        ("de:08115:3195", "Renningen Süd"),
        ("de:08115:7302", "Renningen"),
        ("de:08115:1302", "Rutesheim"),
        ("de:08115:7301", "Leonberg"),
        ("de:08115:1003", "Höfingen"),
        ("de:08118:7000", "Ditzingen"),
        ("de:08111:2270", "Weilimdorf Bf"),
        ("de:08118:7603", "Korntal"),
        ("de:08111:1403", "Neuwirtsh. (Porschep.)"),
        ("de:08111:6465", "Zuffenhausen"),
        ("de:08111:6157", "Feuerbach"),
        ("de:08111:6295", "Nordbahnhof"),
        ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"),
        ("de:08111:6056", "Stadtmitte"),
        ("de:08111:6221", "Feuersee"),
        ("de:08111:6052", "Schwabstraße"),
    ],
    "S62": [
        ("de:08115:1303", "Weil der Stadt"),
        ("de:08115:7301", "Leonberg"),
        ("de:08118:7000", "Ditzingen"),
        ("de:08111:2270", "Weilimdorf Bf"),
        ("de:08118:7603", "Korntal"),
        ("de:08118:7000", "Zuffenhausen"),
        ("de:08111:6157", "Feuerbach"),
    ],
}

delayIconsId = {
    "delay0":  None, 
    "delay3":  None, 
    "delay6":  None,
    "delay15": None,
}


def placeTrain(lineName, currentStation, reverseDirection, progress, delayMin):
    lineStations = linesStations[lineName]
    linePath = linesPathId[lineName]
    parsedPath = parse_path(linePath["@d"])
    if reverseDirection:
        print("revDir")
        parsedPath = parsedPath.reversed()
        stationIdList   = [station[0] for station in lineStations[::-1]]
        stationNameList = [station[1] for station in lineStations[::-1]]
    else:
        print("normDir")
        stationIdList   = [station[0] for station in lineStations]
        stationNameList = [station[1] for station in lineStations]
    if currentStation in stationIdList:
        stationNr = stationIdList.index(currentStation)
    elif currentStation in stationNameList:
        stationNr = stationNameList.index(currentStation)
    else:
        raise ValueError("station not found in this line")
    
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
    print(f"pos {position}")
    print(f"station num {stationNr}")

with open("Liniennetz_S-Bahn_Stuttgart.svg", "r") as inputSvg:
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

#get data
import json
with open("./currentRunningTrains.json") as inputfile, open("live_map.svg", "w") as outputSvg:
    runningTrainsDict = json.loads(inputfile.read())
    for trainRefAndOpData, trainData in runningTrainsDict.items():
        print(f"{trainRefAndOpData}: {trainData}\n")
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
