from datetime import datetime, timezone, timedelta
import xmltodict
import requests
from pathlib import Path
import logging
import sqlite3
import json
import subprocess
import traceback

base_dir      = Path(__file__).parent
logging.basicConfig(
    filename=base_dir/"error.log",
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s'
)

url           = "https://efa-bw.de/trias"
requestorKey  = open(base_dir/"requestor.key").read()
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
    return validStops[0]

def delaySeconds_from_serviceCall(serviceCallDict):
    if serviceCallDict is None:
        return None
    timetableTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("TimetabledTime"))
    estimatedTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("EstimatedTime"))
    if timetableTime is None or estimatedTime is None:
        return None
    return (estimatedTime - timetableTime).total_seconds()

def getIncidentText(serviceData):
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
    return incidentText

def logJourney(serviceData, allStops): #convert this journey into a compressed form for statistics db
    operatingDayRef = datetimeFromTriasDateStr(serviceData["OperatingDayRef"])
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
                timetableDeparture = timetableDeparture.timestamp()
            estimateDeparture  = departureDict.get("EstimatedTime")
            if estimateDeparture is not None:
                estimateDeparture = datetimeFromTriasDatetimeStr(estimateDeparture)
                estimateDeparture = estimateDeparture.timestamp()
        if arrivalDict is not None:
            timetableArrival = arrivalDict.get("TimetabledTime")
            if timetableArrival is not None:
                timetableArrival = datetimeFromTriasDatetimeStr(timetableArrival)
                timetableArrival = timetableArrival.timestamp()
            estimateArrival  = arrivalDict.get("EstimatedTime")
            if estimateArrival is not None:
                estimateArrival = datetimeFromTriasDatetimeStr(estimateArrival)
                estimateArrival = estimateArrival.timestamp()
        processedStopsList.append({
            "journeyRef":          serviceData["JourneyRef"],
            "operatingDay":        operatingDayRef.timestamp(),
            "stopIndex":           thisCall["StopSeqNumber"],
            "stopPointName":       thisCall["StopPointName"]["Text"],
            "stopPointRef":        thisCall["StopPointRef"],
            "notServiced":         (thisCall.get("NotServicedStop") == "true"),
            "departureTimetable":  timetableDeparture,
            "departureEstimate":   estimateDeparture,
            "arrivalTimetable":    timetableArrival,
            "arrivalEstimate":     estimateArrival,
        })
    return {
        "journeyRef":           serviceData["JourneyRef"],
        "operatingDay":         operatingDayRef.timestamp(),
        "trainLineName":        serviceData["ServiceSection"]["PublishedLineName"]["Text"],
        "trainDestination":     serviceData["DestinationText"]["Text"],
        "trainOrigin":          serviceData["OriginText"]["Text"],
        "trainIncidentMessage": getIncidentText(serviceData),
        "isCancelled":          (serviceData.get("Cancelled") == "true"),
        "isUnplanned":          (serviceData.get("Unplanned") == "true"),
        "isDeviated":           (serviceData.get("Deviation") == "true"),
        "stopsList":            processedStopsList,
    }

def compareAllStopsToCurrentTime(allStops, currentTime):
    firstStop = allStops[0]
    lastStop  = allStops[-1]

    firstStopDeparture      = firstStop["CallAtStop"]["ServiceDeparture"]
    firstStopTimetDeparture = datetimeFromTriasDatetimeStr(firstStopDeparture["TimetabledTime"])
    firstStopEstimDeparture = datetimeFromTriasDatetimeStr(firstStopDeparture.get("EstimatedTime"))

    lastStopArrival      = lastStop["CallAtStop"]["ServiceArrival"]
    lastStopTimetArrival = datetimeFromTriasDatetimeStr(lastStopArrival["TimetabledTime"])
    lastStopEstimArrival = datetimeFromTriasDatetimeStr(lastStopArrival.get("EstimatedTime"))

    #check if first stop is still in the future
    if currentTime < firstStopTimetDeparture:
        logging.debug(f"train has not started yet, will start at {firstStopTimetDeparture}")
        return -1

    #check if journey is finished, the add it to the loggedJourneyList
    if ((lastStopEstimArrival is not None) and (lastStopEstimArrival < currentTime)) or (lastStopTimetArrival < currentTime):
        return 1

    return 0

