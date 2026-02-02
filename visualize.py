import xmltodict
from svgpathtools import CubicBezier, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import translate, rotate
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
    "S1":  None, 
    "S2":  None, 
    "S3":  None, 
    "S4":  [("de:08119:7600", "Backnang"), ("de:08119:7500", "Burgstall (M)"), ("de:08119:7502", "Kirchberg (M)"), ("de:08118:3514", "Erdmannhausen"), ("de:08118:7503", "Marbach (N)"), ("de:08118:1500", "Benningen (N)"), ("de:08118:1503", "Freiberg (N)"), ("de:08118:7403", "Favoritepark"), ("de:08118:7402", "Ludwigsburg"), ("de:08118:1402", "Kornwestheim"), ("de:08111:6465","Zuffenhausen"), ("de:08111:6157", "Feuerbach"), ("de:08111:6295", "Nordbahnhof"), ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), ("de:08111:6056", "Stadtmitte"), ("de:08111:6221", "Feuersee"), ("de:08111:6052", "Schwabstraße")],
    "S5":  [("de:08118:1400", "Bietigheim"), ("de:08118:7404", "Tamm"), ("de:08118:7400", "Asperg"), ("de:08118:7402", "Ludwigsburg"), ("de:08118:1402", "Kornwestheim"), ("de:08111:6465","Zuffenhausen"), ("de:08111:6157", "Feuerbach"), ("de:08111:6295", "Nordbahnhof"), ("de:08111:6118", "Stuttgart Hauptbahnhof (tief)"), ("de:08111:6056", "Stadtmitte"), ("de:08111:6221", "Feuersee"), ("de:08111:6052", "Schwabstraße")],
    "S6":  None, 
    "S60": None,
    "S62": None,
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
    stationIdList   = [station[0] for station in LineStations]
    stationNameList = [station[1] for station in LineStations]
    if station in stationIdList:
        stationNr = stationIdList.index(currentStation)
    elif station in stationNameList:
        stationNr = stationNameList.index(currentStation)
    else:
        raise ValueError("station not found in this line")

    startSegmentIdx = stationNr * 3
    pathLenghts = [parsedPath[startSegmentIdx+offsetIdx].length() for offsetIdx in range(3)]
    totalPathLength = sum(pathLenghts)
    pathRatios = [pathLen/totalPathLength for pathLen in pathLenghts]

    print(pathRatios)
    print(progress)
    tempPathLength = 0
    for pathIdx, pathRatio in enumerate(pathRatios):
        tempPathLength += pathRatio
        if progress < tempPathLength:
            break
    progressInCurrentPath = (progress - sum(pathRatios[:pathIdx]))/pathRatios[pathIdx]
    print(f"progressInCurrentPath {progressInCurrentPath}")
    print(pathIdx)
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
    delayIconPath = translate(delayIconPath, -centerX-1J*centerY)
    delayIconPath = rotate(delayIconPath, degs=180/math.pi*angle+90)
    delayIconPath = translate(delayIconPath, position)
    delayIcon["@d"] = delayIconPath.d()
    delayIcon['@transform'] = ""
    svgDict["svg"]["path"].append(delayIcon)

with open("Liniennetz_S-Bahn_Stuttgart.svg", "r") as inputSvg:
    svgFile = inputSvg.read()
svgDict = xmltodict.parse(svgFile)
for path in svgDict["svg"]["path"]:
    pathId = path["@id"]
    if pathId in linesPathId.keys():
        linesPathId[pathId]  = path
    if pathId in delayIconsId.keys():
        delayIconsId[pathId] = path
    
for i in range(21):
    placeTrain("S4", "de:08118:7503", False, i/20, i)
with open("Sbahn_monitor.svg", "w") as outputSvg:
    outputSvg.write(xmltodict.unparse(svgDict))
