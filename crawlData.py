from datetime import datetime, timezone, timedelta
import xmltodict
import requests
from pathlib import Path
import logging
import sqlite3
import json

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


def printResponseStatistics(responseDict):
    serviceDelivery   = responseDict["Trias"]["ServiceDelivery"]
    responseTimestamp = datetimeFromTriasDatetimeStr(serviceDelivery["siri:ResponseTimestamp"])
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

def delaySeconds_from_serviceCall(serviceCallDict):
    if serviceCallDict is None:
        return None
    timetableTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("TimetabledTime"))
    estimatedTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("EstimatedTime"))
    if timetableTime is None or estimatedTime is None:
        return None
    return (estimatedTime - timetableTime).total_seconds()

def getAllDelaysThroughStation(passingThroughName, passingThroughRef, numResults=5, opRef=""):
    #query should also match trains that have already passed through the station some time ago
    currentTime         = datetime.now().astimezone()
    departureAtStopTime = triasStrFromDatetime(currentTime - timedelta(hours=2))
    operatorFilter      = {"Exclude": "false", "OperatorRef": "ddb:00"}
    ptModeFilter        = {"Exclude": "false", "PtMode": "urbanRail", "RailSubmode": "suburbanRailway"}

    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest   = stopEventRequest["Trias"]["ServiceRequest"]
    stopEventRequestPayload = serviceRequest["RequestPayload"]["StopEventRequest"]
    stopEventRequestPayload["Location"]["LocationRef"]["StopPointRef"] = passingThroughRef
    stopEventRequestPayload["Location"]["LocationRef"]["LocationName"] = {"Text": passingThroughName}
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
    
    liveJourneys = {}
    loggedJourneys = []
    
    toEarly = 0
    toLate = 0
    inAcqT = 0
    error = 0

    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        serviceData      = stopEvent["StopEvent"]["Service"]
        trainJourney     = serviceData["JourneyRef"]
        trainLineName    = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        trainOrigin      = serviceData["OriginText"]["Text"]
        trainDestination = serviceData["DestinationText"]["Text"]
        operatingDayRef  = datetimeFromTriasDateStr(serviceData["OperatingDayRef"])
        
        if "S" not in trainLineName:
            continue

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
        firstStopTimetDeparture = datetimeFromTriasDatetimeStr(firstStopDeparture["TimetabledTime"])
        firstStopEstimDeparture = datetimeFromTriasDatetimeStr(firstStopDeparture.get("EstimatedTime"))

        lastStopArrival      = lastStop["CallAtStop"]["ServiceArrival"]
        lastStopTimetArrival = datetimeFromTriasDatetimeStr(lastStopArrival["TimetabledTime"])
        lastStopEstimArrival = datetimeFromTriasDatetimeStr(lastStopArrival.get("EstimatedTime"))

        logger.info(f"from {firstStopTimetDeparture} to {lastStopTimetArrival}")

        #check if first stop is still in the future
        if currentTime < firstStopTimetDeparture:
            logging.info(f"train has not started yet, will start at {firstStopTimetDeparture}")
            toEarly += 1
            continue

        #check if journey is finished, the add it to the loggedJourneyList
        if ((lastStopEstimArrival is not None) and (lastStopEstimArrival < currentTime)) or (lastStopTimetArrival < currentTime):
            toLate += 1
            #log this journey as completed for statistics
            processedStopsList = []
            for stop in allStops:
                thisCall       = stop["CallAtStop"]
                departureDict  = thisCall.get("ServiceDeparture")
                arrivalDict    = thisCall.get("ServiceArrival")
                timetableDeparture = None
                estimateDeparture  = None
                timetableArrival   = None
                estimateArrival    = None
                if departureDict is not None:
                    timetableDeparture = departureDict.get("TimetabledTime")
                    if timetableDeparture is not None:
                        timetableDeparture = datetimeFromTriasDatetimeStr(timetableDeparture)
                    estimateDeparture  = departureDict.get("EstimatedTime")
                    if estimateDeparture is not None:
                        estimateDeparture  = datetimeFromTriasDatetimeStr(estimateDeparture)
                if arrivalDict is not None:
                    timetableArrival = arrivalDict.get("TimetabledTime")
                    if timetableArrival is not None:
                        timetableArrival = datetimeFromTriasDatetimeStr(timetableArrival)
                    estimateArrival  = arrivalDict.get("EstimatedTime")
                    if estimateArrival is not None:
                        estimateArrival  = datetimeFromTriasDatetimeStr(estimateArrival)
                processedStopsList.append({
                    "journeyRef":          serviceData["JourneyRef"],
                    "operatingDay":        operatingDayRef.timestamp(),
                    "stopIndex":           thisCall["StopSeqNumber"],
                    "stopPointName":       thisCall["StopPointName"]["Text"],
                    "stopPointRef":        thisCall["StopPointRef"],
                    "notServiced":         (thisCall.get("NotServicedStop") == "true"),
                    "departureTimetable":  timetableDeparture.timestamp() if timetableDeparture is not None else None,
                    "departureEstimate":   estimateDeparture.timestamp() if estimateDeparture is not None else None,
                    "arrivalTimetable":    timetableArrival.timestamp() if timetableArrival is not None else None,
                    "arrivalEstimate":     estimateArrival.timestamp() if estimateArrival is not None else None,
                })
                
            incidentText = None
            attributes = serviceData.get("Attribute")
            if attributes:
                #if there is only a single attribute, make it a list so the following code can correctely handle it
                attributes = attributes if isinstance(attributes, list) else [attributes]
                for att in attributes:
                    if "Incident" in att["Code"]:
                        if incidentText is not None:
                            logging.error(f'multiple incident messages {incidentText}, {att["Text"]["Text"]}')
                        incidentText = att["Text"]["Text"]
            loggedJourneys.append({
                "journeyRef":           serviceData["JourneyRef"],
                "operatingDay":         operatingDayRef.timestamp(),
                "trainLineName":        trainLineName,
                "trainDestination":     trainDestination,
                "trainOrigin":          trainOrigin,
                "trainIncidentMessage": incidentText,
                "isCancelled":          (serviceData.get("Cancelled") == "true"),
                "isUnplanned":          (serviceData.get("Unplanned") == "true"),
                "isDeviated":           (serviceData.get("Deviation") == "true"),
                "stopsList":            processedStopsList,
            })
            logging.info(f"train has already ended at final stop at estim {lastStopTimetArrival}")
            continue
            
        delayMinutes         = None
        nextStopEstimArrival = None #for calculating progress in between stations
        trainCancelled       = False
        progressToNextStop   = 0
        for stop in allStops[::-1]:
            thisCall        = stop["CallAtStop"]
            stopNumber      = allStops.index(stop)
            notServicedStop = thisCall.get("NotServicedStop")
            departureDict   = thisCall.get("ServiceDeparture")
            stopPointName   = thisCall["StopPointName"]["Text"]
            if departureDict is not None:
                timetableDeparture = datetimeFromTriasDatetimeStr(departureDict["TimetabledTime"])
                logging.debug(f"departTT: {timetableDeparture}")
                estimateDeparture  = datetimeFromTriasDatetimeStr(departureDict.get("EstimatedTime"))
                logging.debug(f"departES: {estimateDeparture}")
            arrivalDict = thisCall.get("ServiceArrival")
            if arrivalDict is not None:
                timetableArrival = datetimeFromTriasDatetimeStr(arrivalDict["TimetabledTime"])
                logging.debug(f"arriveTT: {timetableArrival}")
                estimateArrival  = datetimeFromTriasDatetimeStr(arrivalDict.get("EstimatedTime"))
                logging.debug(f"arriveES: {estimateArrival}")

            if notServicedStop:
                #go back to last station with a delay
                tempDelay = None
                for previousStopIdx, previousStop in enumerate(allStops[:stopNumber:-1]):
                    for serviceKeys in ["ServiceArrival", "ServiceDeparture"]:
                        tempDelay = delaySeconds_from_serviceCall(thisCall.get(serviceKeys))
                        if tempDelay is not None:
                            lastDelay = timedelta(tempDelay)
                            lastStationWithDelay = previousStopIdx
                if tempDelay is None:
                    #no realtime info, use timetable data
                    if (departureDict is not None) and (timetableDeparture < currentTime):
                        trainCancelled = True
                        break
                    elif (arrivalDict is not None) and (timetableArrival < currentTime):
                        trainCancelled = True
                        break
                else:
                    #realtime info, continue delay for non serviced stops
                    if (timetableDeparture+lastDelay < currentTime):
                        trainCancelled = True
                        break
                    elif (timetableArrival+lastDelay < currentTime):
                        trainCancelled = True
                        break
            else:
                #train has just passed this stop and is on way to next station
                if (departureDict is not None) and (estimateDeparture is not None) and (estimateDeparture < currentTime): 
                    
                    delayMinutes = delaySeconds_from_serviceCall(departureDict)/60
                    durationTravelingBetweenStops = currentTime - estimateDeparture
                    durationEstimatedBetweenStops = nextStopEstimArrival - estimateDeparture
                    progressToNextStop = durationTravelingBetweenStops / durationEstimatedBetweenStops
                    break
                #train is currently waiting at this station
                if (arrivalDict is not None) and (estimateArrival is not None) and (estimateArrival < currentTime):
                    #train is waiting at station
                    delayMinutes = delaySeconds_from_serviceCall(arrivalDict)/60
                    progressToNextStop = 0
                    break
                nextStopEstimArrival = estimateArrival
        else:
            error += 1
            logger.error(f"no delay info for {trainLineName}, {trainJourney}, {serviceData}")
            continue


        currentStopName = thisCall["StopPointName"]["Text"]
        currentStopRef  = thisCall["StopPointRef"]


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
        if trainCancelled:
            liveJourneys[trainJourney+":"+str(operatingDayRef)] = {
                "delay":            None,
                "lineName":         trainLineName,
                "incidentText":     incidentText,
                "currentStopName":  currentStopName,
                "currentStopRef":   currentStopRef,
                "destination":      trainDestination,
                "progressNextStop": progressToNextStop,
                "cancelled":        True,
            }
        else:
            liveJourneys[trainJourney+":"+str(operatingDayRef)] = {
                "delay":            delayMinutes,
                "lineName":         trainLineName,
                "incidentText":     incidentText,
                "currentStopName":  currentStopName,
                "currentStopRef":   currentStopRef,
                "destination":      trainDestination,
                "progressNextStop": progressToNextStop,
                "cancelled":        False
            }
    return loggedJourneys, liveJourneys

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

    allLiveJourneys = {}
    allLoggedJourneys = []
    for stationTuple in checkAtStations:
        print(f"station {stationTuple[0]}")
        loggedJourneys, liveJourneys = getAllDelaysThroughStation(*stationTuple, numResults=100)
        allLiveJourneys   |= liveJourneys
        allLoggedJourneys += loggedJourneys
    allLiveJourneys = dict(sorted(allLiveJourneys.items()))
    return allLoggedJourneys, allLiveJourneys


