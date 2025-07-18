
import zlib
import target_pb2
from google.protobuf.json_format import MessageToJson
import binascii

def decode_and_print_data(hex_string):
    """
    Decodes a protobuf-serialized hex string and prints it as JSON.
    It will first attempt to decompress the data with zlib, and if that fails,
    it will treat the data as uncompressed. It then tries to parse the data
    as TargetProtoList, falling back to TargetProto.
    """
    try:
        # 1. Convert hex string to bytes
        cleaned_hex = "".join(hex_string.split())
        byte_data = bytes.fromhex(cleaned_hex)

        # 2. Attempt to decompress the data, but fall back to raw data if it fails
        data_to_parse = None
        try:
            # Try standard zlib decompression
            data_to_parse = zlib.decompress(byte_data)
            print("成功使用zlib解压。")
        except zlib.error:
            try:
                # Fallback for raw deflate stream (e.g., from Java)
                data_to_parse = zlib.decompress(byte_data, -15)
                print("成功使用 raw deflate 解压。")
            except zlib.error:
                # If both decompression methods fail, assume the data is not compressed
                print("zlib解压失败，将作为未压缩数据尝试直接解析。")
                data_to_parse = byte_data

        if not data_to_parse:
            print("错误: 解码或解压后数据为空。")
            return

        # 3. Attempt to deserialize the data
        parsed_message = None
        
        # Try parsing as TargetProtoList first
        try:
            proto_list = target_pb2.TargetProtoList()
            proto_list.ParseFromString(data_to_parse)
            # Check if the list actually contains items
            if proto_list.list:
                parsed_message = proto_list
                print("成功解析为 TargetProtoList。")
        except Exception as e_list:
            print(f"作为 TargetProtoList 解析失败: {e_list}")
            # If it fails, try parsing as a single TargetProto
            try:
                proto_single = target_pb2.TargetProto()
                proto_single.ParseFromString(data_to_parse)
                # Check if the object has any fields
                if proto_single.ByteSize() > 0:
                    parsed_message = proto_single
                    print("成功解析为单个 TargetProto。")
            except Exception as e_single:
                print(f"作为单个 TargetProto 也解析失败: {e_single}")

        if not parsed_message:
            print("错误: 无法将数据解析为任何已知的Protobuf消息类型。")
            print(f"待解析数据的Hex格式: {binascii.hexlify(data_to_parse).decode('ascii')}")
            return

        # 4. Convert the parsed protobuf message to JSON for readable output
        json_output = MessageToJson(parsed_message, indent=2, preserving_proto_field_name=True)

        print("\n------ 解码后的数据 (JSON格式) ------")
        print(json_output)

    except binascii.Error as e:
        print(f"Hex字符串转换错误: {e}. 请检查输入是否为有效的十六进制字符。")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == '__main__':
    input_hex = """
0A CD 01 08 E6 BB B0 DF DA A6 CC E5 22 12 69 08 B1 9A 01 10 8A DE D6 C4 01 18 FF FF FF FF 
07 20 01 28 64 30 FF FF FF FF 07 3A 12 09 4B BC 5F F2 2C B6 36 40 11 16 B5 DB 2E 34 A2 5C 
40 58 1E 60 06 68 1E 70 02 78 80 02 80 01 8A DE D6 C4 01 8A 01 14 59 55 45 48 55 49 44 4F 
4E 47 59 55 58 49 55 39 30 30 38 36 A8 01 E6 BB B0 DF DA A6 CC E5 22 D0 01 FF FF FF FF 07 
18 01 20 8D BA D4 C8 81 33 28 C1 02 30 02 38 80 08 40 FF FF FF FF 07 4A 0F 0A 03 48 4C 58 
12 03 41 49 53 1A 03 33 32 37 52 2C 08 E6 BB B0 DF DA A6 CC E5 22 10 C7 02 1A 12 09 4B BC 
5F F2 2C B6 36 40 11 16 B5 DB 2E 34 A2 5C 40 20 41 28 EE F4 C5 C8 81 33 30 1E 58 03 
    """
    decode_and_print_data(input_hex)
