
import zlib
import target_pb2
from google.protobuf.json_format import MessageToJson
import binascii

def decode_and_print_data(hex_string):
    """
    Decodes a zlib-compressed, protobuf-serialized hex string and prints it as JSON.
    It will try to parse as TargetProtoList first, then fall back to TargetProto.
    """
    try:
        # 1. Convert hex string to bytes
        cleaned_hex = "".join(hex_string.split())
        byte_data = bytes.fromhex(cleaned_hex)

        # 2. Decompress the byte data using zlib
        try:
            decompressed_data = zlib.decompress(byte_data)
        except zlib.error:
            # Fallback for raw deflate stream
            decompressed_data = zlib.decompress(byte_data, -15)

        if not decompressed_data:
            print("错误: 解压后数据为空。")
            return

        # 3. Attempt to deserialize the data
        parsed_message = None
        
        # Try parsing as TargetProtoList first
        try:
            proto_list = target_pb2.TargetProtoList()
            proto_list.ParseFromString(decompressed_data)
            # Check if the list actually contains items
            if proto_list.list:
                parsed_message = proto_list
                print("成功解析为 TargetProtoList。")
        except Exception as e_list:
            print(f"作为 TargetProtoList 解析失败: {e_list}")
            # If it fails, try parsing as a single TargetProto
            try:
                proto_single = target_pb2.TargetProto()
                proto_single.ParseFromString(decompressed_data)
                # Check if the object has any fields
                if proto_single.ByteSize() > 0:
                    parsed_message = proto_single
                    print("成功解析为单个 TargetProto。")
            except Exception as e_single:
                print(f"作为单个 TargetProto 也解析失败: {e_single}")

        if not parsed_message:
            print("错误: 无法将解压后的数据解析为任何已知的Protobuf消息类型。")
            print(f"解压后字节: {binascii.hexlify(decompressed_data).decode('ascii')}")
            return

        # 4. Convert the parsed protobuf message to JSON for readable output
        json_output = MessageToJson(parsed_message, indent=2, preserving_proto_field_name=True)

        print("\n------ 解码后的数据 (JSON格式) ------")
        print(json_output)

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == '__main__':
    input_hex = """
    78 DA E3 5A C8 C8 31 67 C3 AE 35 93 7E 9F 7C AA 24 14 C2 31 BD 9B 4D E0 3F 10 B0 4B 80 49 
05 46 8D 14 03 66 2B 21 4E BE 89 6F 6B EC AF 3A 39 08 FE 53 D9 1F F1 E9 78 AC 43 C4 57 E6 
04 B0 92 0C 30 59 C0 D7 C0 08 66 AC 60 84 1B 77 01 22 22 C1 A8 70 E2 F5 8E E3 0D C6 1A FC 
06 4C 16 5F 99 1D BE 32 07 69 21 2C 95 C2 62 B8 42 90 C6 EF 8B AD 7B 1B 8C 0D BE 32 47 88 
00 00 57 25 50 8B
    """
    decode_and_print_data(input_hex)
