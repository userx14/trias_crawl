from datetime import datetime, timezone, timedelta
import xmltodict
import requests
from pathlib import Path
import logging

logger = logging.getLogger("")
#logger.setLevel(logging.DEBUG)

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

    #import xmlschema
    #xmlschema.validate(requestAsXml, './trias_xsd/Trias.xsd')

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
    return validStops[0]

def delay_from_serviceCall(serviceCallDict):
    if serviceCallDict is None:
        return None
    timetableTime = datetimeFromTriasStr(serviceCallDict["TimetabledTime"])
    estimatedTime = datetimeFromTriasStr(serviceCallDict["EstimatedTime"])
    return (estimatedTime - timetableTime).total_seconds() / 60

def getAllDelaysThroughStation(passingThroughName, passingThroughRef, numResults=5, opRef=""):
    #query should also match trains that have already passed through the station some time ago
    currentTime         = datetime.now().astimezone()
    departureAtStopTime = triasStrFromDatetime(currentTime - timedelta(hours=1))
    operatorFilter      = {"Exclude": "false", "OperatorRef": "ddb:00"}
    ptModeFilter        = {"Exclude": "false", "PtMode": "urbanRail", "RailSubmode": "suburbanRailway"}

    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest   = stopEventRequest["Trias"]["ServiceRequest"]
    stopEventRequestPayload = serviceRequest["RequestPayload"]["StopEventRequest"]
    stopEventRequestPayload["Location"]["LocationRef"]["StopPointRef"] = passingThroughRef
    stopEventRequestPayload["Location"]["LocationRef"]["LocationName"] = {"Text": passingThroughName}
    #stopEventRequestPayload["Location"]["LocationRef"]["DepArrTime"]   = departureAtStopTime
    stopEventRequestPayload["Location"]["DepArrTime"]                  = departureAtStopTime
    stopEventRequestPayload["Params"] = {}
    stopEventRequestPayload["Params"]["PtModeFilter"]                  = ptModeFilter
    #stopEventRequestPayload["Params"]["OperatorFilter"]               = operatorFilter
    stopEventRequestPayload["Params"]["NumberOfResults"]               = numResults
    stopEventRequestPayload["Params"]["StopEventType"]                 = "both"
    stopEventRequestPayload["Params"]["IncludePreviousCalls"]          = "true"
    stopEventRequestPayload["Params"]["IncludeOnwardCalls"]            = "true"
    stopEventRequestPayload["Params"]["IncludeRealtimeData"]           = "true"


    stopEventResponse = sendRequest(stopEventRequest)
    printResponseStatistics(stopEventResponse)

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    delaysForJourneys = {}
    toEarly = 0
    toLate = 0
    inAcqT = 0
    error = 0

    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        serviceData = stopEvent["StopEvent"]["Service"]
        trainJourney     = serviceData["JourneyRef"]
        trainLineName    = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        trainOrigin      = serviceData["OriginText"]["Text"]
        trainDestination = serviceData["DestinationText"]["Text"]
        operatingDayRef  = serviceData["OperatingDayRef"]
        
        logger.info(f"{trainLineName} ({trainJourney}) from {trainOrigin} to {trainDestination}")
        
        allStops = []
        for cls in ["PreviousCall", "ThisCall", "OnwardCall"]:
            stopOrStopsList = stopEvent["StopEvent"].get(cls)
            if isinstance(stopOrStopsList, dict):
                allStops.append(stopOrStopsList)
            elif isinstance(stopOrStopsList, list):
                allStops.extend(stopOrStopsList)

        firstStop = allStops[0]
        lastStop  = allStops[-1]

        firstStopDeparture      = firstStop["CallAtStop"]["ServiceDeparture"]
        firstStopTimetDeparture = datetimeFromTriasStr(firstStopDeparture["TimetabledTime"])
        firstStopEstimDeparture = datetimeFromTriasStr(firstStopDeparture.get("EstimatedTime"))

        lastStopArrival      = lastStop["CallAtStop"]["ServiceArrival"]
        lastStopTimetArrival = datetimeFromTriasStr(lastStopArrival["TimetabledTime"])
        lastStopEstimArrival = datetimeFromTriasStr(lastStopArrival.get("EstimatedTime"))

        logger.info(f"from {firstStopTimetDeparture} to {lastStopTimetArrival}")

        #check if first stop is still in the future
        if currentTime < firstStopTimetDeparture:
            logging.info(f"train has not started yet, will start at {firstStopTimetDeparture}")
            toEarly += 1
            continue

        #check if the last stop in journey is already in the past
        if lastStopEstimArrival:
            if lastStopEstimArrival < currentTime:
                toLate += 1
                logging.info(f"train has already ended at final stop at estim {lastStopTimetArrival}")
                continue
        else:
            if lastStopTimetArrival < currentTime:
                toLate += 1
                logging.info(f"train has already ended at final stop at timet {lastStopTimetArrival}")
                continue

        #check which stop whas the last passed one
        delay = None
        nextStopEstimArrival = None
        for stop in allStops[::-1]:
            stopNumber = allStops.index(stop)
            stopPointName = stop["CallAtStop"]["StopPointName"]["Text"]
            departureDict = stop["CallAtStop"].get("ServiceDeparture")
            if departureDict is not None:
                timetableDeparture = datetimeFromTriasStr(departureDict["TimetabledTime"])
                logging.debug(f"departTT: {timetableDeparture}")
                estimateDeparture  = datetimeFromTriasStr(departureDict.get("EstimatedTime"))
                logging.debug(f"departES: {estimateDeparture}")
            arrivalDict = stop["CallAtStop"].get("ServiceArrival")
            if arrivalDict is not None:
                timetableArrival = datetimeFromTriasStr(arrivalDict["TimetabledTime"])
                logging.debug(f"arriveTT: {timetableArrival}")
                estimateArrival  = datetimeFromTriasStr(arrivalDict.get("EstimatedTime"))
                logging.debug(f"arriveES: {estimateArrival}")

            #check if stop has been reached
            if (departureDict is not None) and (estimateDeparture is not None) and (estimateDeparture < currentTime):
                #train has left station
                delay = estimateDeparture - timetableDeparture
                durationTravelingBetweenStops = currentTime - estimateDeparture
                durationEstimatedBetweenStops = nextStopEstimArrival - estimateDeparture
                progressToNextStop = durationTravelingBetweenStops / durationEstimatedBetweenStops
                break
            elif (arrivalDict is not None) and (estimateArrival is not None) and (estimateArrival < currentTime):
                #train is waiting at station
                delay = estimateArrival - timetableArrival
                progressToNextStop = 0
                break
            nextStopEstimArrival = estimateArrival
        else:
            error += 1
            print("probably error, no delay info")


        currentStopName = stop["CallAtStop"]["StopPointName"]["Text"]
        currentStopRef = stop["CallAtStop"]["StopPointRef"]
        print(f"delay: {delay}, at station {currentStopName}")
        inAcqT += 1
        if serviceData.get("Cancelled") == "true":
            logging.error(allStops)
            logging.error("cancelled train :)")
        if serviceData.get("Unplanned") == "true":
            logging.error("Unplanned train :)")
        if serviceData.get("Deviation") == "true":
            logging.error("Deviated train :)")
        attributes = serviceData.get("Attribute")
        incidentText = None
        if attributes:
            #if there is only a single attribute, make it a list so the following code can correctely handle it
            attributes = attributes if isinstance(attributes, list) else [attributes]
            for att in attributes:
                if "Incident" in att["Code"]:
                    incidentText = att["Text"]["Text"]
                    print(f"warning incident report: {incidentText}")

        if delay is not None:
            delay = delay.total_seconds()/60
        delaysForJourneys[(trainJourney, operatingDayRef)] = {
            "delay":            delay, 
            "lineName":         trainLineName, 
            "incidentText":     incidentText,
            "currentStopName":  currentStopName,
            "currentStopRef":   currentStopRef,
            "destination":      trainDestination,
            "progressNextStop": progressToNextStop,
        }
    print(f"Stats: e{toEarly}, l{toLate}, a{inAcqT}, err{error}")
    return delaysForJourneys