sqlJourneyTableInit = """
CREATE TABLE IF NOT EXISTS journeys (
    operatingDay         INTEGER NOT NULL,      /*unix time utc*/
    journeyRef           TEXT,
    trainLineName        TEXT,
    trainOrigin          TEXT,
    trainDestination     TEXT,
    trainIncidentMessage TEXT,
    isCancelled          INTEGER,               /*boolean*/
    isUnplanned          INTEGER,               /*boolean*/
    isDeviated           INTEGER,               /*boolean*/
    PRIMARY KEY (operatingDay, journeyRef)
);"""

sqlStopTableInit = """CREATE TABLE IF NOT EXISTS stops (
    operatingDay        INTEGER NOT NULL,       /*unix time utc*/
    journeyRef          TEXT NOT NULL,
    stopIndex           INTEGER NOT NULL,
    stopPointName       TEXT,
    stopPointRef        TEXT,
    notServiced         INTEGER,                /*boolean*/
    departureTimetable  INTEGER,                /*unix time utc*/
    departureEstimate   INTEGER,                /*unix time utc*/
    arrivalTimetable    INTEGER,                /*unix time utc*/
    arrivalEstimate     INTEGER,                /*unix time utc*/
    PRIMARY KEY (operatingDay, journeyRef, stopIndex),
    FOREIGN KEY (operatingDay, journeyRef) REFERENCES journeys(operatingDay, journeyRef)
);
"""

