from datetime import datetime, timezone, timedelta
import xmltodict
import requests
import logging
from pathlib import Path
base_dir      = Path(__file__).parent

validateXSD   = False
if validateXSD:
    import xmlschema

url           = "https://efa-bw.de/trias"
requestorKey  = None
namespaces    = {
    "http://www.vdv.de/trias": None,
    "http://www.siri.org.uk/siri": "siri",
    "http://www.w3.org/2001/XMLSchema-instance": "xsi"
}
requestHeader = {'Content-Type': 'application/xml; charset=utf-8', 'User-Agent': 'Python-urllib/3.10'}

def sendRequest(requestAsDict):
    serviceRequest   = requestAsDict["Trias"]["ServiceRequest"]
    currentTimestamp = datetime.now().astimezone(timezone.utc)
    currentTimestamp = currentTimestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    serviceRequest["siri:RequestTimestamp"] = currentTimestamp
    serviceRequest["siri:RequestorRef"]     = requestorKey

    requestAsXml = xmltodict.unparse(requestAsDict, pretty=True)

    if validateXSD:
        xmlschema.validate(requestAsXml, './trias_xsd/Trias.xsd')

    response = requests.post(url, data=requestAsXml, headers=requestHeader)

    #when a single item of these is found, make it a list anyway
    alwaysList = ["Attribute", "LocationResult", "Mode", "PreviousCall", "ThisCall", "OnwardCall"]

    return xmltodict.parse(response.content, process_namespaces=True, namespaces=namespaces, force_list=alwaysList)

def datetimeFromTriasDatetimeStr(triasStr):
    if triasStr is None:
        return None
    time = datetime.strptime(triasStr, "%Y-%m-%dT%H:%M:%SZ")
    time = time.replace(tzinfo=timezone.utc)
    time = time.astimezone() #convert to local timezone
    return time

def datetimeFromTriasDateStr(triasStr):
    if triasStr is None:
        return None
    time = datetime.strptime(triasStr, "%Y-%m-%d")
    time = time.replace(tzinfo=timezone.utc)
    time = time.astimezone() #convert to local timezone
    return time

def triasStrFromDatetime(datetimeObj):
    datetimeObj = datetimeObj.astimezone(timezone.utc)
    return datetimeObj.strftime("%Y-%m-%dT%H:%M:%SZ")

def getResponseStatistics(responseDict):
    serviceDelivery      = responseDict["Trias"]["ServiceDelivery"]
    responseTimestampStr = serviceDelivery["siri:ResponseTimestamp"]
    calculationTime      = int(serviceDelivery["CalcTime"])
    return responseTimestampStr, calculationTime

