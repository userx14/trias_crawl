from datetime import datetime, timezone, timedelta
import xmltodict
import requests
from pathlib import Path
import logging

logger = logging.getLogger("")
logger.setLevel(logging.DEBUG)

url = "https://efa-bw.de/trias"
requestorKey = open(Path("./requestor.key")).read()
namespaces = {
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
    response = requests.post(url, data=requestAsXml, headers=requestHeader)
    return xmltodict.parse(response.content, process_namespaces=True, namespaces=namespaces)

def datetimeFromTriasStr(triasStr):
    if triasStr is None:
        return None
    time = datetime.strptime(triasStr, "%Y-%m-%dT%H:%M:%SZ")
    time = time.replace(tzinfo=timezone.utc)
    time = time.astimezone() #convert to local timezone
    return time

def triasStrFromDatetime(datetimeObj):
    datetimeObj = datetimeObj.astimezone(timezone.utc)
    return datetimeObj.strftime("%Y-%m-%dT%H:%M:%SZ")


def printResponseStatistics(responseDict):
    serviceDelivery   = responseDict["Trias"]["ServiceDelivery"]
    responseTimestamp = datetimeFromTriasStr(serviceDelivery["siri:ResponseTimestamp"])
    print(f"Response timestamp: {responseTimestamp}")

    calculationTime = serviceDelivery["CalcTime"]
    print(f"Calculation time: {calculationTime}")

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
    if not isinstance(locationResultsList, list):
        locationResultsList = [locationResultsList]
    validStops = []
    for locationResult in locationResultsList:
        transportModesList = locationResult["Mode"]
        if not isinstance(transportModesList, list):
            transportModesList = [transportModesList]
        for transportModes in transportModesList:
            if(transportModes["PtMode"] == "rail") and (transportModes["RailSubmode"] == "suburbanRailway"):
                break
        else:
            continue
        ref  = locationResult["Location"]["StopPoint"]["StopPointRef"]
        name = locationResult["Location"]["StopPoint"]["StopPointName"]["Text"]
        validStops.append((name, ref))
    print(validStops)
    return validStops[0][1]

def delay_from_serviceCall(serviceCallDict):
    if serviceCallDict is None:
        return None
    timetableTime = datetimeFromTriasStr(serviceCallDict["TimetabledTime"])
    estimatedTime = datetimeFromTriasStr(serviceCallDict["EstimatedTime"])
    return (estimatedTime - timetableTime).total_seconds() / 60

def getAllDelaysThroughStation(passingThroughRef, numResults=5, opRef=""):
    #query should also match trains that have already passed through the station some time ago
    currentTime         = datetime.now().astimezone()
    departureAtStopTime = triasStrFromDatetime(currentTime - timedelta(hours=4))
    operatorFilter      = {"Exclude": "false", "OperatorRef": "ddb:00"}

    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)


    serviceRequest   = stopEventRequest["Trias"]["ServiceRequest"]
    stopEventRequestPayload = serviceRequest["RequestPayload"]["StopEventRequest"]
    stopEventRequestPayload["Location"]["LocationRef"]["StopPointRef"] = passingThroughRef
    stopEventRequestPayload["Location"]["LocationRef"]["DepArrTime"]   = departureAtStopTime
    print(stopEventRequestPayload["Location"]["LocationRef"])
    stopEventRequestPayload["Params"]["OperatorFilter"]                = operatorFilter
    stopEventRequestPayload["Params"]["IncludePreviousCalls"]          = "true"
    stopEventRequestPayload["Params"]["IncludeOnwardCalls"]            = "true"
    stopEventRequestPayload["Params"]["IncludeRealtimeData"]           = "true"
    stopEventRequestPayload["Params"]["NumberOfResults"]               = numResults

    stopEventResponse = sendRequest(stopEventRequest)
    printResponseStatistics(stopEventResponse)

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    delaysForLines = {}
    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        
        serviceData   = stopEvent["StopEvent"]["Service"]
        trainJourney     = serviceData["JourneyRef"]
        trainLineName    = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        trainOrigin      = serviceData["OriginText"]["Text"]
        trainDestination = serviceData["DestinationText"]["Text"]
        
        print(f"{trainLineName} ({trainJourney}) from {trainOrigin} to {trainDestination}")
        
        previousStops = stopEvent["StopEvent"].get("PreviousCall") or []
        thisStop      = stopEvent["StopEvent"].get("ThisCall")
        nextStops     = stopEvent["StopEvent"].get("OnwardCall") or []
        allStops      = previousStops + [thisStop] + nextStops
        
        firstStopCall = allStops[0]["CallAtStop"]
        firstStopDeparture = datetimeFromTriasStr(firstStopCall["ServiceDeparture"]["TimetabledTime"])
        lastStopCall = allStops[-1]["CallAtStop"]
        lastStopArrival = datetimeFromTriasStr(lastStopCall["ServiceArrival"]["TimetabledTime"])
        print(f"from {firstStopDeparture} to {lastStopArrival}")

        #check if last first stop in journey before the current time
        
        departureDict = firstStopCall.get("ServiceDeparture")
        timetableDeparture = datetimeFromTriasStr(departureDict["TimetabledTime"])
        if currentTime < timetableDeparture:
            logging.info(f"train has not started yet, will start at {timetableDeparture}")
            continue

        #check which stop whas the last passed one
        delay = None
        for stop in allStops[::-1]:
            departureDict = stop["CallAtStop"].get("ServiceDeparture")
            if departureDict is not None:
                timetableDeparture = datetimeFromTriasStr(departureDict["TimetabledTime"])
                estimateDeparture  = datetimeFromTriasStr(departureDict.get("EstimatedTime"))
            arrivalDict = stop["CallAtStop"].get("ServiceArrival")
            if arrivalDict is not None:
                timetableArrival = datetimeFromTriasStr(arrivalDict["TimetabledTime"])
                estimateArrival  = datetimeFromTriasStr(arrivalDict.get("EstimatedTime"))

            #check if stop has been reached
            if (departureDict is not None) and (estimateArrival < currentTime):
                delay = estimateDeparture - timetableDeparture
                break
            if (arrivalDict is not None) and (estimateArrival < currentTime):
                delay = estimateArrival - timetableArrival
                break
        #check if train has already arrived at last stop
        if stop == allStops[-1]:
            logging.info("train has already arrived at final stop")
            print("====\n\n")
            continue
        currentStopName = stop["CallAtStop"]["StopPointName"]["Text"]
        print(f"delay: {delay}, at station {currentStopName}")
        

        if serviceData.get("Cancelled") == "true":
            logging.error("cancelled train :)")
        if serviceData.get("Unplanned") == "true":
            logging.error("Unplanned train :)")
        if serviceData.get("Deviation") == "true":
            logging.error("Deviated train :)")

        for att in serviceData["Attribute"]:
            if "Incident" in att["Code"]:
                incidentText = att["Text"]["Text"]
                print(f"warning incident report: {incidentText}")
        
        if delay is not None:
            delay = delay.total_seconds()/60
        if trainLineName not in delaysForLines.keys():
            delaysForLines[trainLineName] = [delay]
        else:
            delaysForLines[trainLineName].append(delay)
        
    return delaysForLines






#print(stopPointRef_from_LocationName("Zuffenhausen"))
#exit(0)
zuffenhausen= "de:08111:6465"
schwabstraßeRef= "de:08111:6052"
stadtmitteRef    = "de:08111:6052"
hauptbahnhofRef = "de:08111:6118"

print(getAllDelaysThroughStation(hauptbahnhofRef, numResults=50))