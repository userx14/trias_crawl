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

def tripRef_from_locations(originRef, destinationRef, arrivalTime: datetime):
    tripRequestXml = Path("./TripRequest.xml")
    tripRequestXml = open(tripRequestXml, "rb").read()
    tripRequest = xmltodict.parse(tripRequestXml, process_namespaces=True, namespaces=namespaces)

    serviceRequest = tripRequest["Trias"]["ServiceRequest"]
    serviceRequest["RequestPayload"]["TripRequest"]["Origin"]["LocationRef"]["StopPointRef"] = originRef
    datetimestring = arrivalTime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    serviceRequest["RequestPayload"]["TripRequest"]["Origin"]["DepArrTime"] = datetimestring
    serviceRequest["RequestPayload"]["TripRequest"]["Destination"]["LocationRef"]["StopPointRef"] = destinationRef
    serviceRequest["RequestPayload"]["TripRequest"]["Params"]["NumberOfResults"] = 50

    tripResponse = sendRequest(tripRequest)
    printResponseStatistics(tripResponse)

    serviceDelivery = tripResponse["Trias"]["ServiceDelivery"]
    for tripResult in serviceDelivery["DeliveryPayload"]["TripResponse"]["TripResult"]:
        operatingDayRef = tripResult["Trip"]["TripLeg"]["TimedLeg"]["Service"]["OperatingDayRef"]
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
    serviceRequest["RequestPayload"]["TripInfoRequest"]["Params"]["IncludePosition"] = "true"

    tripInfoResponse = sendRequest(tripInfoRequest)
    printResponseStatistics(tripInfoResponse)


    serviceDelivery = tripInfoResponse["Trias"]["ServiceDelivery"]
    if("ErrorMessage" in serviceDelivery["DeliveryPayload"]["TripInfoResponse"].keys()):
        print(serviceDelivery["DeliveryPayload"]["TripInfoResponse"]["ErrorMessage"]["Code"])
        return
    tripInfoResult = serviceDelivery["DeliveryPayload"]["TripInfoResponse"]["TripInfoResult"]
    sbahnLineName = tripInfoResult["Service"]["ServiceSection"]["PublishedLineName"]["Text"]
    sbahnDestinationName = tripInfoResult["Service"]["DestinationText"]["Text"]
    
    print(f"{sbahnLineName} to {sbahnDestinationName}")
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

    print(tripInfoResult["Service"])
    #print(serviceDelivery)


hauptbahnhofRef = "de:08111:6118"#stopPointRef_from_LocationName("Stuttgart (tief)")
stadtmitteRef   = "de:08111:6052"#stopPointRef_from_LocationName("Stuttgart Schwabstraße")

#tripRef_from_locations(hauptbahnhofRef, stadtmitteRef, datetime.now())
getTripInformation(f"ddb:92T03::H:j26:612", datetime.now())
"""
for i in range(10):
    
"""