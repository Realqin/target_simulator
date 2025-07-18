# -*- coding: utf-8 -*-

import target_pb2
from google.protobuf.json_format import MessageToDict


# 组装数据，只是为了看，不需要
def assemble_proto_from_data(data_dict):
    """
    将一个 Python 字典（源自 JSON）的数据组装到一个 TargetProto Protobuf 对象中。
    
    Args:
        data_dict (dict): 包含目标信息的完整 Python 字典。
        
    Returns:
        target_pb2.TargetProto: 填充了数据的 Protobuf 对象。
    """
    
    # 1. 创建 Protobuf 对象
    target = target_pb2.TargetProto()
    
    # 2. 映射顶层字段
    # 注意：Protobuf 的 id 是 uint64，需要将字符串 ID 转换为整数
    target.id = int(data_dict.get("id", 0))
    target.lastTm = data_dict.get("lastTm", 0)
    target.maxLen = int(data_dict.get("maxLen", 0))
    
    # 状态映射: 从字符串 "UPDATE" 转换到枚举值
    status_map = {
        "UPDATE": target_pb2.CurStatusProto.UPDATE,
        "NEW": target_pb2.CurStatusProto.NEW,
        "DELETED": target_pb2.CurStatusProto.DELETED,
        "UNDEFINED": target_pb2.CurStatusProto.UNDEFINED,
    }
    target.status = status_map.get(data_dict.get("status"), target_pb2.CurStatusProto.UNDEFINED)

    # 3. 填充 cTargProto (target.pos)
    pos = target.pos
    pos.displayId = data_dict.get("displayId", 0)
    pos.mmsi = data_dict.get("mmsi", 0)
    pos.id_r = data_dict.get("idR", 0)
    pos.state = data_dict.get("state", 0)
    pos.quality = data_dict.get("quality", 0)
    pos.period = data_dict.get("period", 0)
    pos.course = data_dict.get("course", 0.0)
    pos.speed = data_dict.get("speed", 0.0)
    pos.heading = data_dict.get("heading", 0.0)
    pos.len = int(data_dict.get("len", 0))
    pos.wid = data_dict.get("wid", 0)
    pos.shiptype = data_dict.get("shipType", 0)
    pos.s_class = data_dict.get("class", 0)
    pos.flags = data_dict.get("flags", 0)
    pos.m_mmsi = data_dict.get("mMmsi", 0)
    pos.vesselName = data_dict.get("vesselName", "")
    pos.vendorId = data_dict.get("vendorId", "")
    pos.callSign = data_dict.get("Call_Sign", "")
    #pos.imo = data_dict.get("imo", 0)
    pos.id = data_dict.get("id", 0)
    pos.fleetId = data_dict.get("fleetId", 0)
    pos.comment = data_dict.get("comment", "")
    pos.rec_course = data_dict.get("rec_course", 0)
    pos.rec_speed = data_dict.get("rec_speed", 0)
    pos.aidtype = data_dict.get("aidtype", 0)


    # 填充经纬度
    pos.geoPtn.latitude = data_dict.get("latitude", 0.0)
    pos.geoPtn.longitude = data_dict.get("longitude", 0.0)

    # 从 aisBaseInfo 中提取字段
    ais_info = data_dict.get("aisBaseInfo", {})

    pos.callSign = ais_info.get("Call_Sign", "")
    # proto 里的 imo 是 uint32，需要转换
    if ais_info.get("IMO"):
        pos.imo = int(ais_info.get("IMO"))

    # 同样需要将字符串ID转换为整数
    id_val = data_dict.get("id")
    if id_val:
        try:
            pos.id = int(id_val)
        except (ValueError, TypeError):
            pos.id = 0 # 如果转换失败，则设为默认值
    else:
        pos.id = 0
    
    pos.fleetId = data_dict.get("fleetId", 0)
    pos.comment = data_dict.get("comment", "")
    pos.rec_course = data_dict.get("rec_course", 0)
    pos.rec_speed = data_dict.get("rec_speed", 0)

    # 5. 填充 fusionTargets (vecFusionedTargetInfo)
    if "fusionTargets" in data_dict:
        for ft_item in data_dict["fusionTargets"]:
            ft_proto = target.vecFusionedTargetInfo.add()
            # 注意字段名的映射
            ft_proto.ullUniqueId = ft_item.get("targetId", 0)
            ft_proto.uiStationId = ft_item.get("stationId", 0)
            ft_proto.ullPosUpdateTime = ft_item.get("updateTime", 0)
            # stationType 需要从字符串映射到整数，这里假设 'A'->65, 'R'->82
            if ft_item.get("stationType") == "AIS":
                ft_proto.uiStationType = 65
            elif ft_item.get("stationType") == "RADAR":
                ft_proto.uiStationType = 82

    return target