def getArrAndDepTimes(thisCall):
    ttbArr = None
    estArr = None
    ttbDep = None
    estDep = None
    departureDict = thisCall.get("ServiceDeparture")
    if departureDict is not None:
        ttbDep = datetimeFromTriasDatetimeStr(departureDict["TimetabledTime"])
        logging.debug(f"departTT: {ttbDep}")
        estArr  = datetimeFromTriasDatetimeStr(departureDict.get("EstimatedTime"))
        logging.debug(f"departES: {estArr}")
    arrivalDict = thisCall.get("ServiceArrival")
    if arrivalDict is not None:
        ttbArr = datetimeFromTriasDatetimeStr(arrivalDict["TimetabledTime"])
        logging.debug(f"arriveTT: {ttbArr}")
        estArr  = datetimeFromTriasDatetimeStr(arrivalDict.get("EstimatedTime"))
        logging.debug(f"arriveES: {estArr}")
    return ttbArr, estArr, ttbDep, estArr

def getLiveJourney(serviceData, allStops, currentTime, liveJourneyDict):
    #make delayList
    processedStopList = []
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = getArrAndDepTimes(thisCall)
        processedStopList.append({
            "estArr":      estArr,
            "ttbArr":      ttbArr,
            "estDep":      estDep,
            "ttbDep":      ttbDep,
            "notServiced": (thisCall.get("NotServicedStop") == "true"),
        })

    #fill out non serviced stops
    for stopIdx in range(len(processedStopList)):
        processedStop = processedStopList[stopIdx]
        if processedStop["notServiced"]:
            #try to find realtime data before current stop
            for beforeStopIdx in range(stopIdx-1,-1,-1):
                estDep = processedStopList[beforeStopIdx]["estDep"]
                if estDep is None:
                    continue
                ttbDep = processedStopList[beforeStopIdx]["ttbDep"]
                delayBefore = (estDep - ttbDep)
                break
            else:
                delayBefore = None

            #try to find realtime data after current stop
            for afterStopIdx in range(stopIdx+1, len(processedStopList)):
                estArr = processedStopList[afterStopIdx]["estArr"]
                if estArr is None:
                    continue
                ttbArr = processedStopList[afterStopIdx]["ttbArr"]
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
                logging.debug("insufficient live data")
                return 0
        else:
            if (processedStop["estArr"]) is None and (processedStop["estDep"] is None):
                logging.debug("nonexistent live data")
                return 0

    if processedStopList[-1]["estArr"] < currentTime:
        return 1 #train has already ended

    if currentTime < processedStopList[0]["ttbDep"]:
        return -1 #train has not yet started

    for currentStopIdx in range(len(processedStopList)-2, 0, -1): #exclude first stop
        processedStop = processedStopList[currentStopIdx]
        if processedStop["estDep"] < currentTime:
            #train left this station and is on the way to the next
            progressToNextStop = None #still needs to be calculated
            delay = processedStop["estDep"] - processedStop["ttbDep"]
            break
            #find next station

        elif processedStop["estArr"] < currentTime:
            #train is at this station
            progressToNextStop = 0.0
            delay = processedStop["estArr"] - processedStop["ttbArr"]
            break
    else:
        if processedStop["estDep"] < currentTime:
            #train left this station and is on the way to the next
            progressToNextStop = None #still needs to be calculated
        else:
            progressToNextStop = 0.0
        delay = processedStop["estDep"] - processedStop["ttbDep"]
    delay = delay.total_seconds()
    cancelled = False
    if processedStopList[currentStopIdx]["notServiced"]:
        if not processedStopList[currentStopIdx]["intermediateNotServiced"]:
            cancelled = True

    #find next valid stop
    for nextStopIdx in range(currentStopIdx+1, len(processedStopList)):
        if processedStopList[nextStopIdx]["notServiced"]:
            if not processedStopList[nextStopIdx]["intermediateNotServiced"]:
                cancelled = True
            else:
                continue
        break
    if progressToNextStop is None:
        progressToNextStop = currentTime - processedStopList[currentStopIdx]["estDep"]
        progressToNextStop /= processedStopList[nextStopIdx]["estArr"] - processedStopList[currentStopIdx]["estDep"]

    currentStopName = allStops[currentStopIdx]["CallAtStop"]["StopPointName"]["Text"]
    currentStopRef  = allStops[currentStopIdx]["CallAtStop"]["StopPointRef"]
    nextStopName    = allStops[nextStopIdx]["CallAtStop"]["StopPointName"]["Text"]
    nextStopRef     = allStops[nextStopIdx]["CallAtStop"]["StopPointRef"]

    if serviceData.get("Unplanned") == "true":
        logging.error("Unplanned train :)")
    if serviceData.get("Deviation") == "true":
        logging.error("Deviated train :)")

    liveJourney = {
        "delay":            delay / 60,
        "lineName":         serviceData["ServiceSection"]["PublishedLineName"]["Text"],
        "incidentText":     getIncidentText(serviceData),
        "currentStopName":  currentStopName,
        "currentStopRef":   currentStopRef,
        "nextStopName":     nextStopName,
        "nextStopRef":      nextStopRef,
        "destination":      serviceData["DestinationText"]["Text"],
        "origin":           serviceData["OriginText"]["Text"],
        "progressNextStop": progressToNextStop,
        "cancelled":        cancelled
    }

    trainJourneyRef  = serviceData["JourneyRef"]
    operatingDayRef  = datetimeFromTriasDateStr(serviceData["OperatingDayRef"]).strftime("%Y.%m.%d")
    if not any([trainJourneyRef in iterRef for iterRef in liveJourneyDict.keys()]): #block duplicating journey around midnight
        liveJourneyDict[trainJourneyRef+":"+operatingDayRef] = liveJourney
    return 0