connection = sqlite3.connect('loggedJourney_2026.db')
cursor = connection.cursor()
cursor.execute(sqlJourneyTableInit)
cursor.execute(sqlStopTableInit)
connection.commit()

def insertJourneyInDb(connection, journey):
    journey_keys = [
        "operatingDay", "journeyRef", "trainLineName", 
        "trainOrigin", "trainDestination", "trainIncidentMessage", 
        "isCancelled", "isUnplanned", "isDeviated",
    ]
    journey_data = tuple(journey[key] for key in journey_keys)
    insert_journey_data = f'''
        INSERT OR REPLACE INTO journeys ({', '.join(journey_keys)})
        VALUES ({', '.join(['?'] * len(journey_keys))});
    '''
    cursor.execute(insert_journey_data, journey_data)
    
    for stop in loggedJourney["stopsList"]:
        stop_keys = [
            "operatingDay", "journeyRef", "stopIndex",
            "stopPointName", "stopPointRef", "notServiced",
            "departureTimetable", "departureEstimate", "arrivalTimetable",
            "arrivalEstimate",   
        ]
        stop_data = tuple(stop[key] for key in stop_keys)
        insert_stop_data = f'''
            INSERT OR REPLACE INTO stops ({', '.join(stop_keys)})
            VALUES ({', '.join(['?'] * len(stop_keys))});
        '''
        cursor.execute(insert_stop_data, stop_data)
        

allLoggedJourneys, allLiveJourneys = getCurrentRunningTrains()
for loggedJourney in allLoggedJourneys:
    insertJourneyInDb(connection, loggedJourney)
connection.commit()
cursor.close()
connection.close()

with open("./currentRunningTrains.json", "w") as outputfile:
    allLoggedJourneys, allLiveJourneys = getCurrentRunningTrains()
    
    outputfile.write(json.dumps(allLiveJourneys, indent=4))
"""

    delayPerLine = {}
    for journeyRefAndDay, delayData in allTrainsDict.items():
        print(f"{journeyRefAndDay}: {delayData}")
        delayLineName = delayData['lineName']
        delayInMin = delayData['delay']
        if delayLineName in delayPerLine.keys():
            delayPerLine[delayLineName].append(delayInMin)
        else:
            delayPerLine[delayLineName] = [delayInMin]

    print(delayPerLine)
    """
