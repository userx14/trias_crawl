from datetime import datetime, timezone
import xmltodict
import requests
from pathlib import Path

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

def printResponseStatistics(responseDict):
    serviceDelivery   = responseDict["Trias"]["ServiceDelivery"]
    responseTimestamp = datetime.strptime(serviceDelivery["siri:ResponseTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    responseTimestamp = responseTimestamp.replace(tzinfo=timezone.utc)
    responseTimestamp = responseTimestamp.astimezone() #convert to local timezone
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
    timetableTime = serviceCallDict["TimetabledTime"]
    timetableTime = datetime.strptime(timetableTime, "%Y-%m-%dT%H:%M:%SZ")
    timetableTime = timetableTime.replace(tzinfo=timezone.utc)
    timetableTime = timetableTime.astimezone()

    estimatedTime = serviceCallDict["EstimatedTime"]
    estimatedTime = datetime.strptime(estimatedTime, "%Y-%m-%dT%H:%M:%SZ")
    estimatedTime = estimatedTime.replace(tzinfo=timezone.utc)
    estimatedTime = estimatedTime.astimezone()
    return (estimatedTime - timetableTime).total_seconds() / 60

def tripRef_from_departingStop(originRef, departureTime: datetime, numResults=5, opRef=""):
    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = stopEventRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["StopEventRequest"]["Location"]["LocationRef"]["StopPointRef"] = originRef
    datetimestring = departureTime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    serviceRequest["RequestPayload"]["StopEventRequest"]["Location"]["LocationRef"]["DepArrTime"] = datetimestring
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["OperatorFilter"] = {"Exclude": "false", "OperatorRef": "ddb:00"}
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["IncludePreviousCalls"] = "true"
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["IncludeOnwardCalls"] = "true"
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["IncludeRealtimeData"] = "true"
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["NumberOfResults"] = numResults

    stopEventResponse = sendRequest(stopEventRequest)
    printResponseStatistics(stopEventResponse)

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    
    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        previousStops = stopEvent["StopEvent"].get("PreviousCall") or []
        thisStop =      stopEvent["StopEvent"].get("ThisCall")
        nextStops =     stopEvent["StopEvent"].get("OnwardCall") or []
        serviceData =   stopEvent["StopEvent"].get("Service")

        if serviceData.get("Cancelled") == "true":
            raise ValueError("Debugging cancelled train :)")
        if serviceData.get("Unplanned") == "true":
            raise ValueError("Debugging unplanned train :)")
        if serviceData.get("Deviation") == "true":
            raise ValueError("Debugging deviated train :)")



        if serviceData:
            trainJourney =  serviceData["JourneyRef"]
            trainLineName = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
            trainOrigin =   serviceData["OriginText"]["Text"]
            trainDestination = serviceData["DestinationText"]["Text"]
            print(f"{trainLineName} ({trainJourney}) from {trainOrigin} to {trainDestination}")

            for att in serviceData["Attribute"]:
                if "Incident" in att["Code"]:
                    incidentText = att["Text"]["Text"]
                    print(f"warning incident report: {incidentText}")

        allStops = previousStops + [thisStop] + nextStops
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

def tripRef_from_locations(originRef, destinationRef, arrivalTime: datetime, numResults = 5):
    tripRequestXml = Path("./TripRequest.xml")
    tripRequestXml = open(tripRequestXml, "rb").read()
    tripRequest = xmltodict.parse(tripRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = tripRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["TripRequest"]["Origin"]["LocationRef"]["StopPointRef"] = originRef
    datetimestring = arrivalTime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    serviceRequest["RequestPayload"]["TripRequest"]["Origin"]["DepArrTime"] = datetimestring
    serviceRequest["RequestPayload"]["TripRequest"]["Destination"]["LocationRef"]["StopPointRef"] = destinationRef
    serviceRequest["RequestPayload"]["TripRequest"]["Params"]["NumberOfResults"] = numResults

    tripResponse = sendRequest(tripRequest)
    printResponseStatistics(tripResponse)

    serviceDelivery = tripResponse["Trias"]["ServiceDelivery"]
    for tripResult in serviceDelivery["DeliveryPayload"]["TripResponse"]["TripResult"]:
        operatingDayRef = tripResult["Trip"]["TripLeg"]["TimedLeg"]["Service"]["OperatingDayRef"]
        operatingDay = datetime.strptime(operatingDayRef, "%Y-%m-%dT")
        print(operatingDay)
        journeyRef = tripResult["Trip"]["TripLeg"]["TimedLeg"]["Service"]["JourneyRef"]
        print(f"operatingDayRef: {journeyRef}: {operatingDayRef}")

def getTripInformation(tripRef, operatingDayRef):
    tripInfoRequestXml = Path("./TripInformationRequest.xml")
    tripInfoRequestXml = open(tripInfoRequestXml, "rb").read()
    tripInfoRequest = xmltodict.parse(tripInfoRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = tripInfoRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["TripInfoRequest"]["JourneyRef"] = tripRef
    datetimestring = operatingDayRef.astimezone(timezone.utc).strftime("%Y-%m-%dT")
    serviceRequest["RequestPayload"]["TripInfoRequest"]["OperatingDayRef"] = datetimestring
    #serviceRequest["RequestPayload"]["TripInfoRequest"]["Params"]["IncludePosition"] = "true"
    tripInfoResponse = sendRequest(tripInfoRequest)
    printResponseStatistics(tripInfoResponse)

    serviceDelivery = tripInfoResponse["Trias"]["ServiceDelivery"]
    if("ErrorMessage" in serviceDelivery["DeliveryPayload"]["TripInfoResponse"].keys()):
        print(serviceDelivery["DeliveryPayload"]["TripInfoResponse"]["ErrorMessage"]["Code"])
        return
    tripInfoResult = serviceDelivery["DeliveryPayload"]["TripInfoResponse"]["TripInfoResult"]
    sbahnLineName = tripInfoResult["Service"]["ServiceSection"]["PublishedLineName"]["Text"]
    sbahnDestinationName = tripInfoResult["Service"]["DestinationText"]["Text"]

    if "PreviousCall" in tripInfoResult.keys():
        plannedFirstStopDepart = tripInfoResult["PreviousCall"][0]["ServiceDeparture"]["TimetabledTime"]
    else:
        plannedFirstStopDepart = tripInfoResult["OnwardCall"][0]["ServiceDeparture"]["TimetabledTime"]

    plannedLastStopArrival = tripInfoResult["OnwardCall"][-1]["ServiceArrival"]["TimetabledTime"]

    print(f"{sbahnLineName} to {sbahnDestinationName}")
    print(f"from {plannedFirstStopDepart} till {plannedLastStopArrival}")
    if "PreviousCall" in tripInfoResult.keys():
        for previousCall in tripInfoResult["PreviousCall"]:
            stopName      = previousCall["StopPointName"]["Text"]

            if "ServiceDeparture" in previousCall.keys():
                departureOrArrival = previousCall["ServiceDeparture"]
            elif "ServiceArrival" in previousCall.keys():
                departureOrArrival = previousCall["ServiceArrival"]
            else:
                raise ValueError("No departure or arrival found")

            timetableTime = departureOrArrival["TimetabledTime"]
            timetableTime = datetime.strptime(timetableTime, "%Y-%m-%dT%H:%M:%SZ")
            timetableTime = timetableTime.replace(tzinfo=timezone.utc)
            timetableTime = timetableTime.astimezone()

            estimatedTime = departureOrArrival["EstimatedTime"]
            estimatedTime = datetime.strptime(estimatedTime, "%Y-%m-%dT%H:%M:%SZ")
            estimatedTime = estimatedTime.replace(tzinfo=timezone.utc)
            estimatedTime = estimatedTime.astimezone()
            delay = (estimatedTime - timetableTime).total_seconds() / 60
            print(f"{stopName}: {delay}")
    print("<---  current ")
    if "OnwardCall" in tripInfoResult.keys():
        for onwardCall in tripInfoResult["OnwardCall"]:
            stopName      = onwardCall["StopPointName"]["Text"]

            if "ServiceDeparture" in onwardCall.keys():
                departureOrArrival = onwardCall["ServiceDeparture"]
            elif "ServiceArrival" in onwardCall.keys():
                departureOrArrival = onwardCall["ServiceArrival"]
            else:
                raise ValueError("No departure or arrival found")

            timetableTime = departureOrArrival["TimetabledTime"]
            timetableTime = datetime.strptime(timetableTime, "%Y-%m-%dT%H:%M:%SZ")
            timetableTime = timetableTime.replace(tzinfo=timezone.utc)
            timetableTime = timetableTime.astimezone()

            estimatedTime = departureOrArrival["EstimatedTime"]
            estimatedTime = datetime.strptime(estimatedTime, "%Y-%m-%dT%H:%M:%SZ")
            estimatedTime = estimatedTime.replace(tzinfo=timezone.utc)
            estimatedTime = estimatedTime.astimezone()
            delay = (estimatedTime - timetableTime).total_seconds() / 60

            print(f"{stopName}: {delay}")

    #print(tripInfoResult["Service"])
    #print(serviceDelivery)




#print(stopPointRef_from_LocationName("Zuffenhausen"))
#exit(0)
zuffenhausen= "de:08111:6465"

schwabstraßeRef= "de:08111:6052"
hauptbahnhofRef = "de:08111:6118"

# get all journeys that pass through stadtmitte

stadtmitteRef    = "de:08111:6052"
todayMidnight    = datetime.combine(datetime.now().date(), datetime.min.time())

journeysAndDates, journeyRoughTime = tripRef_from_departingStop(hauptbahnhofRef, datetime.now(), numResults=10)
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
