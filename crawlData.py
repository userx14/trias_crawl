from triasLib import Trias
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
url          = "https://efa-bw.de/trias"
requestorKey = open("requestor.key").read()
def stopPointReference_from_name(locationName):
    findStationRequestXml = Path("LocationInformationRequest_findTrainStations.xml")
    findStationRequestXml = open(findStationRequestXml, "rb").read()
    
    findStationRequest = Trias.from_xml(findStationRequestXml)
    findStationRequest.service_request.request_timestamp = datetime.now()
    findStationRequest.service_request.requestor_ref     = requestorKey
    locationInfoRequest = findStationRequest.service_request.request_payload.location_information_request
    locationInfoRequest.initial_input.location_name      = locationName
    locationInfoRequest.location_param_structure.number_of_results = 5
    
    result = (findStationRequest.query(url))
    #print(response.text)
    root = ET.XML(result)
    ET.indent(root)
    pretty = ET.tostring(root, encoding='unicode')
    print(pretty)
    with open("out.txt", "w", encoding="utf-8") as outfile:
        outfile.write(pretty)
    
stopPointReference_from_name("Stuttgart (tief)")

#analysis part

"""
def stopPointRef_from_LocationName(LocationName):
    xmlTx    = location_information_request(LocationName, NumberOfResults=5)
    response = requests.post(url, data=xmlTx.encode('utf-8'), headers=requestHeader)
    root     = ET.XML(response.content)
    delivery_payload = root.find(".//trias:DeliveryPayload", responseNamespace)
    LocationInformationResponse = delivery_payload.find("trias:LocationInformationResponse", responseNamespace)
    ET.indent(delivery_payload)
   #print(ET.tostring(delivery_payload, encoding='unicode'))
    validStops = []
    for LocationResult in LocationInformationResponse:
        #filter for suburban railway stops
        ModeList = LocationResult.findall("trias:Mode", responseNamespace)
        for Mode in ModeList:
            railSubmode = Mode.find("trias:RailSubmode", responseNamespace)
            if(railSubmode is not None and railSubmode.text == "suburbanRailway"):
                break
        else:
            continue #skip stop if it does not match filter
        #extract information stopname and stopref
        StopPoint = LocationResult.find(".//trias:StopPoint", responseNamespace)
        ref       = StopPoint.find("trias:StopPointRef", responseNamespace).text
        name      = StopPoint.find("trias:StopPointName", responseNamespace)
        name      = name.find("trias:Text", responseNamespace).text
        validStops.append((name, ref))
    print(validStops)
    return validStops[0][1]


def tripsStammstrecke(time):
    stgHbfTiefRef    = stopPointRef_from_LocationName("Stuttgart (tief)")
    stgStadtmitteRef = stopPointRef_from_LocationName("Stuttgart Stadtmitte")
    xmlTx            = trip_request(stgHbfTiefRef, time, stgStadtmitteRef)
    response         = requests.post(url, data=xmlTx, headers=requestHeader)
    root             = ET.XML(response.content)
    delivery_payload = root.find(".//trias:DeliveryPayload", responseNamespace)
    ET.indent(root)
    print(ET.tostring(root, encoding='unicode'))

tripsStammstrecke(datetime.now())


#xml = trip_information_request("ddb:90T10:B:H", datetime.now())
#xml = trip_request("test", datetime.now(), "test2")
xml = location_information_request("Stuttgart hbf (tief)")
print(xml)

#print(response.status_code, response.text, len(xml))

print(response.text)
root = ET.XML(response.text)
ET.indent(delivery_payload)
pretty = ET.tostring(delivery_payload, encoding='unicode')
print(pretty)
with open("out.txt", "w", encoding="utf-8") as outfile:
    outfile.write(pretty)


trias.key("")
trias.url("")


req = trias.StopEventRequest()
req["StopEventRequest","Location"]
req[0,"test"]
req.StopEventRequest.Location.LocationRef.StopPointRef   = "de:08111:6118"
req.StopEventRequest.Location.Params.IncludeRealtimeData = True
response = trias.send(req)
response.trip
"""