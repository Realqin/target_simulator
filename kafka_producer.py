import json
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import logging
import time

# 配置一个基础的日志记录器，以防没有回调时，日志信息能输出到控制台
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KProducer:
    """
    一个KafkaProducer的封装类，用于处理与Kafka的连接和消息发送。
    增加了日志回调功能，可以将内部状态信息传递给UI界面。
    """
    def __init__(self, bootstrap_servers, log_callback=None):
        """
        初始化生产者。
        :param bootstrap_servers: Kafka集群的地址，例如 'localhost:9092'。
        :param log_callback: 一个用于接收日志信息的回调函数。
        """
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self.log_callback = log_callback
        self.connect()

    def _log(self, message):
        """
        内部日志记录函数。
        如果设置了回调函数，则调用它；否则，使用标准的logging模块。
        """
        if self.log_callback:
            self.log_callback(message)
        else:
            # 使用时间戳格式化日志，与UI保持一致
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            logger.info(f"[{timestamp}] {message}")

    def connect(self):
        """
        尝试连接到Kafka服务器。
        """
        try:
            self._log(f"正在尝试连接到 Kafka 服务器: {self.bootstrap_servers}...")
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                # value_serializer 可以在这里设置，但我们直接发送bytes
                # value_serializer=lambda v: v.SerializeToString(),
                retries=3,  # 重试次数
                request_timeout_ms=30000,  # 请求超时时间
                linger_ms=100  # 消息在缓冲区等待更多消息加入批次的时间
            )
            self._log("成功连接到 Kafka！")
        except NoBrokersAvailable:
            self._log(f"错误: 无法连接到 Kafka 服务器 {self.bootstrap_servers}。请检查服务是否运行。")
            self.producer = None
        except Exception as e:
            self._log(f"连接 Kafka 时发生未知错误: {e}")
            self.producer = None

    def send_message(self, topic, message_bytes):
        """
        向指定的Kafka topic发送单条消息。

        :param topic: 目标topic的名称。
        :param message_bytes: 消息的字节流 (例如，经过protobuf序列化的数据)。
        :return: 如果发送成功则返回 True，否则返回 False。
        """
        if not self.producer:
            self._log("错误: Kafka 生产者未连接，无法发送消息。")
            return False

        try:
            # 发送消息，这是一个异步操作，返回一个Future对象
            future = self.producer.send(topic, value=message_bytes)
            
            # 调用 .get() 方法会阻塞，直到消息被确认发送或超时
            # 这使得发送行为变成“同步”的，方便我们获取发送结果
            record_metadata = future.get(timeout=10)
            
            self._log(
                f"消息已发送到 Topic '{record_metadata.topic}' "
                f"(分区 {record_metadata.partition}, "
                f"偏移量 {record_metadata.offset})"
            )
            return True
        except Exception as e:
            self._log(f"发送消息到 Topic '{topic}' 失败: {e}")
            return False

    def close(self):
        """
        关闭Kafka生产者连接，确保所有缓冲区的消息都被发送。
        """
        if self.producer:
            self._log("正在关闭 Kafka 生产者...")
            self.producer.flush()  # 等待所有未���送的消息完成发送
            self.producer.close()
            self._log("Kafka 生产者已关闭。")