def stopPointRef_from_LocationName(LocationName):
    findStationRequestXml = Path("./LocationInformationRequest.xml")
    findStationRequestXml = open(findStationRequestXml, "rb").read()
    findStationRequest = xmltodict.parse(findStationRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = findStationRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["LocationInformationRequest"]["InitialInput"]["LocationName"] = LocationName

    findStationResponse = sendRequest(findStationRequest)
    printResponseStatistics(findStationResponse)

    serviceDelivery = findStationResponse["Trias"]["ServiceDelivery"]
    locationResultsList = serviceDelivery["DeliveryPayload"]["LocationInformationResponse"]["LocationResult"]
    validStops = []
    for locationResult in locationResultsList:
        for transportModes in locationResult["Mode"]:
            if(transportModes["PtMode"] == "rail") and (transportModes["RailSubmode"] == "suburbanRailway"):
                break
        else:
            continue
        ref  = locationResult["Location"]["StopPoint"]["StopPointRef"]
        name = locationResult["Location"]["StopPoint"]["StopPointName"]["Text"]
        validStops.append((name, ref))
    return validStops[0]

def getStopEvents(stationName, stationRef, numResults, lookIntoPast=timedelta(hours=2)):
    currentTime         = datetime.now().astimezone()
    departureAtStopTime = triasStrFromDatetime(currentTime - lookIntoPast)
    ptModeFilter        = {"Exclude": "false", "PtMode": "urbanRail", "RailSubmode": "suburbanRailway"}

    stopEventRequestXml = Path(base_dir/"StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest          = stopEventRequest["Trias"]["ServiceRequest"]
    stopEventRequestPayload = serviceRequest["RequestPayload"]["StopEventRequest"]
    stopEventRequestPayload["Location"]["LocationRef"]["StopPointRef"] = stationRef
    stopEventRequestPayload["Location"]["LocationRef"]["LocationName"] = {"Text": stationName}
    stopEventRequestPayload["Location"]["DepArrTime"]                  = departureAtStopTime
    stopEventRequestPayload["Params"] = {}
    stopEventRequestPayload["Params"]["PtModeFilter"]                  = ptModeFilter
    #operatorFilte = {"Exclude": "false", "OperatorRef": "ddb:00"}
    #stopEventRequestPayload["Params"]["OperatorFilter"]               = operatorFilter
    stopEventRequestPayload["Params"]["NumberOfResults"]               = numResults
    stopEventRequestPayload["Params"]["StopEventType"]                 = "both"
    stopEventRequestPayload["Params"]["IncludePreviousCalls"]          = "true"
    stopEventRequestPayload["Params"]["IncludeOnwardCalls"]            = "true"
    stopEventRequestPayload["Params"]["IncludeRealtimeData"]           = "true"

    stopEventResponse = sendRequest(stopEventRequest)
    return stopEventResponse

def combineAndFixStops(stopEvent):
    allStopsUnfiltered = []
    for callCat in ["PreviousCall", "ThisCall", "OnwardCall"]:
        stopOrStopsList = stopEvent["StopEvent"].get(callCat)
        if stopOrStopsList is not None:
            allStopsUnfiltered.extend(stopOrStopsList)

    #remove stops with identical stopPointRef, and fix indices
    duplicateCount = 0
    allStops = [allStopsUnfiltered[0]]
    for stopIdx in range(1, len(allStopsUnfiltered)):
        if allStopsUnfiltered[stopIdx]["CallAtStop"]["StopPointRef"] == allStops[-1]["CallAtStop"]["StopPointRef"]:
            duplicateCount += 1
            continue
        allStops.append(allStopsUnfiltered[stopIdx])
        seqNr = int(allStops[-1]["CallAtStop"]["StopSeqNumber"])
        allStops[-1]["CallAtStop"]["StopSeqNumber"] = str(seqNr - duplicateCount)
    return allStops

def extrapolateStopsWithClosestDelay(allStops):
    #make delayList
    extrapolatedStops = []
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = getArrAndDepTimes(thisCall)
        extrapolatedStops.append({
            "estArr":      estArr,
            "ttbArr":      ttbArr,
            "estDep":      estDep,
            "ttbDep":      ttbDep,
            "notServiced": (thisCall.get("NotServicedStop") == "true"),
        })

    #fill out non serviced stops
    for stopIdx in range(len(extrapolatedStops)):
        processedStop = extrapolatedStops[stopIdx]
        if processedStop["notServiced"]:
            #try to find realtime data before current stop
            for beforeStopIdx in range(stopIdx-1,-1,-1):
                estDep = extrapolatedStops[beforeStopIdx]["estDep"]
                if estDep is None:
                    continue
                ttbDep = extrapolatedStops[beforeStopIdx]["ttbDep"]
                delayBefore = (estDep - ttbDep)
                break
            else:
                delayBefore = None

            #try to find realtime data after current stop
            for afterStopIdx in range(stopIdx+1, len(extrapolatedStops)):
                estArr = extrapolatedStops[afterStopIdx]["estArr"]
                if estArr is None:
                    continue
                ttbArr = extrapolatedStops[afterStopIdx]["ttbArr"]
                delayAfter = (estArr - ttbArr)
            else:
                delayAfter = None

            if (delayBefore is not None) and (delayAfter is not None):
                processedStop["intermediateNotServiced"] = True
            else:
                processedStop["intermediateNotServiced"] = False

            if delayBefore is not None:
                if processedStop["ttbArr"]:
                    processedStop["estArr"] = processedStop["ttbArr"] + delayBefore
                if processedStop["ttbDep"]:
                    processedStop["estDep"] = processedStop["ttbDep"] + delayBefore
            elif delayAfter is not None:
                if processedStop["ttbArr"]:
                    processedStop["estArr"] = processedStop["ttbArr"] + delayAfter
                if processedStop["ttbDep"]:
                    processedStop["estDep"] = processedStop["ttbDep"] + delayAfter
            else:
                return None
        else:
            if (processedStop["estArr"]) is None and (processedStop["estDep"] is None):
                return None
    return extrapolatedStops

def getIncidentText(serviceData):
    incidentText = None
    attributes = serviceData.get("Attribute")
    if attributes:
        for att in attributes:
            if "Incident" in att["Code"]:
                if incidentText is not None:
                    logging.error(f'multiple incident messages {incidentText}, {att["Text"]["Text"]}')
                incidentText = att["Text"]["Text"]
    return incidentText

def hasAnyRealtimeData(allStops):
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = getArrAndDepTimes(thisCall)
        if (estArr is not None) or (estDep is not None):
            return True
    return False


def getArrAndDepTimes(thisCall):
    ttbArr = None
    estArr = None
    ttbDep = None
    estDep = None
    arrivalDict = thisCall.get("ServiceArrival")
    if arrivalDict is not None:
        ttbArr = datetimeFromTriasDatetimeStr(arrivalDict["TimetabledTime"])
        logging.debug(f"arriveTT: {ttbArr}")
        estArr  = datetimeFromTriasDatetimeStr(arrivalDict.get("EstimatedTime"))
        logging.debug(f"arriveES: {estArr}")
    departureDict = thisCall.get("ServiceDeparture")
    if departureDict is not None:
        ttbDep = datetimeFromTriasDatetimeStr(departureDict["TimetabledTime"])
        logging.debug(f"departTT: {ttbDep}")
        estDep  = datetimeFromTriasDatetimeStr(departureDict.get("EstimatedTime"))
        logging.debug(f"departES: {estArr}")
    return ttbArr, estArr, ttbDep, estDep
