from pydantic_xml import BaseXmlModel, element, attr
from pydantic import field_validator
from datetime import datetime, timezone
from typing import Union, Optional

#todo, make all class search_mode="unordered"

namespaceMap = {
    "": "http://www.vdv.de/trias",
    "siri": "http://www.siri.org.uk/siri",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
}

class LocationName(BaseXmlModel, tag='LocationName', nsmap=namespaceMap):
    text: str = element(tag='Text')

class LocationRef(BaseXmlModel, tag='LocationRef', nsmap=namespaceMap):
    stop_point_ref: str = element(tag='StopPointRef')
    location_name: LocationName = element()

class Origin(BaseXmlModel, tag='Origin', nsmap=namespaceMap):
    dep_arr_time: Optional[datetime] = element(tag="DepArrTime")
    location_ref: LocationRef = element()
    @field_validator("dep_arr_time", mode="before")
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(microsecond=0)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).replace(microsecond=0)
        return None

class Destination(BaseXmlModel, tag='Destination', nsmap=namespaceMap):
    location_ref: LocationRef = element()

class TripRequestParams(BaseXmlModel, tag='Params', nsmap=namespaceMap):
    number_of_results: int = element(tag='NumberOfResults')
    include_track_sections: bool = element(tag='IncludeTrackSections')
    include_intermediate_stops: bool = element(tag='IncludeIntermediateStops')
    include_leg_projection: bool = element(tag='IncludeLegProjection')
    include_fares: bool = element(tag='IncludeFares')

class TripRequest(BaseXmlModel, tag='TripRequest', nsmap=namespaceMap):
    origin: Origin = element(tag='Origin')
    destination: Destination = element(tag='Destination')
    params: TripRequestParams = element(tag='Params')


class Restrictions(BaseXmlModel, tag='Restrictions', nsmap=namespaceMap):
    type: str = element()
    language: str = element()
    numberOfResults: int = element()
    includePtModes: bool = element()

class TripInfoRequestParams(BaseXmlModel, tag='Params', nsmap=namespaceMap):
    include_intermediate_stops: bool = element(tag="IncludeIntermediateStops")
    include_track_sections: bool = element(tag="IncludeTrackSections")
    include_position: bool = element(tag="IncludePosition")

from pydantic import field_serializer

class TripInfoRequest(BaseXmlModel, tag='TripInfoRequest', nsmap=namespaceMap):
    journey_ref: str                = element(tag="JourneyRef")
    operating_day_ref: datetime     = element(tag="OperatingDayRef")
    params: TripInfoRequestParams   = element()
    @field_validator('operating_day_ref', mode='before')
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.strptime(value, "%Y-%m-%dT")
            return dt.replace(tzinfo=timezone.utc)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return None
        
    @field_serializer("operating_day_ref")
    def serialize_date_only(self, value: datetime):
        return value.date().isoformat() + "T"
    
class RequestPayload(BaseXmlModel, tag='RequestPayload', nsmap=namespaceMap):
    content: Union[TripInfoRequest, TripRequest] = element()

class ServiceRequest(BaseXmlModel, tag='ServiceRequest', search_mode='unordered', nsmap=namespaceMap):
    request_timestamp: datetime     = element(tag="RequestTimestamp",  ns="siri")
    requestor_ref: str              = element(tag='RequestorRef',      ns="siri")
    message_identifier: str         = element(tag="MessageIdentifier", ns="siri")
    request_payload: RequestPayload = element()
    @field_validator("request_timestamp", mode="before")
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(microsecond=0)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).replace(microsecond=0)
        return None  
        
class Trias(BaseXmlModel, tag='Trias', nsmap=namespaceMap):
    version: str = attr()
    service_request: ServiceRequest = element()

with open("TripInformationRequest.txt", "rb") as f:
    xml_content = f.read()

trias_obj = Trias.from_xml(xml_content)

from xml.dom import minidom
from pathlib import Path
rough_xml = trias_obj.to_xml()
parsed = minidom.parseString(rough_xml)
pretty_xml = parsed.toprettyxml(indent="    ", encoding="utf-8")
output_file = Path("TripInformationRequest_out.txt")
output_file.write_bytes(pretty_xml)