"""
print(stopPointRef_from_LocationName("Esslingen (Neckar)"))
exit(0)
"""

def getCurrentRunningTrains():
    checkAtStations = [
        ('Zuffenhausen',       'de:08111:6465'),
        ('Vaihingen',          'de:08111:6002'),
        ('Ludwigsburg',        'de:08118:7402'),
        ('Renningen',          'de:08115:7302'),
        ('Böblingen',          'de:08115:7100'),
        ('Bad Cannstatt',      'de:08111:6333'),
        ('Schwabstraße',       'de:08111:6052'),
        ('Waiblingen',         'de:08119:7604'),
        ('Esslingen (Neckar)', 'de:08116:7800'),
    ]

    delayInfoDict = {}
    for stationTuple in checkAtStations:
        print(f"station {stationTuple[0]}")
        delayInfoDict |= getAllDelaysThroughStation(*stationTuple, numResults=100)

    delayInfoDict = dict(sorted(delayInfoDict.items()))
    
    return delayInfoDict
    """
    delayPerLine = {}
    for journeyRefAndDay, delayData in delayInfoDict.items():
        print(f"{journeyRefAndDay[0]}: {delayData}")
        delayLineName = delayData['lineName']
        delayInMin = delayData['delay']
        if delayLineName in delayPerLine.keys():
            delayPerLine[delayLineName].append(delayInMin)
        else:
            delayPerLine[delayLineName] = [delayInMin]

    print(delayPerLine)
    """
#print(getCurrentRunningTrains())
