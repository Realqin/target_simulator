
import zlib
import target_pb2
from google.protobuf.json_format import MessageToJson
import binascii

# 解码pb里发送的数据

def decode_data(hex_string):
    """
    Decodes a protobuf-serialized hex string.
    If successful, returns (True, formatted_json_string).
    If fails, returns (False, error_message_with_logs).
    """
    output_log = []
    try:
        cleaned_hex = "".join(hex_string.split())
        if not cleaned_hex:
            return False, "输入为空。"
        byte_data = bytes.fromhex(cleaned_hex)

        data_to_parse = None
        try:
            data_to_parse = zlib.decompress(byte_data)
            output_log.append("成功使用zlib解压。")
        except zlib.error:
            try:
                data_to_parse = zlib.decompress(byte_data, -15)
                output_log.append("成功使用 raw deflate 解压。")
            except zlib.error:
                output_log.append("zlib解压失败，将作为未压缩数据尝试直接解析。")
                data_to_parse = byte_data

        if not data_to_parse:
            return False, "\n".join(output_log) + "\n错误: 解码或解压后数据为空。"

        parsed_message = None
        try:
            proto_list = target_pb2.TargetProtoList()
            proto_list.ParseFromString(data_to_parse)
            if proto_list.list:
                parsed_message = proto_list
        except Exception:
            try:
                proto_single = target_pb2.TargetProto()
                proto_single.ParseFromString(data_to_parse)
                if proto_single.ByteSize() > 0:
                    parsed_message = proto_single
            except Exception:
                pass # Both failed, handled below

        if not parsed_message:
            output_log.append("错误: 无法将数据解析为任何已知的Protobuf消息类型。")
            hex_dump = binascii.hexlify(data_to_parse).decode('ascii')
            output_log.append(f"待解析数据的Hex格式: {hex_dump}")
            return False, "\n".join(output_log)

        # Success case: Convert to JSON and return only the JSON
        json_output = MessageToJson(parsed_message, indent=2, preserving_proto_field_name=True)
        return True, json_output

    except binascii.Error as e:
        return False, f"Hex字符串转换错误: {e}.\n请检查输入是否为有效的十六进制字符。"
    except Exception as e:
        return False, f"解析失败！"

if __name__ == '__main__':
    input_hex = """
0A A8 02 08 ED 80 9A FA E3 8A B4 E7 22 12 5F 08 F2 9D 04 10 B8 F7 89 61 18 FF FF FF FF 07 
20 01 28 64 30 FF FF FF FF 07 3A 12 09 37 4D E0 DC D5 DC 35 40 11 0B 1A FD A7 96 78 5C 40 
45 CD 0C 83 43 4D 9A 99 D9 40 55 01 00 7E 43 58 27 60 08 68 1E 70 02 78 80 02 80 01 B8 F7 
89 61 A8 01 ED 80 9A FA E3 8A B4 E7 22 D0 01 FF FF FF FF 07 18 01 20 F3 F8 CF B5 8C 33 28 
C1 02 30 02 38 27 40 FF FF FF FF 07 4A 19 0A 03 48 4C 58 12 03 41 49 53 1A 03 33 33 34 1A 
03 33 33 37 1A 03 33 35 34 52 2C 08 ED 80 9A FA E3 8A B4 E7 22 10 CE 02 1A 12 09 2F 9D 6B 
85 D6 DC 35 40 11 89 D8 2D EF 97 78 5C 40 20 41 28 AD 84 CD B5 8C 33 30 27 52 2C 08 ED 80 
9A FA E3 8A B4 E7 22 10 D1 02 1A 12 09 2F 9D 6B 85 D6 DC 35 40 11 89 D8 2D EF 97 78 5C 40 
20 41 28 E3 E7 CE B5 8C 33 30 27 52 2C 08 ED 80 9A FA E3 8A B4 E7 22 10 E2 02 1A 12 09 2F 
9D 6B 85 D6 DC 35 40 11 89 D8 2D EF 97 78 5C 40 20 41 28 A7 DC AB B5 8C 33 30 27 58 03 
    """
    success, result = decode_data(input_hex)
    print(f"Success: {success}")
    print(result)