def get_full_data_example():
    """返回一个包含所有字段的完整数据字典示例"""
    return {
      "aisBaseInfo": {
        "Call_Sign": "BSWD", "Destination": "HUANG HUA", "IMO": "9453561",
        "Length": 178, "MMSI": "413334000", "Ship Class": "A",
        "Ship Type": "Cargo, all ships of this type", "Vessel Name": "CHANG FENG 98",
        "Wide": 28, "draught": "5.8", "etaTime": "Mon Jul  7 12:30:00 2025",
        "receiveTime": "2025-07-14 19:33:15"
      },
      "course": 113.0, "displacement": 232783.9, "displayId": 96021,
      "duration": 633106454, "fixedState": 2, "flags": 0,
      "fusionTargets": [
        {"provider": "HLX", "stationId": 761, "stationType": "RADAR", "targetId": 2507141431163302161, "updateTime": 1752492811669},
        {"provider": "HLX", "stationId": 771, "stationType": "RADAR", "targetId": 2507141431163303933, "updateTime": 1752492811684},
        {"provider": "HLX", "stationId": 765, "stationType": "AIS", "targetId": 2507141436553317609, "updateTime": 1752492471233},
        {"provider": "HLX", "stationId": 771, "stationType": "AIS", "targetId": 2507141436553317609, "updateTime": 1752492652051}
      ],
      "globalAisType": 1, "heading": 262.0, "id": "2507060506333350007",
      "idR": 761, "inheritedId": "2507060506333350007", "lastDT": "2025-07-14 19:33:34",
      "lastTm": 1752492814669, "latitude": 38.41174312, "len": 178.0,
      "longitude": 118.2365294, "mMmsi": 413334000, "maxLen": 178.0,
      "mmsi": 413334000, "nationality": "China", "originalId": "2507141436553317609",
      "processTime": "2025-07-14 19:33:34", "province": "ShanDong", "quality": 100,
      "rangeMaxDistance": 15351.910837162555, "receiveDT": "2025-07-14 19:33:34",
      "receiveTime": 1752492814343, "registry": 1, "sClass": "RADAR_AIS_A",
      "shipType": 70, "shortLived": False,
      "sources": [
        {"ids": ["771", "761"], "provider": "HLX", "type": "RADAR"},
        {"ids": ["771", "765"], "provider": "HLX", "type": "AIS"}
      ],
      "speed": 0.1, "state": 1, "staticState": 2, "status": "UPDATE",
      "targetType": "TT_AR", "vesselName": "CHANG FENG 98", "wid": 28
    }

if __name__ == '__main__':
    # 这是一个使用示例
    
    # 1. 获取源数据
    source_data = get_full_data_example()
    
    # 2. 调用核心函数进行组装
    proto_message = assemble_proto_from_data(source_data)
    
    # 3. 打印组装后的 Protobuf 对象
    print("------ Assembled Protobuf Message ------")
    print(proto_message)
    
    # 4. (可选) 将 Protobuf 对象转换回字典以供验证
    dict_from_proto = MessageToDict(proto_message, preserving_proto_field_name=True)
    
    import json
    print("\n------ Dictionary converted back from Protobuf ------")
    print(json.dumps(dict_from_proto, indent=2))
