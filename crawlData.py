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

def tripRef_from_departingStop(originRef, departureTime: datetime, numResults=5):
    stopEventRequestXml = Path("./StopEventRequest.xml")
    stopEventRequestXml = open(stopEventRequestXml, "rb").read()
    stopEventRequest    = xmltodict.parse(stopEventRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = stopEventRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["StopEventRequest"]["Location"]["LocationRef"]["StopPointRef"] = originRef
    datetimestring = departureTime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    serviceRequest["RequestPayload"]["StopEventRequest"]["Location"]["LocationRef"]["DepArrTime"] = datetimestring
    serviceRequest["RequestPayload"]["StopEventRequest"]["Params"]["NumberOfResults"] = numResults

    stopEventResponse = sendRequest(stopEventRequest)
    printResponseStatistics(stopEventResponse)

    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    
    print(serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResponseContext"]["Situations"]["PtSituation"].keys())
    
    journeyRefs = set()
    journeyApproxTimes = dict()
    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        print(stopEvent["StopEvent"]["Service"]["Attribute"])
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
    print(tripInfoRequest)
    tripInfoResponse = sendRequest(tripInfoRequest)
    printResponseStatistics(tripInfoResponse)

    print(len(str(tripInfoResponse)))
    #exit(0) 
    
    
    
    serviceDelivery = tripInfoResponse["Trias"]["ServiceDelivery"]
    print("servdel")
    print(serviceDelivery)
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




#hauptbahnhofRef = "de:08111:6118"#stopPointRef_from_LocationName("Stuttgart (tief)")

# get all journeys that pass through stadtmitte

stadtmitteRef    = "de:08111:6052"
todayMidnight    = datetime.combine(datetime.now().date(), datetime.min.time())
journeysAndDates, journeyRoughTime = tripRef_from_departingStop(stadtmitteRef, todayMidnight, numResults=5)
"""
print(journeyRoughTime)
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

#getTripInformation(f"ddb:92T03::R:j26:1384", datetime.now())
#getTripInformation(f"ddb:92T01::H:j26:646", datetime.now(), test="false")
"""
for i in range(10):

"""