def acquireTrainLineFilter(lineName):
    if "S" in lineName:
        return True
    return False


def getAllDelaysThroughStation(passingThroughName, passingThroughRef, liveJourneysDict, numResults=5, opRef=""):
    #query should also match trains that have already passed through the station some time ago
    currentTime         = datetime.now().astimezone()
    departureAtStopTime = triasStrFromDatetime(currentTime - timedelta(hours=2))
    operatorFilter      = {"Exclude": "false", "OperatorRef": "ddb:00"}
    ptModeFilter        = {"Exclude": "false", "PtMode": "urbanRail", "RailSubmode": "suburbanRailway"}

    stopEventRequestXml = Path(base_dir/"StopEventRequest.xml")
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
    responseTimestampStr, calculationTimeMs = getResponseStatistics(stopEventResponse)
    liveJourneysDict["info"]["responseTimestamp"] = responseTimestampStr
    liveJourneysDict["info"]["calculationTimeMs"] += calculationTimeMs

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    
    liveJourneys = {}
    loggedJourneys = []
    
    toEarly = 0
    toLate = 0
    inAcqT = 0
    error = 0

    loggedJourneys = []

    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        serviceData      = stopEvent["StopEvent"]["Service"]
        trainLine        = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        trainJourney     = serviceData["JourneyRef"]
        trainOrigin      = serviceData["OriginText"]["Text"]
        trainDestination = serviceData["DestinationText"]["Text"]
        logging.info(f"{trainLine} ({trainJourney}) from {trainOrigin} to {trainDestination}")

        if not acquireTrainLineFilter(trainLine):
            continue
        
        allStops = []
        for callCat in ["PreviousCall", "ThisCall", "OnwardCall"]:
            stopOrStopsList = stopEvent["StopEvent"].get(callCat)
            if isinstance(stopOrStopsList, dict):
                allStops.append(stopOrStopsList)
            elif isinstance(stopOrStopsList, list):
                allStops.extend(stopOrStopsList)

        compRes = getLiveJourney(serviceData, allStops, currentTime, liveJourneysDict["journeys"])
        if compRes < 0:
            toEarly += 1
            continue
        if compRes > 0:
            toLate += 1
            logJourn = logJourney(serviceData, allStops)
            loggedJourneys.append(logJourn)
            continue
    return loggedJourneys

