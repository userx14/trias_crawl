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
