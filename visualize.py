import xmltodict
from svgpathtools import CubicBezier, parse_path
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
    "S4":  [("de:08119:7600", "Backnang"), ("de:08119:7500", "Burgstall (M)"), ("de:08119:7502", "Kirchberg (M)"), ("de:08118:3514", "Erdmannhausen"), ("de:08118:7503", "Marbach (N)")], 
    "S5":  None, 
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
    stationNr = [station[0] for station in lineStations].index(currentStation)
    startSegmentIdx = stationNr * 3
    pathLenghts = [parsedPath[startSegmentIdx+offsetIdx].length() for offsetIdx in range(3)]
    totalPathLength = sum(pathLenghts)
    pathRatios = [pathLen/totalPathLength for pathLen in pathLenghts]
    
    tempPathLength = 0
    for pathIdx, pathRatio in enumerate(pathRatios):
        tempPathLength += pathRatio
        if progress < tempPathLength:
            break
    activeSegment = parsedPath[pathIdx]
    positionInPath = pathRatios[pathIdx]/tempPathLength  
    position = activeSegment.point(positionInPath)
    tangent = activeSegment.derivative(positionInPath)
    angle = math.atan2(tangent.imag, tangent.real)
    
    
    if delayMin <= 3:
        delayIcon = delayIconsId["delay0"]
    elif delayMin <= 6:
        delayIcon = delayIconsId["delay3"]
    elif delayMin <= 15:
        delayIcon = delayIconsId["delay6"]
    else:
        delayIcon = delayIconsId["delay15"]
    delayIcon = delayIcon.copy()    
    old_transform = delayIcon.get('@transform', '')

    path = parse_path(delayIcon['@d'])
    xmin, xmax, ymin, ymax = path.bbox()

    cx_old = (xmin + xmax) / 2
    cy_old = (ymin + ymax) / 2
    print(position)
    
    delayIcon['@transform'] = (
        f"{old_transform} "
        f"translate({position.real-cx_old},{position.imag-cy_old}) "
        f"rotate({angle})"
    )
    svgDict["svg"]["path"].append(delayIcon)
        
    print(position)
    print(angle)
    
with open("Liniennetz_S-Bahn_Stuttgart.svg", "r") as inputSvg:
    svgFile = inputSvg.read()
svgDict = xmltodict.parse(svgFile)
for path in svgDict["svg"]["path"]:
    pathId = path["@id"]
    if pathId in linesPathId.keys():
        linesPathId[pathId]  = path
    if pathId in delayIconsId.keys():
        delayIconsId[pathId] = path
    

    
placeTrain("S4", "de:08119:7502", False, 0.53, 7)
with open("Sbahn_monitor.svg", "w") as outputSvg:
    outputSvg.write(xmltodict.unparse(svgDict))