def getSqlConnection():
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
    yearInt = datetime.now().year
    connection = sqlite3.connect(base_dir/f'loggedJourney_{yearInt}.db')
    cursor = connection.cursor()
    cursor.execute(sqlJourneyTableInit)
    cursor.execute(sqlStopTableInit)
    connection.commit()
    cursor.close()
    return connection

def copy_www_to_webhost(local_path, remote_path = 'bwp@p0ng.de:/var/www/html/trias/'):
    for src_path in local_path.iterdir():
        scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_path]
        try:
            subprocess.run(scp_command, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during file copy: {e}")

def insertJourneysInDb(journeys):
    connection = getSqlConnection()
    cursor = connection.cursor()
    journey_keys = [
        "operatingDay", "journeyRef", "trainLineName", 
        "trainOrigin", "trainDestination", "trainIncidentMessage", 
        "isCancelled", "isUnplanned", "isDeviated",
    ]
    for journey in journeys:
        journey_data = tuple(journey[key] for key in journey_keys)
        insert_journey_data = f'''
            INSERT OR REPLACE INTO journeys ({', '.join(journey_keys)})
            VALUES ({', '.join(['?'] * len(journey_keys))});
        '''
        cursor.execute(insert_journey_data, journey_data)

        for stop in journey["stopsList"]:
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
    connection.commit()
    connection.close()

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

    allLiveJourneys = {"info": {"calculationTimeMs": 0, "responseTimestamp": None}, "journeys": dict()}
    allLoggedJourneys = []
    for stationTuple in checkAtStations:
        logging.info(f"station {stationTuple[0]}")
        allLoggedJourneys += getAllDelaysThroughStation(*stationTuple, allLiveJourneys, numResults=100)
    allLiveJourneys["info"]["attachedDataFormatRevision"] = "2026.02.26"
    allLiveJourneys["info"]["license"]                    = "DL-DE/BY-2-0"
    allLiveJourneys["info"]["rawDataSourceUrl"]           = "https://mobidata-bw.de/dataset/trias"
    allLiveJourneys = dict(sorted(allLiveJourneys.items()))
    return allLoggedJourneys, allLiveJourneys

try:
    #get trias data
    allLoggedJourneys, allLiveJourneys = getCurrentRunningTrains()

    #write into database
    insertJourneysInDb(allLoggedJourneys)

    #write live data into json
    with open(base_dir/"www/currentRunningTrains.json", "w") as outputfile:
        outputfile.write(json.dumps(allLiveJourneys, indent=4))

    #render livemap
    www_dir = base_dir/'www'
    try:
        from visualize_liveMap import render_liveMap
        render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"live_map_source.svg", www_dir/"live_map.svg")
    except Exception as e:
        logging.exception("Failed to update live map")

    #render statmap for this week
    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc
        analysisStartDay = current_utc - timedelta(days=0)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_today.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_today.svg")
    except Exception as e:
        logging.exception("Failed to update stat map for today")

    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc - timedelta(days=1)
        analysisStartDay = current_utc - timedelta(days=1)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_yesterday.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_yesterday.svg")
    except Exception as e:
        logging.exception("Failed to update stat map for yesterday")

    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc
        analysisStartDay = current_utc - timedelta(days=7)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_week.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_week.svg")
    except Exception as e:
        logging.exception("Failed to update stat map")

    #upload
    copy_www_to_webhost(www_dir)
except Exception:
    logging.error("Unhandled exception:\n%s", traceback.format_exc())
    raise
