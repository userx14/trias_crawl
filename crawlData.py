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
    currentTime         = datetime.now()
    departureAtStopTime = triasStrFromDatetime(currentTime - timedelta(hours=2))
    numResults          = 10
    operatorFilter      = {"Exclude": "false", "OperatorRef": "ddb:00"}

    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)


    serviceRequest   = stopEventRequest["Trias"]["ServiceRequest"]
    stopEventRequestPayload = serviceRequest["RequestPayload"]["StopEventRequest"]
    stopEventRequestPayload["Location"]["LocationRef"]["StopPointRef"] = passingThroughRef
    stopEventRequestPayload["Location"]["LocationRef"]["DepArrTime"]   = departureAtStopTime
    stopEventRequestPayload["Params"]["OperatorFilter"]                = operatorFilter
    stopEventRequestPayload["Params"]["IncludePreviousCalls"]          = "true"
    stopEventRequestPayload["Params"]["IncludeOnwardCalls"]            = "true"
    stopEventRequestPayload["Params"]["IncludeRealtimeData"]           = "true"
    stopEventRequestPayload["Params"]["NumberOfResults"]               = numResults

    stopEventResponse = sendRequest(stopEventRequest)
    printResponseStatistics(stopEventResponse)

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        previousStops = stopEvent["StopEvent"].get("PreviousCall") or []
        thisStop      = stopEvent["StopEvent"].get("ThisCall")
        nextStops     = stopEvent["StopEvent"].get("OnwardCall") or []
        serviceData   = stopEvent["StopEvent"].get("Service")
        allStops      = previousStops + [thisStop] + nextStops


        #check if last first stop in journey before the current time
        firstStop = allStops[0]
        departureDict = call.get("ServiceDeparture")
        timetableDeparture = datetimeFromTriasStr(departureDict["TimetabledTime"])
        if currentTime < timetableDeparture:
            logging.info("train has not started yet")
            continue

        #check which stop whas the last passed one
        delay = None
        for stop in allStops[::-1]:
            departureDict = call.get("ServiceDeparture")
            if departureDict is not None:
                timetableDeparture = datetimeFromTriasStr(departureDict["TimetabledTime"])
                estimateDeparture  = datetimeFromTriasStr(arrivalDict.get("EstimateTime"))

            arrivalDict = call.get("ServiceArrival")
            if arrivalDict is not None:
                timetableArrival = datetimeFromTriasStr(arrivalDict["TimetabledTime"])
                estimateArrival  = datetimeFromTriasStr(arrivalDict.get("EstimatedTime"))

            #check if stop has been reached
            if (estimateArrival is not None) and (estimateArrival < currentTime):
                delay = estimatedArrival - timetableArrival
                break
            if (estimateDeparture is None) and (estimateArrical < currentTime):
                delay = estimateDeparture - timetableDeparture
                break
        #check if train has already arrived at last stop
        if stop == allStops[-1]:
            logging.info("train has already arrived at final stop")
            continue
        print(delay)

        if serviceData.get("Cancelled") == "true":
            raise ValueError("Debugging cancelled train :)")
        if serviceData.get("Unplanned") == "true":
            raise ValueError("Debugging unplanned train :)")
        if serviceData.get("Deviation") == "true":
            raise ValueError("Debugging deviated train :)")

        if serviceData:
            trainJourney  = serviceData["JourneyRef"]
            trainLineName = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
            trainOrigin   = serviceData["OriginText"]["Text"]
            trainDestination = serviceData["DestinationText"]["Text"]
            print(f"{trainLineName} ({trainJourney}) from {trainOrigin} to {trainDestination}")

            for att in serviceData["Attribute"]:
                if "Incident" in att["Code"]:
                    incidentText = att["Text"]["Text"]
                    print(f"warning incident report: {incidentText}")


        for stop in allStops:
            stopPointRef  = stop["CallAtStop"]["StopPointRef"]
            stopPointName = stop["CallAtStop"]["StopPointName"]["Text"]
            arrivalDelay = delay_from_serviceCall(stop["CallAtStop"].get("ServiceArrival"))
            departureDelay = delay_from_serviceCall(stop["CallAtStop"].get("ServiceDeparture"))
            print(f"delayAr: {arrivalDelay}, delayDe: {departureDelay} @{stopPointName}")
        print("====\n\n")
    return


    journeyRefs = set()
    journeyApproxTimes = dict()
    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        print(stopEvent.keys())
        print(stopEvent["StopEvent"]["Service"])
        if "Attribute" in stopEvent["StopEvent"]["Service"].keys():
            print(stopEvent["StopEvent"]["Service"]["Attribute"])
        print(stopEvent["StopEvent"]["Service"]["JourneyRef"])
        timetabledTime = stopEvent["StopEvent"]["ThisCall"]["CallAtStop"]["ServiceDeparture"]["TimetabledTime"]
        timetabledTime = datetime.strptime(timetabledTime, "%Y-%m-%dT%H:%M:%SZ")
        timetabledTime = timetabledTime.replace(tzinfo=timezone.utc)
        timetabledTime = timetabledTime.astimezone()
        operatingDayRef = stopEvent["StopEvent"]["Service"]["OperatingDayRef"]
        journeyRef = stopEvent["StopEvent"]["Service"]["JourneyRef"]
        journeyRefs.add((journeyRef, operatingDayRef))
        journeyApproxTimes[journeyRef] = timetabledTime
    return journeyRefs, journeyApproxTimes






#print(stopPointRef_from_LocationName("Zuffenhausen"))
#exit(0)
zuffenhausen= "de:08111:6465"

schwabstraßeRef= "de:08111:6052"
hauptbahnhofRef = "de:08111:6118"

# get all journeys that pass through stadtmitte

stadtmitteRef    = "de:08111:6052"
todayMidnight    = datetime.combine(datetime.now().date(), datetime.min.time())

journeysAndDates, journeyRoughTime = getAllDelaysThroughStation(hauptbahnhofRef, numResults=10)
print(journeysAndDates)

print(journeyRoughTime)
"""

#count statistics
uniqueDates = set([it[1] for it in journeysAndDates])
resultCount = []
for date in uniqueDates:
    counter = 0
    for journeyAndDate in journeysAndDates:
        if journeyAndDate[1] == date:
            counter += 1
    resultCount.append((date, counter))
"""

#getTripInformation(f"ddb:92T04::H:j26:152", datetime.now())
